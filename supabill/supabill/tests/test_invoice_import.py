import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import invoice_import as api
from supabill.api.output import render_docx, render_pdf
from supabill.supabill import invoice_import as ii
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics

HEAD = ii.template_csv().strip()
P = "IMP" + frappe.generate_hash(length=4).upper() + "/"  # Data Import commits, so numbers are unique per run


def _csv(*rows: dict) -> bytes:
	labels = HEAD.split(",")
	fields = [dict((l, f) for f, l in ii.COLUMNS)[l] for l in labels]
	out = [HEAD]
	for r in rows:
		out.append(",".join('"' + str(r.get(f, "")).replace('"', '""') + '"' for f in fields))
	return ("\n".join(out) + "\n").encode()


def _upload(content: bytes, name: str) -> str:
	return frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1, "content": content}).insert().file_url


ROW = {"invoice_date": "15/04/2026", "client": "Acme Test", "currency": "USD", "amount": "1,000.00",
	"tax_treatment": "Export under LUT", "wallet": "Test Wallet", "description": "Old work", "sac_code": "998313",
	"cbic_rate": "85.5", "received_inr": "85000", "payment_status": "Received", "wallet_reference": "W-1"}


class TestInvoiceImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_basics()

	@classmethod
	def tearDownClass(cls):
		# Data Import commits its rows, so remove what this run created
		frappe.set_user("Administrator")
		for name in frappe.get_all("SB Invoice", filters={"name": ("like", P + "%")}, pluck="name"):
			doc = frappe.get_doc("SB Invoice", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("SB Invoice", name, force=True, ignore_permissions=True)
		for c in frappe.get_all("SB Client", filters={"name": ("like", "Imported " + P + "%")}, pluck="name"):
			frappe.delete_doc("SB Client", c, force=True, ignore_permissions=True)
		frappe.db.delete("SB Invoice Import", {"invoice_number": ("like", P + "%")})
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _run(self, rows):
		out = api.run_import(rows)
		return out, api.import_status(out["data_import"]) if out["data_import"] else None

	def test_template_matches_staging_doctype(self):
		meta = frappe.get_meta("SB Invoice Import")
		self.assertEqual(HEAD.split(","), [meta.get_field(f).label for f, _l in ii.TEMPLATE_COLUMNS])

	def test_values(self):
		self.assertEqual(ii.parse_amount("$1,972.42"), 1972.42)
		self.assertEqual(ii.parse_amount("(25.00)"), -25)
		self.assertEqual(str(ii.parse_date("01/02/2026")), "2026-02-01", "numeric dates are day first")
		self.assertEqual(str(ii.parse_date("Oct 9, 2026")), "2026-10-09")

	def test_create_keeps_number_counter_and_flags(self):
		nxt = frappe.db.get_single_value("SupaBill Settings", "next_invoice_number")
		url = _upload(_csv({**ROW, "invoice_number": P + "101"}), "i.csv")
		rev = api.review_csv(url)
		r = rev["rows"][0]
		self.assertEqual((r["status"], r["action"], r["client"], r["wallet"], r["errors"]), ("new", "create", "Acme Test", "Test Wallet", []))
		out, st = self._run(rev["rows"])
		self.assertEqual((st["status"], st["created"]), ("Success", 1))
		inv = frappe.get_doc("SB Invoice", P + "101")
		self.assertEqual((inv.docstatus, inv.imported, str(inv.invoice_date), inv.grand_total, inv.cbic_rate, inv.amount_inr),
			(1, 1, "2026-04-15", 1000, 85.5, 85500))
		self.assertEqual((inv.received_inr, inv.payment_status, inv.wallet_reference), (85000, "Received", "W-1"))
		self.assertEqual(frappe.db.get_single_value("SupaBill Settings", "next_invoice_number"), nxt)

	def test_existing_number_update_skip_renumber(self):
		name = frappe.get_doc("SB Invoice", frappe.get_all("SB Invoice", filters={"docstatus": 1}, pluck="name", limit=1)[0]).name
		before = frappe.get_doc("SB Invoice", name)
		rows = ii.review(ii.read_csv(_csv({**ROW, "invoice_number": name, "if_exists": "Update", "received_inr": "", "wallet_reference": "NEW-REF"},
			{**ROW, "invoice_number": name}, {**ROW, "invoice_number": name})))["rows"]
		self.assertEqual([r["action"] for r in rows], ["update", "skip", "skip"])
		self.assertTrue(all(any("more than once" in e for e in r["errors"]) for r in rows))
		rows[2].update(action="renumber", invoice_number=P + "102")
		out, st = self._run(rows)
		self.assertEqual((st["updated"], st["created"], out["skipped"]), (1, 1, 1), st)
		after = frappe.get_doc("SB Invoice", name)
		self.assertEqual(after.wallet_reference, "NEW-REF")
		self.assertEqual(after.received_inr, before.received_inr, "blank cells keep current values")
		self.assertEqual(after.grand_total, before.grand_total, "update never touches invoice content")
		self.assertTrue(frappe.db.exists("SB Invoice", P + "102"))

	def test_unresolved_clash_refused(self):
		name = frappe.get_all("SB Invoice", filters={"docstatus": 1}, pluck="name", limit=1)[0]
		rows = ii.review(ii.read_csv(_csv({**ROW, "invoice_number": name})))["rows"]
		rows[0]["action"] = "create"
		with self.assertRaises(frappe.ValidationError):
			api.run_import(rows)

	def test_new_client_created_on_request(self):
		client = "Imported " + P
		rows = ii.review(ii.read_csv(_csv({**ROW, "invoice_number": P + "103", "client": client,
			"client_address": "1 Road, Pune", "client_country": "India"})))["rows"]
		self.assertTrue(rows[0]["new_client"])
		self.assertEqual(rows[0]["client"], "")
		out, st = self._run(rows)
		self.assertEqual(st["created"], 1, st)
		self.assertEqual(frappe.db.get_value("SB Client", client, "country"), "India")

	def test_review_errors(self):
		rows = ii.review(ii.read_csv(_csv({"invoice_number": "X1", "client": "Acme Test", "wallet": "Nope"})))["rows"]
		text = " ".join(rows[0]["errors"])
		for word in ("date", "Amount", "Currency", "wallet"):
			self.assertIn(word, text)

	def test_supabill_pdf_and_docx_roundtrip(self):
		from supabill.api import invoice
		name = invoice.create_invoice(payload(client_request_id=frappe.generate_hash()))["name"]
		doc = frappe.get_doc("SB Invoice", name)
		for ext, render in (("pdf", render_pdf), ("docx", render_docx)):
			v = ii.extract(ii.document_text(render(doc), "a." + ext))["values"]
			self.assertEqual((v["invoice_number"], v["invoice_date"], v["currency"], float(v["amount"]), v["client"]),
				(name, str(doc.invoice_date), "USD", doc.grand_total, doc.client_name), ext)
			self.assertEqual(v["tax_treatment"], "Export under LUT")
		self.assertEqual(ii.match_wallet("", v["bank_details"], ii._wallets()), "Test Wallet")

	def test_files_import_attaches_original_and_downloads_it(self):
		from supabill.api import invoice
		from supabill.api.output import download
		name = invoice.create_invoice(payload(client_request_id=frappe.generate_hash()))["name"]
		pdf = render_pdf(frappe.get_doc("SB Invoice", name))
		url = _upload(pdf, "old.pdf")
		rev = api.review_files([url])
		r = rev["rows"][0]
		self.assertEqual((r["status"], r["action"]), ("exists", "skip"))
		r.update(action="renumber", invoice_number=P + "104")
		out, st = self._run([r])
		self.assertEqual(st["created"], 1, st)
		inv = frappe.get_doc("SB Invoice", P + "104")
		self.assertEqual(inv.original_file, url)
		self.assertTrue(inv.bank_details.startswith("Account Number: 123") or "Account Number" in inv.bank_details)
		download(P + "104", "pdf")
		self.assertEqual(frappe.local.response.filecontent[:4], b"%PDF")
		self.assertTrue(frappe.local.response.filename.startswith("old"))

	def test_other_layout_keywords(self):
		text = """ACME CONSULTING LLC
Invoice #: INV-2041
Date of issue: March 3, 2026
Payment due: April 2, 2026
Bill To:
Globex Corporation
42 Elm Street
Springfield, IL 62701, USA
Description Qty Rate Amount
1 Data migration services 1 2,400.00 2,400.00
Subtotal: $2,400.00
Total: USD 2,400.00
Wire instructions
Account Name: Acme Consulting LLC
Account Number: 9876543210
SWIFT/BIC: CHASUS33"""
		v = ii.extract(text)["values"]
		self.assertEqual((v["invoice_number"], v["invoice_date"], v["due_date"], v["currency"], v["amount"]),
			("INV-2041", "2026-03-03", "2026-04-02", "USD", "2400.00"))
		self.assertEqual((v["client"], v["client_country"], v["description"]), ("Globex Corporation", "United States", "Data migration services"))
		self.assertIn("Account Number: 9876543210", v["bank_details"])

	def test_unreadable_file_reported_not_imported(self):
		url = _upload(b"plain text", "notes.txt")
		rev = api.review_files([url])
		self.assertEqual((rev["rows"], len(rev["unread"])), ([], 1))
		self.assertFalse(frappe.db.exists("File", {"file_url": url}))

	def test_manager_only(self):
		frappe.set_user(make_user("ii.user@example.com", "SupaBill User"))
		for fn, arg in ((api.review_csv, "/private/files/x.csv"), (api.review_files, ["/private/files/x.pdf"]), (api.run_import, [{"action": "skip"}])):
			with self.assertRaises(frappe.PermissionError):
				fn(arg)
