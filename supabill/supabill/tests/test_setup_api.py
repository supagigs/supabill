import json

import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import invoice as inv_api
from supabill.api import setup as api
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics


class TestSetupAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_basics()
		cls.user = make_user("set.user@example.com", "SupaBill User")
		cls.manager = make_user("set.manager@example.com", "SupaBill Manager")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_client_create_rename_and_guarded_delete(self):
		frappe.set_user(self.user)
		api.save_client({"client_name": "Globex", "address": "2 Side St", "wallet": "Test Wallet", "currency": "USD"})
		api.save_client({"client_name": "Globex Corp", "address": "2 Side St"}, name="Globex")
		self.assertTrue(frappe.db.exists("SB Client", "Globex Corp"))
		self.assertFalse(frappe.db.exists("SB Client", "Globex"))
		with self.assertRaises(frappe.PermissionError):
			api.delete_client("Globex Corp")  # users cannot delete
		frappe.set_user(self.manager)
		inv_api.create_invoice(payload(client="Globex Corp"), request_id="setup-1")
		with self.assertRaises(frappe.ValidationError):
			api.delete_client("Globex Corp")  # has invoices
		row = next(c for c in api.list_clients() if c.name == "Globex Corp")
		self.assertEqual(row["invoice_count"], 1)

	def test_wallet_crud_manager_only(self):
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			api.save_wallet({"wallet_name": "Wise"})
		frappe.set_user(self.manager)
		api.save_wallet({"wallet_name": "Wise", "details": [{"label": "IBAN", "value": "X1"}, {"label": "", "value": "dropped"}]})
		w = next(w for w in api.list_wallets() if w.name == "Wise")
		self.assertEqual([d.label for d in w["details"]], ["IBAN"])
		self.assertTrue(w["complete"])
		api.save_wallet({"wallet_name": "Wise EU", "details": [{"label": "IBAN", "value": ""}]}, name="Wise")
		w = next(w for w in api.list_wallets() if w.name == "Wise EU")
		self.assertFalse(w["complete"])
		api.delete_wallet("Wise EU")

	def test_settings_secrets_write_only(self):
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			api.get_settings()
		frappe.set_user(self.manager)
		out = api.save_settings({"lut_arn": "ARN999"}, secrets={"allratestoday_api_key": "art_live_secret_value"})
		self.assertTrue(out["has_allratestoday_api_key"])
		self.assertNotIn("art_live_secret_value", json.dumps(out, default=str))
		self.assertNotIn("allratestoday_api_key", [k for k in out if not k.startswith("has_")])
		out = api.save_settings({}, secrets={"allratestoday_api_key": ""})  # blank keeps the old value
		self.assertTrue(out["has_allratestoday_api_key"])
		out = api.save_settings({}, clear_secrets=["allratestoday_api_key"])
		self.assertFalse(out["has_allratestoday_api_key"])
		self.assertEqual(out["lut_arn"], "ARN999")

	def test_settings_ignore_unknown_fields(self):
		frappe.set_user(self.manager)
		out = api.save_settings({"cbic_last_status": "hacked", "legal_name": "Test Co"})
		self.assertNotEqual(out["cbic_last_status"], "hacked")

	def test_codes_and_rates(self):
		frappe.set_user(self.manager)
		codes = api.save_code("tax", "8471", "Computers", code_type="HSN")
		self.assertIn("HSN-8471", [c.name for c in codes["tax_codes"]])
		codes = api.toggle_favourite("tax", "HSN-8471")
		self.assertEqual(next(c for c in codes["tax_codes"] if c.name == "HSN-8471").is_favourite, 0)
		with self.assertRaises(frappe.ValidationError):
			api.save_code("tax", "84A1", "bad", code_type="HSN")
		rates = api.save_cbic_rate("2026-12-03", "USD", 89.1, 90.8)
		self.assertIn("USD-2026-12-03", [r.name for r in rates])
		self.assertEqual(inv_api.cbic_rate_for("2026-12-10", "USD")["rate"], 89.1)
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			api.save_cbic_rate("2026-12-17", "USD", 1)
