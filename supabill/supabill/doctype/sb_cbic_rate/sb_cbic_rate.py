import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SBCBICRate(Document):
	def validate(self):
		if self.currency == "INR":
			frappe.throw(_("INR needs no exchange rate"))
		if flt(self.export_rate) <= 0:
			frappe.throw(_("Export rate must be greater than zero"))
		if self.import_rate is not None and flt(self.import_rate) < 0:
			frappe.throw(_("Import rate cannot be negative"))
