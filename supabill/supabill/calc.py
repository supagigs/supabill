"""Pure calculation helpers for SupaBill. No database access except cbic_rate_for."""
from __future__ import annotations

import frappe
from frappe.utils import flt, getdate

TAX_RATES = {
	"Export under LUT": 0.0,
	"IGST 18%": 0.18,
	"CGST + SGST 9%": 0.18,
}

QUARTERS = (
	(1, 3, "January - March"),
	(4, 6, "April - June"),
	(7, 9, "July - September"),
	(10, 12, "October - December"),
)


def format_invoice_number(prefix: str, number: int, digits: int) -> str:
	return f"{prefix}{int(number):0{max(int(digits or 1), 1)}d}"


def gst_return_period(date) -> str:
	if not date:
		return ""
	d = getdate(date)
	for start, end, label in QUARTERS:
		if start <= d.month <= end:
			return f"{label} {d.year}"
	return ""


def tax_rate(treatment: str) -> float:
	if treatment not in TAX_RATES:
		frappe.throw(f"Unknown tax treatment: {treatment}")
	return TAX_RATES[treatment]


def compute_lines(items, treatment: str, precision: int = 2) -> dict:
	"""Sets amount/tax on each item (dicts or child docs) and returns totals."""
	rate = tax_rate(treatment)
	subtotal = tax_total = 0.0
	for it in items:
		base = flt(flt(it.get("qty")) * flt(it.get("rate")), precision)
		tax = flt(base * rate, precision)
		it.update({"tax_amount": tax, "amount": flt(base + tax, precision)})
		subtotal += base
		tax_total += tax
	subtotal, tax_total = flt(subtotal, precision), flt(tax_total, precision)
	return {"subtotal": subtotal, "tax_total": tax_total, "grand_total": flt(subtotal + tax_total, precision)}


def register_calcs(amount_inr, received_inr, bank_charges_inr) -> dict:
	"""Forex gain and net received follow the Excel sheet: P-O and P-charges."""
	if received_inr in (None, ""):
		return {"forex_gain": None, "net_received": None}
	received = flt(received_inr, 2)
	return {
		"forex_gain": flt(received - flt(amount_inr, 2), 2),
		"net_received": flt(received - flt(bank_charges_inr, 2), 2),
	}


def derive_payment_status(current: str, received_inr, amount_inr) -> str:
	"""Only moves a Pending invoice forward; never overrides a status set by hand."""
	if current != "Pending" or received_inr in (None, "") or not flt(received_inr):
		return current
	return "Received" if flt(received_inr) >= flt(amount_inr) * 0.95 else "Partially received"


def cbic_rate_for(date, currency: str):
	"""Export rate notified on or before the date. Returns (rate, effective_from) or (None, None)."""
	if not date or not currency or currency == "INR":
		return (1.0, None) if currency == "INR" else (None, None)
	row = frappe.get_all(
		"SB CBIC Rate",
		filters={"currency": currency, "effective_from": ("<=", getdate(date))},
		fields=["export_rate", "effective_from"],
		order_by="effective_from desc",
		limit=1,
	)
	if not row:
		return None, None
	return flt(row[0].export_rate, 4), row[0].effective_from
