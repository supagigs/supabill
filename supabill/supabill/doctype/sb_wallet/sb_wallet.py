import frappe
from frappe import _
from frappe.model.document import Document


class SBWallet(Document):
	def validate(self):
		labels = [(d.label or "").strip().lower() for d in self.details]
		if len(labels) != len(set(labels)):
			frappe.throw(_("Each bank detail label can appear only once"))

	@property
	def is_complete(self) -> bool:
		return bool(self.is_upwork) or (bool(self.details) and all((d.value or "").strip() for d in self.details))
