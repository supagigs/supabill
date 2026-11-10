import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from supabill.supabill.calc import format_invoice_number


class SupaBillSettings(Document):
	def validate(self):
		if not (self.invoice_prefix or "").strip():
			frappe.throw(_("Invoice prefix is required"))
		if cint(self.next_invoice_number) < 1:
			frappe.throw(_("Next number must be 1 or more"))
		if not 1 <= cint(self.number_digits) <= 6:
			frappe.throw(_("Digits must be between 1 and 6"))
		nxt = format_invoice_number(self.invoice_prefix, self.next_invoice_number, self.number_digits)
		if frappe.db.exists("SB Invoice", nxt):
			frappe.throw(_("Invoice {0} already exists, so the next number must be higher").format(nxt))
		if cint(self.pull_interval_minutes) and cint(self.pull_interval_minutes) < 1:
			frappe.throw(_("Pull interval must be at least 1 minute"))

	@property
	def next_invoice_preview(self) -> str:
		return format_invoice_number(self.invoice_prefix, self.next_invoice_number, self.number_digits)
