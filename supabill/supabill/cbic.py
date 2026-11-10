"""CBIC exchange rates from AllRatesToday (provider code "cbic").

The key comes from SupaBill Settings (Password field) or the site config
`allratestoday_api_key`. It is never logged, returned to the browser, or written to Excel.
"""
from __future__ import annotations

import time

import frappe
import requests
from frappe.utils import flt, getdate, now_datetime

BASE = "https://allratestoday.com"
CURRENCIES = ("USD", "EUR", "GBP", "AUD", "CAD")
TIMEOUT = 15
RETRIES = 3


class RateError(Exception):
	"""Safe message only; never contains the key."""


def _key() -> str | None:
	s = frappe.get_doc("SupaBill Settings")
	return s.get_password("allratestoday_api_key", raise_exception=False) or frappe.conf.get("allratestoday_api_key")


def _get(path: str, params: dict | None = None, auth: bool = True) -> dict:
	headers = {"Accept": "application/json", "User-Agent": "SupaBill/1.0"}
	if auth:
		key = _key()
		if not key:
			raise RateError("No AllRatesToday API key is saved")
		headers["Authorization"] = f"Bearer {key}"
	last = "unknown error"
	for attempt in range(RETRIES):
		try:
			r = requests.get(BASE + path, params=params, headers=headers, timeout=TIMEOUT)
		except requests.RequestException as e:
			last = type(e).__name__
		else:
			if r.status_code == 200:
				try:
					return r.json()
				except ValueError:
					raise RateError("AllRatesToday sent a response that is not JSON") from None
			if r.status_code == 401:
				raise RateError("AllRatesToday rejected the API key (401) — check or rotate it")
			if r.status_code == 403:
				raise RateError("AllRatesToday refused the request (403) — dated rates need a paid plan")
			if r.status_code == 404:
				raise RateError("AllRatesToday has no CBIC table for that request (404)")
			last = f"HTTP {r.status_code}"
			if r.status_code != 429 and r.status_code < 500:
				break
			wait = flt(r.headers.get("Retry-After")) or 2**attempt
			time.sleep(min(wait, 10))
			continue
		time.sleep(2**attempt)
	raise RateError(f"AllRatesToday unreachable ({last})")


def parse_table(payload: dict) -> list[dict]:
	"""Accepts either a table ({rate_date, rates:[{base,quote,type,value}]}) or one pair."""
	if not isinstance(payload, dict):
		raise RateError("Unexpected response shape from AllRatesToday")
	date = (payload.get("rate_date") or payload.get("date") or "")[:10]
	rows = payload.get("rates")
	if rows is None and payload.get("rate") is not None:
		rows = [{"base": payload.get("source"), "quote": payload.get("target"), "type": payload.get("rate_type"),
			"value": payload.get("rate")}]
	if not date or not isinstance(rows, list):
		raise RateError("AllRatesToday response is missing rate_date or rates")
	by: dict[str, dict] = {}
	for row in rows:
		if not isinstance(row, dict):
			continue
		base = str(row.get("base") or row.get("source") or "").upper()
		quote = str(row.get("quote") or row.get("target") or "INR").upper()
		value = flt(row.get("value", row.get("rate")))
		if quote != "INR" or base not in CURRENCIES or value <= 0:
			continue
		kind = str(row.get("type") or row.get("rate_type") or "export").lower()
		by.setdefault(base, {})[kind] = value
	out = []
	for cur, v in by.items():
		exp = v.get("export")
		if not exp:
			continue  # export rate is what invoices need; skip import-only rows
		out.append({"effective_from": date, "currency": cur, "export_rate": exp, "import_rate": v.get("import")})
	return out


def store(rates: list[dict], source: str = "AllRatesToday") -> int:
	saved = 0
	for r in rates:
		name = f"{r['currency']}-{r['effective_from']}"
		doc = frappe.get_doc("SB CBIC Rate", name) if frappe.db.exists("SB CBIC Rate", name) else frappe.new_doc("SB CBIC Rate")
		doc.update({**r, "source": source})
		doc.flags.ignore_permissions = True
		doc.save()
		saved += 1
	return saved


def _log(status: str, message: str):
	frappe.get_doc({"doctype": "SB Sync Log", "integration": "CBIC", "direction": "Fetch", "status": status,
		"message": message[:1000]}).insert(ignore_permissions=True)
	frappe.db.set_single_value("SupaBill Settings", {"cbic_last_sync": now_datetime(),
		"cbic_last_status": message[:500]})


def sync(raise_errors: bool = False) -> dict:
	"""Fetch the latest CBIC table and store it. Keyed endpoint first, key-free fallback."""
	s = frappe.get_cached_doc("SupaBill Settings")
	if s.cbic_provider == "Manual":
		return {"ok": False, "message": "CBIC source is set to Manual — nothing fetched"}
	try:
		try:
			payload = _get("/api/v1/central-bank/cbic/latest")
		except RateError as keyed_error:
			if "No AllRatesToday API key" not in str(keyed_error) and "401" not in str(keyed_error):
				raise
			payload = _get("/api/open/central-bank/cbic", auth=False)
		rates = parse_table(payload)
		if not rates:
			raise RateError("AllRatesToday returned no INR export rates — existing rates kept")
		n = store(rates)
		date = rates[0]["effective_from"]
		msg = f"Stored {n} rates ({', '.join(sorted(r['currency'] for r in rates))}) notified {getdate(date).strftime('%d %b %Y')}"
		_log("Success", msg)
		return {"ok": True, "message": msg}
	except RateError as e:
		_log("Failed", str(e))
		if raise_errors:
			frappe.db.commit()  # keep the failure log even though the request rolls back
			frappe.throw(str(e), title="CBIC rates not updated")
		return {"ok": False, "message": str(e)}


def fetch_for_date(date, currency: str = "USD") -> dict | None:
	"""Dated lookup (paid plan). Stores and returns the rate, or None if unavailable."""
	try:
		rates = parse_table(_get(f"/api/v1/central-bank/cbic/{getdate(date)}", {"source": currency, "target": "INR"}))
	except RateError:
		return None
	store(rates)
	return next((r for r in rates if r["currency"] == currency), None)


def scheduled_sync():
	"""Scheduler entry: runs on CBIC notification days and daily as a safety net."""
	sync()
