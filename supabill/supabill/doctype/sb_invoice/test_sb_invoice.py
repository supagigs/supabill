import frappe
from frappe.tests import IntegrationTestCase


EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["SB Client", "SB Wallet", "Currency", "Country", "SB Purpose Code"]

from supabill.supabill.tests.fixtures import PREFIX, make_user, setup_basics


class TestSBInvoice(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_basics()
		cls.user = make_user("sb.user@example.com", "SupaBill User")
		cls.manager = make_user("sb.manager@example.com", "SupaBill Manager")

	def tearDown(self):
		frappe.set_user("Administrator")

	def new_invoice(self, **kw):
		doc = {"doctype": "SB Invoice", "client": "Acme Test", "invoice_date": "2026-11-10",
			"currency": "USD", "tax_treatment": "Export under LUT", "milestone": "Milestone 1 of 2",
			"items": [{"description": "Work", "qty": 1, "rate": 1000}]}
		doc.update(kw)
		return frappe.get_doc(doc)

	def test_numbering_increments_and_skips_existing(self):
		a = self.new_invoice().insert()
		b = self.new_invoice().insert()
		self.assertTrue(a.name.startswith(PREFIX))
		self.assertEqual(int(b.name[-3:]), int(a.name[-3:]) + 1)
		# someone sets the counter back: the next free number is used, never a duplicate
		frappe.db.set_single_value("SupaBill Settings", "next_invoice_number", int(a.name[-3:]))
		c = self.new_invoice().insert()
		self.assertNotIn(c.name, (a.name, b.name))

	def test_totals_dates_and_snapshot(self):
		inv = self.new_invoice(items=[{"description": "A", "qty": 2, "rate": 500},
			{"description": "B", "qty": 1, "rate": 250}]).insert()
		self.assertEqual(inv.grand_total, 1250)
		self.assertEqual(str(inv.due_date), "2026-12-01")
		self.assertEqual(inv.gst_return_period, "October - December 2026")
		self.assertEqual(inv.billing_address, "1 Main St")
		self.assertIn("Account Number: 123", inv.bank_details)
		self.assertEqual(inv.notes, "LUT ARN ARN123")

	def test_igst_totals(self):
		inv = self.new_invoice(tax_treatment="IGST 18%").insert()
		self.assertEqual((inv.subtotal, inv.tax_total, inv.grand_total), (1000, 180, 1180))

	def test_cbic_rate_by_date_and_manual(self):
		self.assertEqual(self.new_invoice().insert().cbic_rate, 88.45)
		old = self.new_invoice(invoice_date="2026-10-20").insert()
		self.assertEqual((old.cbic_rate, str(old.cbic_rate_effective_from)), (88.10, "2026-10-17"))
		self.assertEqual(old.amount_inr, 88100)
		man = self.new_invoice(cbic_rate_source="Manual", cbic_rate=90).insert()
		self.assertEqual(man.cbic_rate, 90)

	def test_blocking_checks(self):
		with self.assertRaises(frappe.ValidationError):
			self.new_invoice(invoice_date="2026-01-01").insert()  # no CBIC rate that early
		with self.assertRaises(frappe.ValidationError):
			self.new_invoice(wallet="Half Wallet").insert()
		with self.assertRaises(frappe.ValidationError):
			self.new_invoice(items=[{"description": "Zero", "qty": 1, "rate": 0}]).insert()

	def test_submit_and_register_update(self):
		inv = self.new_invoice().insert()
		inv.submit()
		self.assertEqual(frappe.db.get_value("SB Client", "Acme Test", "last_milestone"), "Milestone 1 of 2")
		self.assertEqual(inv.excel_sync_status, "Not synced")  # Excel sync off in tests
		inv.reload()
		inv.received_inr = 88000
		inv.bank_charges_inr = 300
		inv.save()
		self.assertEqual(inv.payment_status, "Received")
		self.assertEqual((inv.forex_gain, inv.net_received), (-450, 87700))
		inv.items[0].rate = 5
		with self.assertRaises(frappe.ValidationError):
			inv.save()  # invoice content is locked after submit

	def test_permissions(self):
		frappe.set_user(self.user)
		self.assertTrue(frappe.has_permission("SB Invoice", "create"))
		self.assertTrue(frappe.has_permission("SB Invoice", "submit"))
		self.assertFalse(frappe.has_permission("SB Invoice", "cancel"))
		self.assertFalse(frappe.has_permission("SB Invoice", "delete"))
		self.assertFalse(frappe.has_permission("SupaBill Settings", "write"))
		self.assertFalse(frappe.has_permission("SB Wallet", "write"))
		self.assertFalse(frappe.has_permission("SB CBIC Rate", "create"))
		self.assertTrue(frappe.has_permission("SB Client", "create"))
		self.assertFalse(frappe.has_permission("SB Client", "delete"))
		frappe.set_user(self.manager)
		self.assertTrue(frappe.has_permission("SB Invoice", "cancel"))
		self.assertTrue(frappe.has_permission("SupaBill Settings", "write"))
		self.assertTrue(frappe.has_permission("SB Wallet", "write"))
		frappe.set_user("Guest")
		self.assertFalse(frappe.has_permission("SB Invoice", "read"))

	def test_settings_rejects_used_number(self):
		inv = self.new_invoice().insert()
		s = frappe.get_doc("SupaBill Settings")
		s.next_invoice_number = int(inv.name[-3:])
		with self.assertRaises(frappe.ValidationError):
			s.save(ignore_permissions=True)
