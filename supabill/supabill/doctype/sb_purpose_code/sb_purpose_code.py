from frappe.model.document import Document


class SBPurposeCode(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
