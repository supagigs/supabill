"""Install-time setup: roles and standard public codes only. No company data."""
import frappe

ROLES = ("SupaBill User", "SupaBill Manager")

PURPOSE_CODES = [
	("P1005", "Accounting, auditing, bookkeeping & tax consulting", 1),
	("P0802", "Software consultancy / implementation", 1),
	("P0807", "Off-site software exports", 0),
	("P0803", "Database, data processing charges", 0),
	("P0806", "Other information services", 0),
	("P1006", "Business & management consultancy, PR", 0),
	("P1007", "Research & development services", 0),
	("P1008", "Architectural, engineering & technical services", 0),
	("P1099", "Other services not elsewhere included", 0),
]

TAX_CODES = [
	("SAC", "998313", "IT consulting & support services", 1),
	("SAC", "998222", "Accounting & bookkeeping services", 1),
	("SAC", "998314", "IT design & development services", 0),
	("SAC", "998311", "Management consulting services", 0),
]

SETTINGS_DEFAULTS = {
	"legal_name": "Your Company Pvt. Ltd.",
	"invoice_prefix": "INV/",
	"next_invoice_number": 1,
	"number_digits": 3,
	"default_currency": "USD",
	"default_terms_days": 21,
	"country_of_supply": "India",
	"default_sac": "998313",
	"lut_note": "Supply meant for Export under Letter of Undertaking (ARN. {ARN}) without payment of "
	"Integrated Tax. Whether the tax is payable on the reverse charge basis – No",
}


def after_install():
	ensure_roles()
	ensure_codes()
	ensure_settings()
	frappe.db.commit()


def after_migrate():
	ensure_roles()


def ensure_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_codes():
	for code, desc, fav in PURPOSE_CODES:
		if not frappe.db.exists("SB Purpose Code", code):
			frappe.get_doc({"doctype": "SB Purpose Code", "code": code, "description": desc,
				"is_favourite": fav}).insert(ignore_permissions=True)
	for ctype, code, desc, fav in TAX_CODES:
		if not frappe.db.exists("SB Tax Code", f"{ctype}-{code}"):
			frappe.get_doc({"doctype": "SB Tax Code", "code_type": ctype, "code": code,
				"description": desc, "is_favourite": fav}).insert(ignore_permissions=True)


def ensure_settings():
	s = frappe.get_doc("SupaBill Settings")
	for field, value in SETTINGS_DEFAULTS.items():
		if not s.get(field):
			s.set(field, value)
	if not s.default_purpose_code and frappe.db.exists("SB Purpose Code", "P0802"):
		s.default_purpose_code = "P0802"
	s.flags.ignore_permissions = True
	s.save()
