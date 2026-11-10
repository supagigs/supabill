import json

import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import invoice as api
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics


class TestInvoiceAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_basics()
		cls.user = make_user("api.user@example.com", "SupaBill User")
		cls.manager = make_user("api.manager@example.com", "SupaBill Manager")
		cls.stranger = make_user("api.none@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_bootstrap_has_no_secrets(self):
		frappe.set_user(self.user)
		b = api.bootstrap()
		self.assertIn("Acme Test", [c.name for c in b["clients"]])
		self.assertTrue(next(w for w in b["wallets"] if w.name == "Test Wallet")["complete"])
		self.assertFalse(next(w for w in b["wallets"] if w.name == "Half Wallet")["complete"])
		blob = json.dumps(b, default=str)
		for secret in ("ms_client_secret", "allratestoday_api_key"):
			self.assertNotIn(secret, blob)

	def test_preview_matches_saved_invoice(self):
		frappe.set_user(self.user)
		p = api.preview(payload(tax_treatment="IGST 18%"))
		self.assertEqual((p["subtotal"], p["tax_total"], p["grand_total"]), (1000, 180, 1180))
		self.assertEqual(p["cbic_rate"], 88.45)
		self.assertEqual(p["due_date"], "2026-12-01")
		self.assertFalse([r for r in p["readiness"] if r["level"] == "error"])
		saved = api.create_invoice(payload(tax_treatment="IGST 18%"), request_id="prev-1")
		self.assertEqual((saved["grand_total"], saved["amount_inr"]), (1180, p["amount_inr"]))

	def test_preview_reports_blockers_without_throwing(self):
		frappe.set_user(self.user)
		p = api.preview(payload(wallet="Half Wallet", invoice_date="2026-01-01", items=[]))
		errors = {r["message"] for r in p["readiness"] if r["level"] == "error"}
		self.assertTrue(any("Bank details" in e for e in errors))
		self.assertTrue(any("CBIC" in e for e in errors))
		self.assertTrue(any("Amount" in e for e in errors))

	def test_create_is_idempotent(self):
		frappe.set_user(self.user)
		a = api.create_invoice(payload(), request_id="same-click")
		b = api.create_invoice(payload(), request_id="same-click")
		self.assertEqual(a["name"], b["name"])
		self.assertTrue(b["duplicate"])
		self.assertEqual(frappe.db.get_value("SB Invoice", a["name"], "docstatus"), 1)

	def test_update_register_only_register_fields(self):
		frappe.set_user(self.user)
		inv = api.create_invoice(payload(), request_id="reg-1")
		row = api.update_register(inv["name"], {"received_inr": 88000, "wallet_reference": "W-1"})
		self.assertEqual(row["payment_status"], "Received")
		self.assertEqual(row["forex_gain"], -450)
		with self.assertRaises(frappe.ValidationError):
			api.update_register(inv["name"], {"grand_total": 1})
		cleared = api.update_register(inv["name"], {"received_inr": ""})
		self.assertIsNone(cleared["forex_gain"])

	def test_cancel_needs_manager(self):
		frappe.set_user(self.user)
		inv = api.create_invoice(payload(), request_id="cancel-1")
		with self.assertRaises(frappe.PermissionError):
			api.cancel_invoice(inv["name"])
		frappe.set_user(self.manager)
		self.assertEqual(api.cancel_invoice(inv["name"], "test")["docstatus"], 2)
		self.assertEqual(frappe.db.get_value("SB Invoice", inv["name"], "invoice_status"), "Cancelled")

	def test_list_register_filters_and_totals(self):
		frappe.set_user(self.user)
		a = api.create_invoice(payload(), request_id="list-1")
		api.create_invoice(payload(invoice_date="2026-10-20"), request_id="list-2")
		api.update_register(a["name"], {"received_inr": 88450})
		nov = api.list_register({"month": "2026-11"})
		self.assertTrue(all(str(r.invoice_date).startswith("2026-11") for r in nov["rows"]))
		self.assertIn(a["name"], [r.name for r in nov["rows"]])
		received = api.list_register({"payment_state": "Received"})
		self.assertTrue(all(r.payment_state == "Received" for r in received["rows"]))
		found = api.list_register(search=a["name"])
		self.assertEqual([r.name for r in found["rows"]], [a["name"]])
		self.assertGreaterEqual(nov["totals"]["received_inr"], 88450)

	def test_stranger_is_refused(self):
		frappe.set_user(self.stranger)
		for call in (api.bootstrap, lambda: api.preview(payload()), lambda: api.list_register()):
			with self.assertRaises(frappe.PermissionError):
				call()
