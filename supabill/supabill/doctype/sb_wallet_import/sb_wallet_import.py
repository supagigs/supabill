from frappe.model.document import Document

from supabill.supabill.wallet_import import apply_row


class SBWalletImport(Document):
	"""One imported wallet row. Inserting it (normally through Data Import) creates, updates or skips the wallet."""

	def before_insert(self):
		apply_row(self)
