"""Whitelisted invoice API used by the SupaBill Vue app."""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from supabill.api.session import user_access
from supabill.supabill import calc
from supabill.supabill.doctype.sb_invoice.sb_invoice import REGISTER_FIELDS, readiness

INPUT_FIELDS = (
	"client", "client_name", "attention", "client_email", "billing_address", "client_country",
	"project", "milestone", "billing_period", "invoice_date", "payment_terms_days",
	"currency", "wallet", "wallet_name_other", "payment_method", "tax_treatment", "purpose_code",
	"country_of_supply", "cbic_rate", "cbic_rate_source", "notes",
	"register_description", "wallet_reference", "upwork_invoice", "upwork_account_holder", "invoice_status",
)
ITEM_FIELDS = ("description", "sac_code", "hsn_code", "qty", "rate")
LIST_FIELDS = (
	"name", "client", "client_name", "invoice_date", "due_date", "currency", "grand_total", "cbic_rate",
	"amount_inr", "wallet", "wallet_name_other", "gst_return_period", "register_description",
	"wallet_reference", "upwork_invoice", "upwork_account_holder", "received_inr", "bank_charges_usd",
	"bank_charges_inr", "forex_gain", "net_received", "payment_status", "invoice_status",
	"excel_sync_status", "excel_row", "docstatus", "tax_treatment", "purpose_code",
)


def _require_access(manager: bool = False):
	a = user_access()
	if not a["has_access"] or (manager and not a["is_manager"]):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _load(payload) -> dict:
	if isinstance(payload, str):
		payload = json.loads(payload or "{}")
	return payload or {}


def _build(payload: dict):
	data = {k: payload.get(k) for k in INPUT_FIELDS if payload.get(k) not in (None, "")}
	doc = frappe.new_doc("SB Invoice")
	doc.update(data)
	for row in payload.get("items") or []:
		doc.append("items", {k: row.get(k) for k in ITEM_FIELDS})
	return doc


@frappe.whitelist()
def bootstrap() -> dict:
	"""Everything the invoice screen needs in one call. Secrets are never included."""
	_require_access()
	s = frappe.get_cached_doc("SupaBill Settings")
	settings = {
		k: s.get(k) for k in (
			"legal_name", "display_name", "company_address", "company_email", "company_phone", "gstin",
			"pan", "iec", "invoice_prefix", "next_invoice_number", "number_digits", "default_currency",
			"default_terms_days", "country_of_supply", "default_sac", "default_hsn", "default_purpose_code",
			"lut_arn", "lut_note", "worksheet_name", "excel_enabled",
		)
	}
	settings["next_invoice_preview"] = calc.format_invoice_number(
		s.invoice_prefix, s.next_invoice_number, s.number_digits)
	wallets = []
	for w in frappe.get_all("SB Wallet", filters={"disabled": 0}, fields=["name", "is_upwork", "settles_to"],
			order_by="wallet_name asc"):
		details = frappe.get_all("SB Wallet Detail", filters={"parent": w.name, "parenttype": "SB Wallet"},
			fields=["label", "value"], order_by="idx asc")
		w["details"] = details
		w["complete"] = bool(w.is_upwork) or (bool(details) and all((d.value or "").strip() for d in details))
		wallets.append(w)
	return {
		"settings": settings,
		"clients": frappe.get_all("SB Client", filters={"disabled": 0}, fields=[
			"name", "client_name", "contact_person", "email", "address", "country", "project", "currency",
			"payment_terms_days", "tax_treatment", "wallet", "payment_method", "purpose_code", "sac_code",
			"hsn_code", "last_milestone", "last_billing_period", "last_amount"], order_by="client_name asc"),
		"wallets": wallets,
		"tax_codes": frappe.get_all("SB Tax Code", fields=["code_type", "code", "description", "is_favourite"],
			order_by="is_favourite desc, code asc"),
		"purpose_codes": frappe.get_all("SB Purpose Code", fields=["code", "description", "is_favourite"],
			order_by="is_favourite desc, code asc"),
		"tax_treatments": list(calc.TAX_RATES),
		"access": user_access(),
	}


@frappe.whitelist()
def preview(payload) -> dict:
	"""Runs the same server rules as saving, without saving. Never throws for missing data."""
	_require_access()
	doc = _build(_load(payload))
	if doc.client and frappe.db.exists("SB Client", doc.client):
		doc.fill_from_client()
	doc.invoice_date = doc.invoice_date or frappe.utils.today()
	doc.due_date = frappe.utils.add_days(doc.invoice_date, cint(doc.payment_terms_days))
	doc.gst_return_period = calc.gst_return_period(doc.invoice_date)
	totals = calc.compute_lines(doc.items, doc.tax_treatment or "Export under LUT")
	doc.update(totals)
	doc.set_cbic_rate()
	doc.amount_inr = flt(doc.grand_total * flt(doc.cbic_rate), 2)
	s = frappe.get_cached_doc("SupaBill Settings")
	return {
		"next_invoice": calc.format_invoice_number(s.invoice_prefix, s.next_invoice_number, s.number_digits),
		"due_date": str(doc.due_date),
		"gst_return_period": doc.gst_return_period,
		"items": [{"amount": i.amount, "tax_amount": i.tax_amount} for i in doc.items],
		**totals,
		"cbic_rate": doc.cbic_rate,
		"cbic_rate_source": doc.cbic_rate_source,
		"cbic_rate_effective_from": str(doc.cbic_rate_effective_from) if doc.cbic_rate_effective_from else None,
		"amount_inr": doc.amount_inr,
		"readiness": [{"level": lv, "message": m} for lv, m in readiness(doc)],
	}


@frappe.whitelist()
def cbic_rate_for(date: str, currency: str) -> dict:
	_require_access()
	rate, effective = calc.cbic_rate_for(getdate(date), currency)
	return {"rate": rate, "effective_from": str(effective) if effective else None}


@frappe.whitelist(methods=["POST"])
def create_invoice(payload, request_id: str | None = None) -> dict:
	"""Creates and submits the invoice. The same request_id returns the first invoice again."""
	_require_access()
	if not frappe.has_permission("SB Invoice", "create") or not frappe.has_permission("SB Invoice", "submit"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if request_id:
		existing = frappe.db.get_value("SB Invoice", {"client_request_id": request_id}, "name")
		if existing:
			return _summary(frappe.get_doc("SB Invoice", existing), duplicate=True)
	doc = _build(_load(payload))
	doc.client_request_id = request_id
	doc.insert()
	doc.submit()
	return _summary(doc)


def _summary(doc, duplicate: bool = False) -> dict:
	return {
		"name": doc.name, "client_name": doc.client_name, "grand_total": doc.grand_total,
		"currency": doc.currency, "amount_inr": doc.amount_inr, "invoice_date": str(doc.invoice_date),
		"excel_sync_status": doc.excel_sync_status, "duplicate": duplicate,
	}


@frappe.whitelist(methods=["POST"])
def update_register(name: str, values) -> dict:
	"""Updates only the register columns of a submitted invoice."""
	_require_access()
	values = _load(values)
	bad = set(values) - set(REGISTER_FIELDS)
	if bad:
		frappe.throw(_("These fields cannot be changed here: {0}").format(", ".join(sorted(bad))))
	doc = frappe.get_doc("SB Invoice", name)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted invoices can be updated in the register"))
	for k, v in values.items():
		doc.set(k, None if v == "" and k in ("received_inr", "bank_charges_usd", "bank_charges_inr") else v)
	doc.save()
	return {k: doc.get(k) for k in LIST_FIELDS}


@frappe.whitelist(methods=["POST"])
def cancel_invoice(name: str, reason: str | None = None) -> dict:
	_require_access(manager=True)
	doc = frappe.get_doc("SB Invoice", name)
	doc.check_permission("cancel")
	doc.cancel()
	if reason:
		doc.add_comment("Comment", _("Cancelled: {0}").format(reason))
	return {"name": doc.name, "docstatus": doc.docstatus}


@frappe.whitelist()
def list_register(filters=None, search: str | None = None, limit: int = 500, start: int = 0) -> dict:
	"""Register rows plus totals. Filters: month (YYYY-MM), client, wallet, payment_state."""
	_require_access()
	f = _load(filters)
	conds = {"docstatus": ("in", (1, 2))}
	if f.get("client"):
		conds["client"] = f["client"]
	if f.get("wallet"):
		conds["wallet"] = f["wallet"]
	if f.get("month"):
		y, m = (int(x) for x in f["month"].split("-"))
		start_d = f"{y}-{m:02d}-01"
		end_d = f"{y + (m // 12)}-{(m % 12) + 1:02d}-01"
		conds["invoice_date"] = ("between", (start_d, frappe.utils.add_days(end_d, -1)))
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"name": ("like", like), "client_name": ("like", like), "wallet_reference": ("like", like),
			"upwork_invoice": ("like", like), "register_description": ("like", like)}
	rows = frappe.get_list("SB Invoice", filters=conds, or_filters=or_filters, fields=list(LIST_FIELDS),
		order_by="invoice_date asc, name asc", limit_page_length=min(cint(limit) or 500, 2000),
		limit_start=cint(start))
	today = getdate()
	for r in rows:
		r["payment_state"] = _payment_state(r, today)
	if f.get("payment_state"):
		rows = [r for r in rows if r["payment_state"] == f["payment_state"]]
	live = [r for r in rows if r.docstatus == 1]
	return {
		"rows": rows,
		"totals": {
			"count": len(live),
			"amount_inr": flt(sum(flt(r.amount_inr) for r in live), 2),
			"received_inr": flt(sum(flt(r.received_inr) for r in live), 2),
			"outstanding_inr": flt(sum(flt(r.amount_inr) for r in live if r.payment_state != "Received"), 2),
			"forex_gain": flt(sum(flt(r.forex_gain) for r in live), 2),
			"overdue": sum(1 for r in live if r.payment_state == "Overdue"),
			"missing_wallet_ref": sum(1 for r in live if not r.wallet_reference and r.wallet != "Upwork"),
		},
		"months": sorted({str(r.invoice_date)[:7] for r in rows}),
	}


def _payment_state(r, today) -> str:
	if r.docstatus == 2:
		return "Cancelled"
	if r.payment_status in ("Received", "Partially received"):
		return r.payment_status
	return "Overdue" if r.due_date and getdate(r.due_date) < today else "Pending"
