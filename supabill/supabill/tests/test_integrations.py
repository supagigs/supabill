"""CBIC and Excel integrations against fake HTTP servers. No network is used."""
import json
import re
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import invoice as api
from supabill.supabill import cbic, excel
from supabill.supabill.tests.fixtures import payload, setup_basics

SECRET = "sb-test-secret-value"
KEY = "art_live_test_key_value"


class Resp:
	def __init__(self, status=200, body=None, headers=None):
		self.status_code, self._body, self.headers = status, body, headers or {}
		self.content = b"" if body is None else json.dumps(body).encode()

	def json(self):
		if isinstance(self._body, str):
			raise ValueError("not json")
		return self._body


class FakeWorkbook:
	"""Just enough of Microsoft Graph's workbook API for SupaBill."""

	def __init__(self):
		self.header = list(excel.COLUMNS)
		self.rows = []
		self.first = 2  # header on sheet row 2, as in the Supagigs register
		self.fail_next = []  # list of status codes to return first
		self.calls = []

	def request(self, method, url, json=None, timeout=None, headers=None):
		self.calls.append((method, url))
		if self.fail_next:
			code = self.fail_next.pop(0)
			return Resp(code, {"error": {"message": "boom"}}, {"Retry-After": "0"})
		if "/shares/" in url:
			return Resp(200, {"id": "ITEM", "parentReference": {"driveId": "DRIVE"}})
		if url.endswith("/range") and method == "GET":
			last = self.first + len(self.rows)
			return Resp(200, {"address": f"'2026-27'!A{self.first}:V{last}", "values": [self.header, *self.rows]})
		if url.endswith("/rows") and method == "POST":
			self.rows.append(list(json["values"][0]))
			return Resp(201, {"index": len(self.rows) - 1}, {"request-id": "req-1"})
		m = re.search(r"range\(address='A(\d+):V\d+'\)", url)
		if m:
			idx = int(m.group(1)) - self.first - 1
			if method == "GET":
				return Resp(200, {"formulas": [self.rows[idx]]})
			self.rows[idx] = list(json["formulas"][0])
			return Resp(200, {}, {"request-id": "req-2"})
		return Resp(404, {"error": {"message": "not found " + url}})


def token_ok(*a, **k):
	return Resp(200, {"access_token": "tok", "expires_in": 3600})


class TestIntegrations(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_basics()

	def tearDown(self):
		frappe.db.set_single_value("SupaBill Settings", {"excel_enabled": 0, "ms_client_secret": None,
			"allratestoday_api_key": None, "cbic_provider": "AllRatesToday"})
		frappe.clear_document_cache("SupaBill Settings", "SupaBill Settings")

	def setUp(self):
		frappe.cache.delete_keys("supabill:graph_token")
		s = frappe.get_doc("SupaBill Settings")
		s.update({"excel_enabled": 1, "ms_tenant_id": "tenant", "ms_client_id": "client", "ms_client_secret": SECRET,
			"workbook_share_link": "https://example.sharepoint.com/:x:/g/abc", "worksheet_name": "2026-27",
			"table_name": "Register", "cbic_provider": "AllRatesToday", "allratestoday_api_key": KEY})
		s.flags.ignore_permissions = True
		s.save()
		self.wb = FakeWorkbook()

	def graph(self):
		return patch.multiple(excel.requests, request=self.wb.request, post=token_ok)

	def make(self, **kw):
		with patch("frappe.enqueue"):  # jobs are run by hand in these tests
			return api.create_invoice(payload(**kw), request_id=frappe.generate_hash())["name"]

	# ---------- Excel ----------
	def test_push_adds_row_with_formulas_once(self):
		name = self.make()
		with self.graph(), patch("time.sleep"):
			excel.push_invoice(name)
			excel.push_invoice(name)  # second run must not add a duplicate row
		self.assertEqual(len(self.wb.rows), 1)
		row = dict(zip(excel.COLUMNS, self.wb.rows[0]))
		self.assertEqual(row["Original Invoice Number"], name)
		self.assertEqual(row["Month"], "=MONTH(F3)")
		self.assertEqual(row["Invoice Amount in INR"], "=M3*N3")
		self.assertEqual(row["Forex Gain"], "=P3-O3")
		self.assertEqual(row["Invoice Amount in Original Currency"], 1000)
		d = frappe.get_doc("SB Invoice", name)
		self.assertEqual((d.excel_sync_status, d.excel_row), ("Synced", 3))

	def test_pull_excel_wins_and_blanks_do_not_wipe(self):
		name = self.make()
		with self.graph(), patch("time.sleep"):
			excel.push_invoice(name)
			row = self.wb.rows[0]
			row[excel.COL["Received"]] = "88,000"
			row[excel.COL["Wallet Reference Invoice Number"]] = "W-777"
			row[excel.COL["Payment Status"]] = "Paid"
			with patch("frappe.enqueue") as enq:
				out = excel.pull(force=True)
				enq.assert_not_called()  # changes that came from Excel are not pushed back
		self.assertEqual(out["updated"], 1)
		d = frappe.get_doc("SB Invoice", name)
		self.assertEqual((d.received_inr, d.wallet_reference, d.payment_status), (88000, "W-777", "Received"))
		self.assertEqual(d.forex_gain, 88000 - d.amount_inr)
		with self.graph(), patch("time.sleep"):
			self.wb.rows[0][excel.COL["Wallet Reference Invoice Number"]] = ""
			excel.pull(force=True)
		self.assertEqual(frappe.db.get_value("SB Invoice", name, "wallet_reference"), "W-777")

	def test_register_edit_written_back_keeping_formulas(self):
		name = self.make()
		with self.graph(), patch("time.sleep"):
			excel.push_invoice(name)
			api.update_register(name, {"received_inr": 50000, "wallet_reference": "W-9"})
			excel.push_register_update(name)
		row = dict(zip(excel.COLUMNS, self.wb.rows[0]))
		self.assertEqual((row["Received"], row["Wallet Reference Invoice Number"]), (50000, "W-9"))
		self.assertEqual(row["Forex Gain"], "=P3-O3")  # formula untouched

	def test_retry_on_429_then_success(self):
		name = self.make()
		self.wb.fail_next = [429, 503]
		with self.graph(), patch("time.sleep"):
			excel.push_invoice(name)
		self.assertEqual(frappe.db.get_value("SB Invoice", name, "excel_sync_status"), "Synced")

	def test_403_is_logged_as_failed_without_secret(self):
		name = self.make()
		self.wb.fail_next = [403]
		with self.graph(), patch("time.sleep"):
			excel.push_invoice(name)
		self.assertEqual(frappe.db.get_value("SB Invoice", name, "excel_sync_status"), "Failed")
		log = frappe.get_last_doc("SB Sync Log", filters={"invoice": name})
		self.assertIn("no access to this file", log.message)
		self.assertNotIn(SECRET, log.message)

	def test_missing_columns_and_bad_signin(self):
		self.wb.header = [h for h in excel.COLUMNS if h != "Received"]
		with self.graph(), patch("time.sleep"):
			out = excel.pull(force=True)
		self.assertFalse(out["ok"])
		self.assertIn("missing columns: Received", out["message"])
		self.wb.header = list(excel.COLUMNS)
		frappe.cache.delete_keys("supabill:graph_token")
		bad = lambda *a, **k: Resp(401, {"error_description": "AADSTS7000215: Invalid client secret provided."})  # noqa: E731
		with patch.multiple(excel.requests, request=self.wb.request, post=bad):
			out = excel.pull(force=True)
		self.assertIn("Microsoft sign-in failed: AADSTS7000215", out["message"])
		self.assertNotIn(SECRET, out["message"])

	def test_retry_failed_requeues(self):
		name = self.make()
		frappe.db.set_value("SB Invoice", name, "excel_sync_status", "Failed")
		with self.graph(), patch("time.sleep"):
			excel.retry_failed()
		self.assertEqual(frappe.db.get_value("SB Invoice", name, "excel_sync_status"), "Synced")

	def test_share_id_and_letters(self):
		self.assertEqual(excel.share_id("https://a.b/c"), "u!aHR0cHM6Ly9hLmIvYw")
		self.assertEqual([excel.letter(i) for i in (0, 21, 25, 26)], ["A", "V", "Z", "AA"])

	# ---------- CBIC ----------
	def test_cbic_sync_keyed(self):
		seen = {}

		def get(url, params=None, headers=None, timeout=None):
			seen["auth"] = headers.get("Authorization")
			return Resp(200, {"rate_date": "2026-11-20", "rates": [
				{"base": "USD", "quote": "INR", "type": "export", "value": 88.9},
				{"base": "USD", "quote": "INR", "type": "import", "value": 90.6},
				{"base": "EUR", "quote": "INR", "type": "export", "value": 96.4},
				{"base": "JPY", "quote": "INR", "type": "export", "value": 0.58}]})
		with patch.object(cbic.requests, "get", get):
			out = cbic.sync()
		self.assertTrue(out["ok"], out)
		self.assertEqual(seen["auth"], f"Bearer {KEY}")
		usd = frappe.get_doc("SB CBIC Rate", "USD-2026-11-20")
		self.assertEqual((usd.export_rate, usd.import_rate, usd.source), (88.9, 90.6, "AllRatesToday"))
		self.assertFalse(frappe.db.exists("SB CBIC Rate", "JPY-2026-11-20"))
		self.assertEqual(api.cbic_rate_for("2026-11-25", "USD")["rate"], 88.9)
		self.assertNotIn(KEY, frappe.db.get_single_value("SupaBill Settings", "cbic_last_status"))

	def test_cbic_401_falls_back_to_keyfree(self):
		def get(url, params=None, headers=None, timeout=None):
			if "/api/v1/" in url:
				return Resp(401, {})
			return Resp(200, {"rate_date": "2026-12-04", "rates": [{"base": "USD", "quote": "INR", "type": "export", "value": 89.2}]})
		with patch.object(cbic.requests, "get", get):
			self.assertTrue(cbic.sync()["ok"])
		self.assertTrue(frappe.db.exists("SB CBIC Rate", "USD-2026-12-04"))

	def test_cbic_errors_keep_existing_rates(self):
		before = frappe.db.count("SB CBIC Rate")
		cases = [Resp(403, {}), Resp(200, {"unexpected": True}), Resp(200, "<html>"),
			Resp(200, {"rate_date": "2026-12-18", "rates": []})]
		for resp in cases:
			with patch.object(cbic.requests, "get", lambda *a, r=resp, **k: r), patch("time.sleep"):
				out = cbic.sync()
			self.assertFalse(out["ok"])
		self.assertEqual(frappe.db.count("SB CBIC Rate"), before)
		with patch.object(cbic.requests, "get", lambda *a, **k: Resp(500, {})), patch("time.sleep"):
			self.assertIn("unreachable (HTTP 500)", cbic.sync()["message"])

	def test_cbic_manual_mode_skips(self):
		frappe.db.set_single_value("SupaBill Settings", "cbic_provider", "Manual")
		frappe.clear_document_cache("SupaBill Settings", "SupaBill Settings")
		with patch.object(cbic.requests, "get") as g:
			self.assertFalse(cbic.sync()["ok"])
			g.assert_not_called()
