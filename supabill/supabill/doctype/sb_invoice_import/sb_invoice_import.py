from frappe.model.document import Document

from supabill.supabill.invoice_import import apply_row


class SBInvoiceImport(Document):
	"""One imported invoice row. Inserting it (normally through Data Import) creates, updates or skips the invoice."""

	def before_insert(self):
		apply_row(self)
