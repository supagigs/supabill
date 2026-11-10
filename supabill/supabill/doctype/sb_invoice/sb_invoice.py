import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, today

from supabill.supabill import calc

REGISTER_FIELDS = (
	"register_description", "wallet_reference", "upwork_invoice", "upwork_account_holder",
	"invoice_status", "received_inr", "bank_charges_usd", "bank_charges_inr", "payment_status",
)


class SBInvoice(Document):
	def autoname(self):
		self.name = next_invoice_name()

	def validate(self):
		self.fill_from_client()
		self.due_date = add_days(self.invoice_date, cint(self.payment_terms_days))
		self.gst_return_period = calc.gst_return_period(self.invoice_date)
		for it in self.items:
			it.currency = self.currency
		self.update(calc.compute_lines(self.items, self.tax_treatment))
		self.set_cbic_rate()
		self.amount_inr = flt(self.grand_total * flt(self.cbic_rate), 2)
		self.snapshot_bank_details()
		if not self.notes and self.tax_treatment == "Export under LUT":
			s = frappe.get_cached_doc("SupaBill Settings")
			self.notes = (s.lut_note or "").replace("{ARN}", s.lut_arn or "")
		self.country_of_supply = self.country_of_supply or frappe.db.get_single_value(
			"SupaBill Settings", "country_of_supply")
		self.apply_register_rules()
		self.check_ready()

	def before_update_after_submit(self):
		self.apply_register_rules()

	def on_submit(self):
		first = self.items[0] if self.items else None
		frappe.db.set_value("SB Client", self.client, {
			"last_milestone": self.milestone,
			"last_billing_period": self.billing_period,
			"last_amount": first.rate if first else 0,
		}, update_modified=False)
		self.db_set("excel_sync_status", "Queued")
		frappe.enqueue("supabill.api.output.attach_files", name=self.name, queue="short", enqueue_after_commit=True)

	def on_cancel(self):
		self.db_set("invoice_status", "Cancelled")

	# ----- helpers -----
	def fill_from_client(self):
		c = frappe.get_cached_doc("SB Client", self.client)
		defaults = {
			"client_name": c.client_name, "billing_address": c.address, "client_country": c.country,
			"attention": c.contact_person, "client_email": c.email, "project": c.project,
			"wallet": c.wallet, "payment_method": c.payment_method, "purpose_code": c.purpose_code,
		}
		for field, value in defaults.items():
			if not self.get(field) and value:
				self.set(field, value)

	def set_cbic_rate(self):
		if self.currency == "INR":
			self.cbic_rate, self.cbic_rate_source, self.cbic_rate_effective_from = 1, "Auto", None
			return
		if self.cbic_rate_source == "Manual" and flt(self.cbic_rate) > 0:
			self.cbic_rate_effective_from = None
			return
		rate, effective = calc.cbic_rate_for(self.invoice_date, self.currency)
		if rate:
			self.cbic_rate, self.cbic_rate_effective_from, self.cbic_rate_source = rate, effective, "Auto"

	def snapshot_bank_details(self):
		if self.docstatus or not self.wallet:
			return
		w = frappe.get_cached_doc("SB Wallet", self.wallet)
		self.bank_details = "\n".join(f"{d.label}: {d.value or ''}" for d in w.details)

	def apply_register_rules(self):
		self.payment_status = calc.derive_payment_status(
			self.payment_status or "Pending", self.received_inr, self.amount_inr)
		r = calc.register_calcs(self.amount_inr, self.received_inr, self.bank_charges_inr)
		self.forex_gain, self.net_received = r["forex_gain"], r["net_received"]

	def check_ready(self):
		blocking = [m for level, m in readiness(self) if level == "error"]
		if blocking:
			frappe.throw(_("Fix before saving: {0}").format(", ".join(blocking)), title=_("Invoice not ready"))


def readiness(doc) -> list[tuple[str, str]]:
	"""(level, message) pairs. 'error' blocks saving, 'warning' is shown but allowed."""
	out = []
	err = lambda m: out.append(("error", m))  # noqa: E731
	warn = lambda m: out.append(("warning", m))  # noqa: E731
	if not doc.client:
		err(_("Client"))
	if not (doc.billing_address or "").strip():
		err(_("Client billing address"))
	if flt(doc.grand_total) <= 0:
		err(_("Amount greater than zero"))
	if not doc.invoice_date:
		err(_("Invoice date"))
	if doc.currency != "INR" and flt(doc.cbic_rate) <= 0:
		err(_("CBIC exchange rate for {0} on {1}").format(doc.currency, doc.invoice_date))
	if not doc.wallet:
		err(_("Wallet"))
	else:
		w = frappe.get_cached_doc("SB Wallet", doc.wallet)
		if not w.is_upwork and (not w.details or any(not (d.value or "").strip() for d in w.details)):
			err(_("Bank details for wallet {0}").format(doc.wallet))
		if doc.wallet == "Others" and not (doc.wallet_name_other or "").strip():
			warn(_("Name of the wallet for 'Others'"))
		if not w.is_upwork and not (doc.wallet_reference or "").strip():
			warn(_("Wallet reference no. (can be added later in the register)"))
	if not (doc.client_email or "").strip():
		warn(_("Client email"))
	if not (doc.billing_period or "").strip():
		warn(_("Billing period"))
	if doc.tax_treatment == "Export under LUT" and not doc.purpose_code:
		warn(_("Purpose code"))
	if not doc.client_country:
		warn(_("Client country"))
	return out


def next_invoice_name() -> str:
	"""Takes the next number under a row lock so two users never get the same number."""
	s = frappe.qb.DocType("Singles")
	settings = frappe.get_doc("SupaBill Settings")
	row = (
		frappe.qb.from_(s).select(s.value)
		.where((s.doctype == "SupaBill Settings") & (s.field == "next_invoice_number"))
		.for_update().run()
	)
	number = cint(row[0][0]) if row else cint(settings.next_invoice_number) or 1
	while True:
		name = calc.format_invoice_number(settings.invoice_prefix, number, settings.number_digits)
		if not frappe.db.exists("SB Invoice", name):
			break
		number += 1
	frappe.db.set_single_value("SupaBill Settings", "next_invoice_number", number + 1)
	return name
