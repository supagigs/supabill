"""Setup screens: clients, wallets, settings, codes and CBIC rates."""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from supabill.api.session import user_access
from supabill.supabill import calc

CLIENT_FIELDS = (
	"client_name", "contact_person", "email", "address", "country", "project", "currency",
	"payment_terms_days", "tax_treatment", "wallet", "payment_method", "purpose_code", "sac_code", "hsn_code",
	"last_milestone", "last_billing_period", "last_amount", "disabled",
)
SETTINGS_FIELDS = (
	"legal_name", "display_name", "company_address", "company_email", "company_phone", "gstin", "pan", "iec",
	"invoice_prefix", "next_invoice_number", "number_digits", "default_currency", "default_terms_days",
	"country_of_supply", "default_cbic_rate", "default_sac", "default_hsn", "default_purpose_code",
	"lut_arn", "lut_note", "ad_bank_name", "ad_code", "ad_branch_address", "signatory_name",
	"signatory_designation", "signatory_place", "realisation_months", "excel_enabled", "ms_tenant_id", "ms_client_id",
	"workbook_share_link", "worksheet_name", "table_name", "pull_interval_minutes", "cbic_provider",
)
SECRETS = ("ms_client_secret", "allratestoday_api_key")
READ_ONLY = ("excel_last_push", "excel_last_pull", "cbic_last_sync", "cbic_last_status")


def _need(manager=False):
	a = user_access()
	if not a["has_access"] or (manager and not a["is_manager"]):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _load(v):
	return json.loads(v) if isinstance(v, str) else (v or {})


# ---------- clients ----------
@frappe.whitelist()
def list_clients(search: str | None = None, include_disabled: int = 1) -> list[dict]:
	_need()
	filters = {} if cint(include_disabled) else {"disabled": 0}
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"client_name": ("like", like), "contact_person": ("like", like), "project": ("like", like)}
	rows = frappe.get_list("SB Client", filters=filters, or_filters=or_filters, fields=["name", *CLIENT_FIELDS],
		order_by="client_name asc", limit_page_length=1000)
	stats = frappe.db.sql(
		"""select client, count(*) n, sum(amount_inr) inr from `tabSB Invoice` where docstatus = 1 group by client""",
		as_dict=True)
	by = {s.client: s for s in stats}
	for r in rows:
		s = by.get(r.name)
		r["invoice_count"] = s.n if s else 0
		r["billed_inr"] = flt(s.inr, 2) if s else 0
	return rows


@frappe.whitelist(methods=["POST"])
def save_client(values, name: str | None = None) -> dict:
	_need()
	v = {k: val for k, val in _load(values).items() if k in CLIENT_FIELDS}
	new_name = (v.get("client_name") or "").strip()
	if not new_name:
		frappe.throw(_("Client name is required"))
	if name:
		doc = frappe.get_doc("SB Client", name)
		doc.check_permission("write")
		if new_name != name:
			if frappe.db.exists("SB Client", new_name):
				frappe.throw(_("A client called {0} already exists").format(new_name))
			frappe.rename_doc("SB Client", name, new_name)
			doc = frappe.get_doc("SB Client", new_name)
		doc.update(v)
		doc.save()
	else:
		if frappe.db.exists("SB Client", new_name):
			frappe.throw(_("A client called {0} already exists").format(new_name))
		doc = frappe.get_doc({"doctype": "SB Client", **v})
		doc.insert()
	return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def delete_client(name: str) -> dict:
	_need(manager=True)
	if frappe.db.exists("SB Invoice", {"client": name}):
		frappe.throw(_("{0} has invoices, so it can only be disabled, not deleted").format(name))
	frappe.delete_doc("SB Client", name)
	return {"deleted": name}


# ---------- wallets ----------
@frappe.whitelist()
def list_wallets() -> list[dict]:
	_need()
	out = []
	for w in frappe.get_all("SB Wallet", fields=["name", "wallet_name", "is_upwork", "settles_to", "disabled"],
			order_by="wallet_name asc"):
		w["details"] = frappe.get_all("SB Wallet Detail", filters={"parent": w.name, "parenttype": "SB Wallet"},
			fields=["label", "value"], order_by="idx asc")
		w["complete"] = bool(w.is_upwork) or (bool(w["details"]) and all((d.value or "").strip() for d in w["details"]))
		w["invoice_count"] = frappe.db.count("SB Invoice", {"wallet": w.name, "docstatus": 1})
		out.append(w)
	return out


@frappe.whitelist(methods=["POST"])
def save_wallet(values, name: str | None = None) -> dict:
	_need(manager=True)
	v = _load(values)
	new_name = (v.get("wallet_name") or "").strip()
	if not new_name:
		frappe.throw(_("Wallet name is required"))
	details = [{"label": (d.get("label") or "").strip(), "value": (d.get("value") or "").strip()}
		for d in v.get("details") or [] if (d.get("label") or "").strip()]
	if name:
		if new_name != name:
			if frappe.db.exists("SB Wallet", new_name):
				frappe.throw(_("A wallet called {0} already exists").format(new_name))
			frappe.rename_doc("SB Wallet", name, new_name)
		doc = frappe.get_doc("SB Wallet", new_name)
	else:
		if frappe.db.exists("SB Wallet", new_name):
			frappe.throw(_("A wallet called {0} already exists").format(new_name))
		doc = frappe.new_doc("SB Wallet")
		doc.wallet_name = new_name
	doc.update({k: v.get(k) for k in ("is_upwork", "settles_to", "disabled") if k in v})
	doc.set("details", details)
	doc.save()
	return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def delete_wallet(name: str) -> dict:
	_need(manager=True)
	if frappe.db.exists("SB Invoice", {"wallet": name}) or frappe.db.exists("SB Client", {"wallet": name}):
		frappe.throw(_("{0} is used by invoices or clients, so it can only be disabled").format(name))
	frappe.delete_doc("SB Wallet", name)
	return {"deleted": name}


# ---------- settings ----------
@frappe.whitelist()
def get_settings() -> dict:
	_need(manager=True)
	s = frappe.get_doc("SupaBill Settings")
	data = {k: s.get(k) for k in SETTINGS_FIELDS + READ_ONLY}
	for k in SECRETS:
		data[f"has_{k}"] = bool(s.get_password(k, raise_exception=False))
	data["next_invoice_preview"] = calc.format_invoice_number(s.invoice_prefix, s.next_invoice_number, s.number_digits)
	from supabill.api.output import pdf_engine
	data["pdf_engine"] = pdf_engine()
	return data


@frappe.whitelist(methods=["POST"])
def save_settings(values, secrets=None, clear_secrets=None) -> dict:
	"""Secrets are write-only: send a new value to replace, or name it in clear_secrets to remove."""
	_need(manager=True)
	s = frappe.get_doc("SupaBill Settings")
	s.update({k: v for k, v in _load(values).items() if k in SETTINGS_FIELDS})
	for k, v in _load(secrets).items():
		if k in SECRETS and (v or "").strip():
			s.set(k, v.strip())
	for k in (json.loads(clear_secrets) if isinstance(clear_secrets, str) else clear_secrets) or []:
		if k in SECRETS:
			s.set(k, "")
	s.save()
	frappe.clear_document_cache("SupaBill Settings", "SupaBill Settings")
	return get_settings()


# ---------- codes ----------
@frappe.whitelist()
def list_codes() -> dict:
	_need()
	return {
		"tax_codes": frappe.get_all("SB Tax Code", fields=["name", "code_type", "code", "description", "is_favourite"],
			order_by="code_type asc, is_favourite desc, code asc"),
		"purpose_codes": frappe.get_all("SB Purpose Code", fields=["name", "code", "description", "is_favourite"],
			order_by="is_favourite desc, code asc"),
	}


@frappe.whitelist(methods=["POST"])
def save_code(kind: str, code: str, description: str = "", code_type: str = "SAC", is_favourite: int = 1) -> dict:
	_need(manager=True)
	doctype = {"tax": "SB Tax Code", "purpose": "SB Purpose Code"}.get(kind)
	if not doctype:
		frappe.throw(_("Unknown code kind"))
	key = f"{code_type}-{code.strip()}" if kind == "tax" else code.strip().upper()
	if frappe.db.exists(doctype, key):
		doc = frappe.get_doc(doctype, key)
		doc.update({"description": description, "is_favourite": cint(is_favourite)})
		doc.save()
	else:
		data = {"doctype": doctype, "code": code, "description": description, "is_favourite": cint(is_favourite)}
		if kind == "tax":
			data["code_type"] = code_type
		doc = frappe.get_doc(data).insert()
	return list_codes()


@frappe.whitelist(methods=["POST"])
def toggle_favourite(kind: str, name: str) -> dict:
	_need(manager=True)
	doctype = {"tax": "SB Tax Code", "purpose": "SB Purpose Code"}[kind]
	doc = frappe.get_doc(doctype, name)
	doc.is_favourite = 0 if doc.is_favourite else 1
	doc.save()
	return list_codes()


@frappe.whitelist(methods=["POST"])
def delete_code(kind: str, name: str) -> dict:
	_need(manager=True)
	doctype = {"tax": "SB Tax Code", "purpose": "SB Purpose Code"}[kind]
	frappe.delete_doc(doctype, name)
	return list_codes()


# ---------- CBIC rates ----------
@frappe.whitelist()
def list_cbic_rates(limit: int = 200) -> list[dict]:
	_need()
	return frappe.get_all("SB CBIC Rate", fields=["name", "effective_from", "currency", "export_rate", "import_rate", "source"],
		order_by="effective_from desc, currency asc", limit_page_length=cint(limit))


@frappe.whitelist(methods=["POST"])
def save_cbic_rate(effective_from: str, currency: str, export_rate: float, import_rate: float | None = None) -> list[dict]:
	_need(manager=True)
	name = f"{currency}-{effective_from}"
	if frappe.db.exists("SB CBIC Rate", name):
		doc = frappe.get_doc("SB CBIC Rate", name)
	else:
		doc = frappe.new_doc("SB CBIC Rate")
		doc.update({"effective_from": effective_from, "currency": currency})
	doc.update({"export_rate": flt(export_rate, 4), "import_rate": flt(import_rate, 4) if import_rate else None,
		"source": "Manual"})
	doc.save()
	return list_cbic_rates()


@frappe.whitelist(methods=["POST"])
def delete_cbic_rate(name: str) -> list[dict]:
	_need(manager=True)
	frappe.delete_doc("SB CBIC Rate", name)
	return list_cbic_rates()
