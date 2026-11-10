import io
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from supabill.api import invoice as api
from supabill.api import output
from supabill.supabill.tests.fixtures import make_user, payload, setup_basics


def docx_text(data: bytes) -> str:
	from docx import Document
	d = Document(io.BytesIO(data))
	parts = [p.text for p in d.paragraphs]
	for t in d.tables:
		for row in t.rows:
			for cell in row.cells:
				parts.append(cell.text)
				for nt in cell.tables:
					for r2 in nt.rows:
						parts.extend(c.text for c in r2.cells)
	for s in d.sections:
		parts.extend(p.text for p in s.footer.paragraphs)
	return "\n".join(parts)


class TestOutput(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_basics()
		cls.user = make_user("out.user@example.com", "SupaBill User")
		cls.stranger = make_user("out.none@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def make(self, **kw):
		r = api.create_invoice(payload(**kw), request_id=frappe.generate_hash())
		return frappe.get_doc("SB Invoice", r["name"])

	def test_docx_has_values_and_no_tags(self):
		doc = self.make(items=[{"description": "Build", "qty": 2, "rate": 500, "sac_code": "998313"},
			{"description": "Support", "qty": 1, "rate": 250, "sac_code": "998313", "hsn_code": "8471"}])
		text = docx_text(output.render_docx(doc))
		for expected in (doc.name, "Acme Test", "1 Main St", "$1,250.00", "Build", "Support", "998313 / HSN 8471",
				"Account Number:", "123", "LUT ARN ARN123", "Test Co", "Total Due (USD)"):
			self.assertIn(expected, text)
		self.assertNotIn("{{", text)
		self.assertNotIn("{%", text)
		self.assertNotIn("Supa/26-27/027", text)  # the sample invoice number the template was made from
		self.assertNotIn("python-docx", text)

	def test_tax_labels(self):
		c = output.context(self.make(tax_treatment="CGST + SGST 9%"))
		self.assertEqual((c["title"], c["split_tax"], c["tax_half"]), ("TAX INVOICE", True, "$90.00"))
		c = output.context(self.make(tax_treatment="IGST 18%"))
		self.assertEqual((c["tax_label"], c["tax_total"], c["is_lut"]), ("IGST 18%", "$180.00", False))

	def test_pdf_both_engines(self):
		doc = self.make()
		self.assertTrue(output.render_pdf(doc).startswith(b"%PDF"))
		with patch("supabill.api.output._docx_to_pdf", return_value=None):
			self.assertTrue(output.render_pdf(doc).startswith(b"%PDF"))  # HTML fallback
		html = output.render_html(doc)
		self.assertIn(doc.name, html)
		self.assertIn("Bank Name:", html)

	def test_download_permissions(self):
		doc = self.make()
		frappe.set_user(self.user)
		output.download(doc.name, "docx")
		self.assertTrue(frappe.local.response.filename.endswith(".docx"))
		with self.assertRaises(frappe.ValidationError):
			output.download(doc.name, "exe")
		frappe.set_user(self.stranger)
		with self.assertRaises(frappe.PermissionError):
			output.download(doc.name, "pdf")

	def test_attach_files(self):
		doc = self.make()
		output.attach_files(doc.name)
		output.attach_files(doc.name)  # running twice replaces, never duplicates
		files = frappe.get_all("File", filters={"attached_to_doctype": "SB Invoice", "attached_to_name": doc.name},
			fields=["file_name", "is_private"])
		self.assertEqual(sorted(f.file_name.rsplit(".", 1)[1] for f in files), ["docx", "pdf"])
		self.assertTrue(all(f.is_private for f in files))

	def test_html_is_escaped(self):
		frappe.db.set_value("SB Client", "Acme Test", "client_name", "Acme Test")
		doc = self.make(billing_address='<img src="file:///etc/passwd">\nLine 2', notes="<script>x()</script>")
		html = output.render_html(doc)
		self.assertNotIn('<img src="file:///etc/passwd">', html)
		self.assertNotIn("<script>x()</script>", html)
		self.assertIn("&lt;img", html)
		self.assertIn("<br>Line 2", html)
