import frappe
from frappe.model.document import Document


class SBClient(Document):
	def validate(self):
		self.client_name = (self.client_name or "").strip()
		if self.email:
			self.email = self.email.strip().lower()
