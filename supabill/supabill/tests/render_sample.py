"""Writes PDF and DOCX for one invoice to a folder. bench execute ...render_sample.run --kwargs '{"name":..,"out":..}'"""
import os

import frappe

from supabill.api.output import file_name, render_docx, render_pdf


def run(name, out):
	doc = frappe.get_doc("SB Invoice", name)
	for ext, fn in (("pdf", render_pdf), ("docx", render_docx)):
		path = os.path.join(out, file_name(doc, ext))
		with open(path, "wb") as fh:
			fh.write(fn(doc))
		print(path)


def run_html(name, out):
	"""HTML fallback only, for comparing layouts."""
	from frappe.utils.pdf import get_pdf

	from supabill.api.output import render_html
	doc = frappe.get_doc("SB Invoice", name)
	path = os.path.join(out, "html-fallback.pdf")
	with open(path, "wb") as fh:
		fh.write(get_pdf(render_html(doc), {"page-size": "A4", "margin-top": "14mm", "margin-bottom": "14mm",
			"margin-left": "14mm", "margin-right": "14mm", "disable-smart-shrinking": ""}))
	print(path)
