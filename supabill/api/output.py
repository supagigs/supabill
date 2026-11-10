"""Invoice PDF and DOCX output. Both are rendered from the saved invoice on request."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate

from supabill.api.session import user_access

SYM = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "AUD": "A$", "CAD": "C$"}
TEMPLATE_DOCX = os.path.join(os.path.dirname(__file__), "..", "templates", "docx", "invoice_template.docx")


def money(value, currency) -> str:
	return f"{SYM.get(currency, (currency or '') + ' ')}{flt(value):,.2f}"


def _date(d) -> str:
	return formatdate(d, "d MMM yyyy") if d else ""


def context(doc) -> dict:
	s = frappe.get_cached_doc("SupaBill Settings")
	cur = doc.currency
	lut = doc.tax_treatment == "Export under LUT"
	tax_label = {"Export under LUT": "Tax Payable", "IGST 18%": "IGST 18%", "CGST + SGST 9%": "CGST 9% + SGST 9%"}
	bank = []
	for line in (doc.bank_details or "").splitlines():
		label, _sep, value = line.partition(":")
		if label.strip():
			bank.append({"label": label.strip(), "value": value.strip()})
	items = []
	for i, it in enumerate(doc.items, 1):
		codes = it.sac_code or ""
		if it.hsn_code:
			codes = f"{codes} / HSN {it.hsn_code}" if codes else f"HSN {it.hsn_code}"
		items.append({
			"idx": i, "description": it.description, "sac": it.sac_code or "", "hsn": it.hsn_code or "",
			"codes": codes, "rate": money(it.rate, cur), "qty": f"{flt(it.qty):g}",
			"tax": money(it.tax_amount, cur), "amount": money(it.amount, cur),
		})
	milestone_line = doc.milestone or ""
	if doc.billing_period:
		milestone_line = f"{milestone_line} – Billing period: {doc.billing_period}" if milestone_line else f"Billing period: {doc.billing_period}"
	return {
		"doc": doc, "name": doc.name, "title": "INVOICE" if lut else "TAX INVOICE", "is_lut": lut,
		"legal_name": s.legal_name or "", "display_name": s.display_name or s.legal_name or "",
		"company_address": s.company_address or "", "company_email": s.company_email or "",
		"company_phone": s.company_phone or "", "gstin": s.gstin or "", "pan": s.pan or "", "iec": s.iec or "",
		"invoice_date": _date(doc.invoice_date), "due_date": _date(doc.due_date),
		"country_of_supply": doc.country_of_supply or "", "purpose_code": doc.purpose_code or "", "currency": cur,
		"client_name": doc.client_name or "", "billing_address": doc.billing_address or "",
		"attention": doc.attention or "", "client_email": doc.client_email or "", "project": doc.project or "",
		"milestone_line": milestone_line,
		"payment_terms": f"Payable by {_date(doc.due_date)}" if cint(doc.payment_terms_days) else "Due on receipt",
		"payment_method": doc.payment_method or "", "items": items, "has_hsn": any(i["hsn"] for i in items),
		"subtotal": money(doc.subtotal, cur), "tax_label": tax_label.get(doc.tax_treatment, "Tax"),
		"tax_total": money(doc.tax_total, cur), "tax_half": money(flt(doc.tax_total) / 2, cur),
		"split_tax": doc.tax_treatment == "CGST + SGST 9%", "grand_total": money(doc.grand_total, cur),
		"notes": doc.notes or "", "bank": bank, "cancelled": doc.docstatus == 2,
	}


def render_html(doc) -> str:
	return frappe.render_template("supabill/templates/print/invoice.html", context(doc))


def render_pdf(doc) -> bytes:
	"""PDF from the DOCX template via LibreOffice when installed (identical layout), else from HTML."""
	pdf = _docx_to_pdf(render_docx(doc))
	if pdf:
		return pdf
	from frappe.utils.pdf import get_pdf
	return get_pdf(render_html(doc), {"page-size": "A4", "margin-top": "14mm", "margin-bottom": "14mm",
		"margin-left": "14mm", "margin-right": "14mm", "zoom": "1.25"})


def pdf_engine() -> str:
	return "LibreOffice (from the DOCX template)" if shutil.which("soffice") else "HTML (wkhtmltopdf)"


def _docx_to_pdf(data: bytes) -> bytes | None:
	soffice = shutil.which("soffice")
	if not soffice:
		return None
	with tempfile.TemporaryDirectory(prefix="supabill-") as tmp:
		src = os.path.join(tmp, "invoice.docx")
		with open(src, "wb") as fh:
			fh.write(data)
		# A private profile per call so parallel conversions never share a lock.
		profile = "file://" + os.path.join(tmp, "profile")
		try:
			subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless", "--norestore",
				"--convert-to", "pdf", "--outdir", tmp, src], check=True, timeout=90,
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			with open(os.path.join(tmp, "invoice.pdf"), "rb") as fh:
				return fh.read()
		except (subprocess.SubprocessError, OSError):
			frappe.log_error("SupaBill: LibreOffice PDF conversion failed, used HTML instead")
			return None


def render_docx(doc) -> bytes:
	from docxtpl import DocxTemplate, Listing
	ctx = context(doc)
	for key in ("company_address", "billing_address", "notes"):
		ctx[key] = Listing(ctx[key])
	ctx.pop("doc")
	tpl = DocxTemplate(TEMPLATE_DOCX)
	tpl.render(ctx, autoescape=True)
	buf = io.BytesIO()
	tpl.save(buf)
	return buf.getvalue()


def file_name(doc, ext: str) -> str:
	safe = doc.name.replace("/", "-")
	client = "".join(ch for ch in (doc.client_name or "") if ch.isalnum() or ch in " -_").strip().replace(" ", "_")
	return f"{safe}_{client}.{ext}" if client else f"{safe}.{ext}"


@frappe.whitelist()
def download(name: str, fmt: str = "pdf"):
	"""Streams the invoice as PDF or DOCX. Needs read permission on the invoice."""
	if not user_access()["has_access"]:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	doc = frappe.get_doc("SB Invoice", name)
	doc.check_permission("read")
	if fmt not in ("pdf", "docx"):
		frappe.throw(_("Format must be pdf or docx"))
	if doc.imported and doc.original_file and doc.original_file.lower().endswith("." + fmt):
		# an imported invoice downloads as the file it was imported from
		f = frappe.get_doc("File", {"file_url": doc.original_file})
		frappe.local.response.filename = f.file_name
		frappe.local.response.filecontent = f.get_content()
		frappe.local.response.type = "download"
		return
	data = render_pdf(doc) if fmt == "pdf" else render_docx(doc)
	frappe.local.response.filename = file_name(doc, fmt)
	frappe.local.response.filecontent = data
	frappe.local.response.type = "download"


def attach_files(name: str):
	"""Background job after submit: saves PDF and DOCX copies on the invoice (private files)."""
	doc = frappe.get_doc("SB Invoice", name)
	for ext, render in (("pdf", render_pdf), ("docx", render_docx)):
		fname = file_name(doc, ext)
		for old in frappe.get_all("File", filters={"attached_to_doctype": "SB Invoice", "attached_to_name": name,
				"file_name": fname}, pluck="name"):
			frappe.delete_doc("File", old, ignore_permissions=True)
		frappe.get_doc({"doctype": "File", "file_name": fname, "attached_to_doctype": "SB Invoice",
			"attached_to_name": name, "is_private": 1, "content": render(doc)}).insert(ignore_permissions=True)
