import frappe
from frappe import _
from frappe.model.document import Document


class SBTaxCode(Document):
	def validate(self):
		self.code = (self.code or "").strip()
		if not self.code.isdigit():
			frappe.throw(_("{0} code must contain digits only").format(self.code_type))
