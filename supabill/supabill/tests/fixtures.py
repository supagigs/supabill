"""Shared synthetic test data. Never real client or bank data."""
import frappe

from supabill.supabill.install import ensure_codes, ensure_roles

PREFIX = "TST/26-27/"


def make_user(email, role=None):
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0})
		if role:
			doc.append("roles", {"role": role})
		doc.insert(ignore_permissions=True)
	return email


def setup_basics():
	ensure_roles()
	ensure_codes()
	s = frappe.get_doc("SupaBill Settings")
	s.update({"legal_name": "Test Co", "invoice_prefix": PREFIX, "number_digits": 3,
		"lut_arn": "ARN123", "lut_note": "LUT ARN {ARN}"})
	if not s.next_invoice_number or s.next_invoice_number < 1:
		s.next_invoice_number = 1
	s.flags.ignore_permissions = True
	try:
		s.save()
	except frappe.ValidationError:
		s.next_invoice_number = (frappe.db.count("SB Invoice") or 0) + 100
		s.save()
	if not frappe.db.exists("SB Wallet", "Test Wallet"):
		frappe.get_doc({"doctype": "SB Wallet", "wallet_name": "Test Wallet", "details": [
			{"label": "Account Number", "value": "123"}, {"label": "Bank Name", "value": "Test Bank"}]}).insert()
	if not frappe.db.exists("SB Wallet", "Half Wallet"):
		frappe.get_doc({"doctype": "SB Wallet", "wallet_name": "Half Wallet", "details": [
			{"label": "Account Number", "value": ""}]}).insert()
	if not frappe.db.exists("SB Wallet", "Upwork"):
		frappe.get_doc({"doctype": "SB Wallet", "wallet_name": "Upwork", "is_upwork": 1}).insert()
	if not frappe.db.exists("SB Client", "Acme Test"):
		frappe.get_doc({"doctype": "SB Client", "client_name": "Acme Test", "address": "1 Main St",
			"country": "United States", "currency": "USD", "wallet": "Test Wallet",
			"payment_terms_days": 21, "email": "ap@acme.example", "purpose_code": "P0802"}).insert()
	for d, r in (("2026-10-17", 88.10), ("2026-11-07", 88.45)):
		if not frappe.db.exists("SB CBIC Rate", f"USD-{d}"):
			frappe.get_doc({"doctype": "SB CBIC Rate", "currency": "USD", "effective_from": d,
				"export_rate": r, "source": "Manual"}).insert()


def payload(**kw):
	p = {"client": "Acme Test", "invoice_date": "2026-11-10", "currency": "USD",
		"tax_treatment": "Export under LUT", "milestone": "Milestone 1 of 2", "billing_period": "Nov 2026",
		"items": [{"description": "Work", "qty": 1, "rate": 1000, "sac_code": "998313"}]}
	p.update(kw)
	return p
