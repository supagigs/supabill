import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, getdate

from supabill.api import edf, invoice
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics

MONTH = "2026-11"


class TestEDF(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_basics()
		cls.inv = invoice.create_invoice(payload(client_request_id=frappe.generate_hash()))["name"]
		cls.gst = invoice.create_invoice(payload(client_request_id=frappe.generate_hash(), tax_treatment="IGST 18%"))["name"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("SB EDF", {"month": MONTH})

	def test_due_and_realise_dates(self):
		self.assertEqual(str(edf.due_date(MONTH)), "2026-12-30")
		doc = frappe.get_doc("SB Invoice", self.inv)
		self.assertEqual(getdate(doc.realise_by), getdate(add_months(doc.invoice_date, 9)))

	def test_draft_includes_only_export_invoices(self):
		d = edf.get_edf(MONTH)
		names = [l["invoice"] for l in d["lines"]]
		self.assertIn(self.inv, names)
		self.assertNotIn(self.gst, names)
		line = next(l for l in d["lines"] if l["invoice"] == self.inv)
		self.assertEqual(line["net_realisable_value"], line["amount"])
		self.assertEqual(line["country"], "United States")
		self.assertTrue(d["total_in_words"])

	def test_edits_survive_refresh_and_are_validated(self):
		edf.get_edf(MONTH)
		edf.save_edf(MONTH, {"form_no": "F1"}, [{"invoice": self.inv, "remarks": "Hello", "net_realisable_value": 900}])
		d = edf.get_edf(MONTH)
		line = next(l for l in d["lines"] if l["invoice"] == self.inv)
		self.assertEqual((line["remarks"], line["net_realisable_value"], d["form_no"]), ("Hello", 900, "F1"))
		with self.assertRaises(frappe.ValidationError):
			edf.save_edf(MONTH, {}, [{"invoice": self.inv, "net_realisable_value": 999999}])

	def test_file_freezes_and_reopen(self):
		edf.get_edf(MONTH)
		d = edf.mark_filed(MONTH, "REF-9")
		self.assertEqual(d["status"], "Filed")
		self.assertEqual(frappe.db.get_value("SB Invoice", self.inv, "edf"), f"EDF-{MONTH}")
		with self.assertRaises(frappe.ValidationError):
			edf.save_edf(MONTH, {}, [{"invoice": self.inv, "remarks": "x"}])
		edf.save_edf(MONTH, {"form_no": "F2"})  # form no. may still be added
		d = edf.reopen(MONTH)
		self.assertEqual(d["status"], "Draft")
		self.assertFalse(frappe.db.get_value("SB Invoice", self.inv, "edf"))

	def test_user_cannot_file(self):
		edf.get_edf(MONTH)
		frappe.set_user(make_user("edf.user@example.com", "SupaBill User"))
		self.assertTrue(edf.get_edf(MONTH)["lines"])
		with self.assertRaises(frappe.PermissionError):
			edf.mark_filed(MONTH)

	def test_outsider_blocked(self):
		frappe.set_user(make_user("edf.nobody@example.com"))
		with self.assertRaises(frappe.PermissionError):
			edf.list_months()

	def test_pdf_and_csv(self):
		html = edf.render_html(MONTH)
		self.assertIn("Export Declaration Form", html)
		self.assertIn(self.inv, html)
		edf.download(MONTH, "csv")
		self.assertIn(b"Net Realisable value", frappe.local.response.filecontent)

	def test_html_is_escaped(self):
		edf.get_edf(MONTH)
		edf.save_edf(MONTH, {}, [{"invoice": self.inv, "remarks": "<script>x</script>"}])
		self.assertNotIn("<script>x", edf.render_html(MONTH))

	def test_realisation_close(self):
		r = edf.update_realisation(self.inv, {"irm_number": " IRM1 ", "edpms_status": "Closed"})
		self.assertEqual((r["irm_number"], r["edpms_status"]), ("IRM1", "Closed"))
		self.assertTrue(r["realised_on"])
		rows = edf.realisation()["rows"]
		self.assertNotIn(self.inv, [x["name"] for x in rows])
		self.assertIn(self.inv, [x["name"] for x in edf.realisation(show_closed=1)["rows"]])
		r = edf.update_realisation(self.inv, {"edpms_status": "Open"})
		self.assertIsNone(r["realised_on"])
		with self.assertRaises(frappe.ValidationError):
			edf.update_realisation(self.inv, {"received_inr": 5})

	def test_bad_month(self):
		with self.assertRaises(frappe.ValidationError):
			edf.get_edf("2026-13")
