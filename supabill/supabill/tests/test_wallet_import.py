import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import wallet_import as api
from supabill.supabill import wallet_import as wi
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics

HEADER = "Wallet Name,If Wallet Exists,Paid via Upwork,Beneficiary Name,Account Number,Routing / SWIFT Code,Bank Name,IBAN,Other Details\n"


def _upload(content: bytes, name: str) -> str:
	return frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1, "content": content}).insert().file_url


def _details(name):
	return {d.label: d.value for d in frappe.get_doc("SB Wallet", name).details}


class TestWalletImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_basics()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_template_header_matches_staging_doctype(self):
		labels = wi.template_csv().strip().split(",")
		meta = frappe.get_meta("SB Wallet Import")
		self.assertEqual(labels, [meta.get_field(f).label for f, _l in wi.COLUMNS])

	def test_review_flags_new_existing_and_errors(self):
		rows = wi.review(wi.read_csv(HEADER + "Test Wallet,Update,,,9,,,,\nWI New,,,,1,,,,\nWI Dup,,,,1,,,,\nWI Dup,,,,2,,,,\n,,,,3,,,,\n"))
		st = [(r["wallet_name"], r["status"], r["action"]) for r in rows]
		self.assertEqual(st[0], ("Test Wallet", "exists", "update"))
		self.assertEqual(st[1], ("WI New", "new", "create"))
		self.assertEqual([s[1] for s in st[2:]], ["error", "error", "error"])

	def test_missing_header_refused(self):
		with self.assertRaises(frappe.ValidationError):
			wi.read_csv("Name,Account\nA,1\n")

	def test_details_order_and_extras(self):
		d = wi.details_from_row({"account_number": "1", "iban": "DE1", "other_details": "Sort Code: 20-20-15\nIBAN: dup"})
		self.assertEqual([x["label"] for x in d][:7], [l for _f, l in wi.STANDARD])
		self.assertEqual(d[7:], [{"label": "IBAN", "value": "DE1"}, {"label": "Sort Code", "value": "20-20-15"}])
		self.assertEqual(wi.details_from_row({"is_upwork": 1}), [])

	def test_merge_keeps_blank_and_adds_filled(self):
		cur = [{"label": "Account Number", "value": "1"}, {"label": "ACH Routing Code", "value": "026"}]
		inc = [{"label": "Account Number", "value": ""}, {"label": "Bank Name", "value": "B"}, {"label": "Routing / SWIFT Code", "value": ""}]
		self.assertEqual(wi.merge_details(cur, inc), cur + [{"label": "Bank Name", "value": "B"}])

	def test_run_csv_create_update_skip_rename(self):
		frappe.db.delete("SB Wallet Detail", {"parent": ("like", "WI %")})
		frappe.db.delete("SB Wallet", {"name": ("like", "WI %")})
		frappe.get_doc({"doctype": "SB Wallet", "wallet_name": "WI Half", "details": [
			{"label": "Account Number", "value": ""}, {"label": "Bank Name", "value": "Keep Bank"}]}).insert()
		url = _upload((HEADER + "WI Alpha,,,Acme,111,,Bank A,DE89,\nTest Wallet,,,,,,,,\nWI Half,,,,555,,,,\nUpwork,,,,,,,,\n").encode(), "w.csv")
		rev = api.review_csv(url)
		self.assertFalse(frappe.db.exists("File", {"file_url": url}), "upload is deleted after reading")
		rows = rev["rows"]
		rows[1]["action"] = "skip"
		rows[2]["action"] = "update"
		rows[3]["action"], rows[3]["wallet_name"] = "rename", "WI Upwork Two"
		out = api.run_csv(rows)
		st = api.csv_status(out["data_import"])
		self.assertEqual((st["status"], st["created"], st["updated"], out["skipped"]), ("Success", 2, 1, 1))
		self.assertEqual(_details("WI Alpha")["IBAN"], "DE89")
		self.assertEqual(_details("WI Half"), {"Account Number": "555", "Bank Name": "Keep Bank"})
		self.assertTrue(frappe.db.exists("SB Wallet", "WI Upwork Two"))
		self.assertEqual(_details("Test Wallet")["Account Number"], "123", "skipped wallet unchanged")

	def test_run_csv_refuses_unresolved_clash(self):
		rows = wi.review(wi.read_csv(HEADER + "Test Wallet,,,,1,,,,\n"))
		rows[0]["action"] = "create"
		with self.assertRaises(frappe.ValidationError):
			api.run_csv(rows)
		rows[0].update(action="rename", wallet_name="Half Wallet")
		with self.assertRaises(frappe.ValidationError):
			api.run_csv(rows)

	def test_pdf_from_supabill_invoice(self):
		from supabill.api import invoice
		from supabill.api.output import render_pdf
		name = invoice.create_invoice(payload(client_request_id=frappe.generate_hash()))["name"]
		url = _upload(render_pdf(frappe.get_doc("SB Invoice", name)), "inv.pdf")
		out = api.read_pdf(url)
		self.assertTrue(out["block_found"])
		self.assertEqual({d["label"]: d["value"] for d in out["details"]}, {"Account Number": "123", "Bank Name": "Test Bank"})

	def test_pdf_text_other_layout(self):
		text = "ACME\nInvoice 5\nWire instructions\nAccount Name: Foo Ltd\nIBAN: GB33BUKB\nSWIFT/BIC: BUKBGB22\nThank you\nEmail: x@y.z"
		labels = [d["label"] for d in wi.bank_lines_from_text(text)["details"]]
		self.assertEqual(labels, ["Account Name", "IBAN", "SWIFT/BIC"])
		loose = wi.bank_lines_from_text("Invoice No: 5\nEmail: a@b\nAccount No: 77\nIFSC: IDFB0000001")["details"]
		self.assertEqual([d["label"] for d in loose], ["Account No", "IFSC"])

	def test_bad_pdf(self):
		with self.assertRaises(frappe.ValidationError):
			api.read_pdf(_upload(b"not a pdf", "x.txt"))

	def test_manager_only(self):
		frappe.set_user(make_user("wi.user@example.com", "SupaBill User"))
		with self.assertRaises(frappe.PermissionError):
			api.review_csv("/private/files/x.csv")
		with self.assertRaises(frappe.PermissionError):
			api.read_pdf("/private/files/x.pdf")

	def test_cannot_read_someone_elses_upload(self):
		url = _upload(b"hello", "a.txt")
		frappe.set_user(make_user("wi.mgr@example.com", "SupaBill Manager"))
		with self.assertRaises(frappe.PermissionError):
			api.read_pdf(url)
