"""EDF filing and realisation tracking.

One consolidated Export Declaration Form per invoice month (all wallets settle into one AD bank),
laid out like the RBI Annex. Draft EDFs follow the register; a filed EDF is frozen.
"""
from __future__ import annotations

import csv
import io
import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, flt, formatdate, get_last_day, getdate, money_in_words, today

from supabill.api.session import user_access
from supabill.supabill.doctype.sb_invoice.sb_invoice import realisation_months

EDITABLE_HEADER = ("export_type", "exporter_category", "form_no")
EDITABLE_LINE = ("net_realisable_value", "contract", "remarks")
DUE_DAYS = 30  # after month-end


def _require(manager: bool = False):
	a = user_access()
	if not a["has_access"] or (manager and not a["is_manager"]):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _load(v):
	return json.loads(v or "{}") if isinstance(v, str) else (v or {})


def _check_month(month: str) -> str:
	try:
		y, m = (int(x) for x in str(month).split("-"))
		assert 2000 < y < 2100 and 1 <= m <= 12
	except Exception:
		frappe.throw(_("Month must look like 2026-11"))
	return f"{y}-{m:02d}"


def month_range(month: str):
	start = getdate(f"{month}-01")
	return start, get_last_day(start)


def due_date(month: str):
	return add_days(month_range(month)[1], DUE_DAYS)


def eligible_invoices(month: str) -> list[dict]:
	"""Submitted export invoices dated in the month, excluding cancelled ones."""
	start, end = month_range(month)
	return frappe.get_all("SB Invoice", filters={
		"docstatus": 1, "tax_treatment": "Export under LUT", "invoice_status": ("!=", "Cancelled"),
		"invoice_date": ("between", (start, end))},
		fields=["name", "client", "client_name", "billing_address", "client_country", "invoice_date", "currency",
			"grand_total", "amount_inr", "register_description", "wallet", "wallet_name_other", "realise_by"],
		order_by="invoice_date asc, name asc")


def _line_from_invoice(inv) -> dict:
	item = frappe.get_all("SB Invoice Item", filters={"parent": inv.name, "parenttype": "SB Invoice"},
		fields=["description", "sac_code"], order_by="idx asc", limit=1)
	wallet = inv.wallet_name_other if inv.wallet == "Others" and inv.wallet_name_other else inv.wallet
	return {
		"invoice": inv.name, "client_name": inv.client_name, "address": (inv.billing_address or "").replace("\n", ", "),
		"country": inv.client_country or "", "invoice_date": inv.invoice_date, "currency": inv.currency,
		"amount": flt(inv.grand_total, 2), "amount_inr": flt(inv.amount_inr, 2),
		"description": (item[0].description if item else "") or inv.register_description or "",
		"sac_code": (item[0].sac_code if item else "") or "", "_wallet": wallet,
	}


def refresh(doc) -> None:
	"""Re-reads the month's invoices into a draft EDF, keeping the user's edits per invoice."""
	kept = {l.invoice: {k: l.get(k) for k in EDITABLE_LINE} for l in doc.lines}
	doc.set("lines", [])
	for inv in eligible_invoices(doc.month):
		line = _line_from_invoice(inv)
		wallet = line.pop("_wallet")
		edits = kept.get(inv.name) or {}
		line["net_realisable_value"] = edits.get("net_realisable_value") if edits.get("net_realisable_value") not in (None, "") else line["amount"]
		line["contract"] = edits.get("contract") or ""
		line["remarks"] = edits.get("remarks") if inv.name in kept else (f"Collected via {wallet}" if wallet else "")
		doc.append("lines", line)
	_totals(doc)


def _totals(doc):
	doc.due_date = due_date(doc.month)
	dates = [getdate(l.invoice_date) for l in doc.lines if l.invoice_date]
	doc.realise_by = add_months(min(dates), realisation_months()) if dates else None
	doc.invoice_count = len(doc.lines)
	doc.total_inr = flt(sum(flt(l.amount_inr) for l in doc.lines), 2)


def get_or_create(month: str):
	name = frappe.db.get_value("SB EDF", {"month": month})
	if name:
		doc = frappe.get_doc("SB EDF", name)
	else:
		doc = frappe.new_doc("SB EDF")
		doc.month = month
	if doc.status != "Filed":
		refresh(doc)
		if doc.is_new():
			if doc.lines:
				doc.insert()
		else:
			doc.save()
	return doc


def _settings():
	s = frappe.get_cached_doc("SupaBill Settings")
	return {
		"legal_name": s.legal_name or "", "company_address": (s.company_address or "").replace("\n", " "),
		"gstin": s.gstin or "", "pan": s.pan or "", "iec": s.iec or "",
		"ad_bank_name": s.ad_bank_name or "", "ad_code": s.ad_code or "", "ad_branch_address": s.ad_branch_address or "",
		"signatory_name": s.signatory_name or "", "signatory_designation": s.signatory_designation or "",
		"signatory_place": s.signatory_place or "",
	}


def _missing(doc, st) -> list[str]:
	out = []
	for key, label in (("ad_code", "AD code (Settings → AD bank)"), ("ad_branch_address", "AD branch address (Settings → AD bank)"),
			("pan", "PAN (Settings → Company)"), ("iec", "IEC (Settings → Company)"), ("signatory_name", "Authorised signatory (Settings)")):
		if not st[key] or st[key].upper() == "NA" and key == "iec":
			out.append(label)
	for l in doc.lines:
		if not l.country:
			out.append(f"Country for {l.client_name} ({l.invoice})")
		if not l.address:
			out.append(f"Address for {l.client_name} ({l.invoice})")
		if not l.sac_code:
			out.append(f"SAC code on {l.invoice}")
	return out


def _payload(doc) -> dict:
	st = _settings()
	d = {"name": None if doc.is_new() else doc.name, "filed_on": str(doc.filed_on) if doc.filed_on else None,
		"bank_reference": doc.bank_reference or ""}
	d.update({
		"month": doc.month, "status": doc.status or "Draft", "export_type": doc.export_type or "Service — software",
		"exporter_category": doc.exporter_category or "Others", "form_no": doc.form_no or "",
		"due_date": str(doc.due_date or due_date(doc.month)), "realise_by": str(doc.realise_by) if doc.realise_by else None,
		"days_left": date_diff(doc.due_date or due_date(doc.month), today()),
		"lines": [{k: (str(v) if k == "invoice_date" and v else v) for k, v in l.as_dict().items()
			if k in ("invoice", "client_name", "address", "country", "invoice_date", "currency", "amount", "amount_inr",
				"net_realisable_value", "contract", "description", "sac_code", "remarks")} for l in doc.lines],
		"total_inr": flt(doc.total_inr), "total_in_words": money_in_words(flt(doc.total_inr), "INR") if doc.total_inr else "",
		"settings": st, "missing": _missing(doc, st), "saved": not doc.is_new(),
		"countries": sorted({l.country for l in doc.lines if l.country}),
		"wallets": sorted({(l.remarks or "").replace("Collected via ", "") for l in doc.lines if (l.remarks or "").startswith("Collected via ")}),
	})
	return d


# ---------------- whitelisted ----------------

@frappe.whitelist()
def list_months() -> list[dict]:
	"""Months with export invoices (plus the current month), newest first, with filing status."""
	_require()
	rows = frappe.db.sql("""select date_format(invoice_date, '%Y-%m') m, count(*) n, sum(amount_inr) inr
		from `tabSB Invoice` where docstatus=1 and tax_treatment='Export under LUT' and invoice_status!='Cancelled'
		group by m""", as_dict=True)
	by = {r.m: r for r in rows}
	edfs = {e.month: e for e in frappe.get_all("SB EDF", fields=["month", "status", "filed_on", "bank_reference"])}
	months = sorted(set(by) | set(edfs) | {today()[:7]}, reverse=True)
	out = []
	for m in months:
		e = edfs.get(m)
		out.append({"month": m, "label": formatdate(f"{m}-01", "MMMM yyyy"), "invoices": cint(by[m].n) if m in by else 0,
			"total_inr": flt(by[m].inr) if m in by else 0, "status": e.status if e else "Not started",
			"filed_on": str(e.filed_on) if e and e.filed_on else None, "bank_reference": e.bank_reference if e else None,
			"due_date": str(due_date(m)), "days_left": date_diff(due_date(m), today())})
	return out


@frappe.whitelist()
def get_edf(month: str) -> dict:
	_require()
	return _payload(get_or_create(_check_month(month)))


@frappe.whitelist(methods=["POST"])
def save_edf(month: str, values=None, lines=None) -> dict:
	"""Saves header choices and per-invoice edits (net realisable value, contract, remarks) on a draft."""
	_require()
	month = _check_month(month)
	doc = get_or_create(month)
	if doc.is_new():
		frappe.throw(_("There are no export invoices in this month yet"))
	values, lines = _load(values), _load(lines) if lines else []
	if doc.status == "Filed" and (set(values) - {"form_no"} or lines):
		frappe.throw(_("This EDF is filed. Reopen it to make changes."))
	for k in EDITABLE_HEADER:
		if k in values:
			doc.set(k, values[k])
	by_inv = {l.invoice: l for l in doc.lines}
	for row in lines:
		l = by_inv.get(row.get("invoice"))
		if not l:
			continue
		for k in EDITABLE_LINE:
			if k in row:
				v = row[k]
				if k == "net_realisable_value":
					v = flt(v, 2)
					if v < 0 or v > flt(l.amount) * 1.0001:
						frappe.throw(_("Net realisable value for {0} must be between 0 and the invoice amount").format(l.invoice))
				l.set(k, v)
	doc.save()
	return _payload(doc)


@frappe.whitelist(methods=["POST"])
def mark_filed(month: str, bank_reference: str | None = None, filed_on: str | None = None) -> dict:
	_require(manager=True)
	doc = get_or_create(_check_month(month))
	if doc.is_new() or not doc.lines:
		frappe.throw(_("There are no export invoices in this month to file"))
	doc.status, doc.filed_on, doc.bank_reference = "Filed", getdate(filed_on or today()), (bank_reference or "").strip()
	doc.save()
	for l in doc.lines:
		frappe.db.set_value("SB Invoice", l.invoice, "edf", doc.name, update_modified=False)
	doc.add_comment("Info", _("Marked as filed{0}").format(f" · ref {doc.bank_reference}" if doc.bank_reference else ""))
	return _payload(doc)


@frappe.whitelist(methods=["POST"])
def reopen(month: str) -> dict:
	_require(manager=True)
	doc = frappe.get_doc("SB EDF", {"month": _check_month(month)})
	doc.status, doc.filed_on = "Draft", None
	refresh(doc)
	doc.save()
	frappe.db.sql("update `tabSB Invoice` set edf=NULL where edf=%s", doc.name)
	doc.add_comment("Info", _("Reopened"))
	return _payload(doc)


def render_html(month: str) -> str:
	d = get_or_create(month)
	p = _payload(d)
	p["date"] = formatdate(d.filed_on or today(), "d MMM yyyy")
	p["fmt"] = lambda x: formatdate(x, "d MMM yyyy") if x else ""
	p["is_software"] = p["export_type"] == "Service — software"
	p["categories"] = ["Custom (DTA units)", "SEZ", "100% EOU", "Warehouse export", "Others"]
	return frappe.render_template("supabill/templates/print/edf.html", p)


@frappe.whitelist()
def download(month: str, fmt: str = "pdf"):
	_require()
	month = _check_month(month)
	if fmt == "pdf":
		from frappe.utils.pdf import get_pdf
		data = get_pdf(render_html(month), {"page-size": "A4", "orientation": "Portrait", "margin-top": "10mm",
			"margin-bottom": "10mm", "margin-left": "10mm", "margin-right": "10mm"})
	elif fmt == "csv":
		p = _payload(get_or_create(month))
		st = p["settings"]
		buf = io.StringIO()
		w = csv.writer(buf)
		for row in (["Export Declaration Form", formatdate(f"{month}-01", "MMMM yyyy"), p["export_type"]],
				["Exporter", st["legal_name"]], ["PAN", st["pan"]], ["GSTIN", st["gstin"]], ["IEC", st["iec"]],
				["AD name", st["ad_bank_name"]], ["AD code", st["ad_code"]], ["Mode of delivery", "Internet"],
				["Mode of realisation", "Others"], [],
				["S. No.", "Service recipient", "Address", "Country", "Invoice No.", "Date", "Currency", "Amount",
					"Net Realisable value", "Contract No. & Date", "Description of services", "SAC Code", "Remarks"]):
			w.writerow(row)
		for i, l in enumerate(p["lines"], 1):
			w.writerow([i, l["client_name"], l["address"], l["country"], l["invoice"], l["invoice_date"], l["currency"],
				f"{flt(l['amount']):.2f}", f"{flt(l['net_realisable_value']):.2f}", l["contract"] or "", l["description"],
				l["sac_code"], l["remarks"] or ""])
		data = ("﻿" + buf.getvalue()).encode()
	else:
		frappe.throw(_("Format must be pdf or csv"))
	frappe.local.response.filename = f"EDF_{month}.{fmt}"
	frappe.local.response.filecontent = data
	frappe.local.response.type = "download"


@frappe.whitelist()
def realisation(show_closed: int = 0) -> dict:
	"""Every export invoice until its EDPMS entry is closed, soonest deadline first."""
	_require()
	filters = {"docstatus": 1, "tax_treatment": "Export under LUT", "invoice_status": ("!=", "Cancelled")}
	rows = frappe.get_all("SB Invoice", filters=filters, fields=["name", "invoice_date", "client_name", "wallet",
		"wallet_name_other", "currency", "grand_total", "amount_inr", "received_inr", "payment_status", "realise_by",
		"irm_number", "edpms_status", "realised_on", "edf"], order_by="invoice_date asc", limit=2000)
	months = realisation_months()
	out, kp = [], {"open": 0, "due_60": 0, "late": 0, "closed": 0, "ready_to_close": 0}
	for r in rows:
		by = r.realise_by or add_months(r.invoice_date, months)
		closed = r.edpms_status == "Closed"
		left = date_diff(by, today())
		ready = not closed and r.payment_status == "Received"
		if closed:
			kp["closed"] += 1
		else:
			kp["open"] += 1
			kp["late"] += left < 0
			kp["due_60"] += 0 <= left <= 60
			kp["ready_to_close"] += ready
		if closed and not cint(show_closed):
			continue
		out.append({**r, "invoice_date": str(r.invoice_date), "realise_by": str(by), "days_left": left, "closed": closed,
			"ready_to_close": ready, "realised_on": str(r.realised_on) if r.realised_on else None,
			"wallet": r.wallet_name_other if r.wallet == "Others" and r.wallet_name_other else r.wallet})
	out.sort(key=lambda x: (x["closed"], x["days_left"]))
	return {"rows": out, "kpis": kp, "months": months}


@frappe.whitelist(methods=["POST"])
def update_realisation(name: str, values) -> dict:
	"""IRM number, EDPMS status and realised date on a submitted invoice."""
	_require()
	values = _load(values)
	bad = set(values) - {"irm_number", "edpms_status", "realised_on"}
	if bad:
		frappe.throw(_("These fields cannot be changed here: {0}").format(", ".join(sorted(bad))))
	if values.get("edpms_status") not in (None, "Open", "Closed"):
		frappe.throw(_("EDPMS status must be Open or Closed"))
	doc = frappe.get_doc("SB Invoice", name)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted invoices are tracked"))
	for k, v in values.items():
		doc.set(k, (v or None) if k == "realised_on" else (v or "").strip() if k == "irm_number" else v)
	if doc.edpms_status == "Closed" and not doc.realised_on:
		doc.realised_on = getdate(today())
	if doc.edpms_status == "Open":
		doc.realised_on = None
	doc.save()
	return {"name": doc.name, "irm_number": doc.irm_number, "edpms_status": doc.edpms_status,
		"realised_on": str(doc.realised_on) if doc.realised_on else None}


def edf_badge() -> int:
	"""Months with export invoices whose EDF is not filed."""
	return sum(1 for m in list_months() if m["invoices"] and m["status"] != "Filed")
