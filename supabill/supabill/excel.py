"""Two-way Excel sync with the Microsoft 365 workbook through Microsoft Graph.

Push: each submitted invoice becomes one row in the workbook's Excel table.
Pull: the columns the team fills in later (wallet ref, Received, bank charges,
payment status) are read back. For those columns Excel wins; for everything else
SupaBill wins and Excel is never written over except in rows SupaBill added.

App-only auth (client credentials). Credentials live in SupaBill Settings
(client secret is a Password field) and are never logged.
"""
from __future__ import annotations

import base64
import time

import frappe
import requests
from frappe.utils import cint, flt, formatdate, now_datetime

GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 20
RETRIES = 4

# Excel columns, in sheet order (A..V). Index into a row's values.
COLUMNS = [
	"Sr. No.", "Original Invoice Number", "Upwork Invoice", "Upwork Account Holder", "Wallet Reference Invoice Number",
	"Invoice Date", "Month", "Client Name", "Description", "Mode of Payment (Wallet Name)", "GST Return", "Currency",
	"Invoice Amount in Original Currency", "CBIC Rate Rs./$", "Invoice Amount in INR", "Received", "Forex Gain",
	"Net Received", "Bank Conversion Charges (In $)", "Bank Conversion Charges (In Rs)", "Payment Status", "Invoice Status",
]
COL = {name: i for i, name in enumerate(COLUMNS)}
PULL = {  # Excel column -> SB Invoice field (Excel wins for these)
	"Wallet Reference Invoice Number": "wallet_reference",
	"Received": "received_inr",
	"Bank Conversion Charges (In $)": "bank_charges_usd",
	"Bank Conversion Charges (In Rs)": "bank_charges_inr",
	"Payment Status": "payment_status",
}
STATUS_MAP = {"paid": "Received", "received": "Received", "partially received": "Partially received",
	"partial": "Partially received", "pending": "Pending", "": None}


class SyncError(Exception):
	pass


def letter(i: int) -> str:
	s = ""
	i += 1
	while i:
		i, r = divmod(i - 1, 26)
		s = chr(65 + r) + s
	return s


def share_id(url: str) -> str:
	"""Graph 'shares' id for a sharing link: u! + unpadded base64url."""
	return "u!" + base64.urlsafe_b64encode(url.strip().encode()).decode().rstrip("=")


class Graph:
	def __init__(self, settings=None):
		self.s = settings or frappe.get_doc("SupaBill Settings")
		for f in ("ms_tenant_id", "ms_client_id", "workbook_share_link", "table_name"):
			if not (self.s.get(f) or "").strip():
				raise SyncError(f"Excel sync needs '{self.s.meta.get_label(f)}' in Settings")
		self.secret = self.s.get_password("ms_client_secret", raise_exception=False)
		if not self.secret:
			raise SyncError("Excel sync needs the client secret in Settings")
		self._token = None
		self._item = None

	def token(self) -> str:
		if self._token:
			return self._token
		cache_key = f"supabill:graph_token:{self.s.ms_client_id}"
		cached = frappe.cache.get_value(cache_key)
		if cached:
			self._token = cached
			return cached
		r = requests.post(f"https://login.microsoftonline.com/{self.s.ms_tenant_id}/oauth2/v2.0/token", data={
			"client_id": self.s.ms_client_id, "client_secret": self.secret, "grant_type": "client_credentials",
			"scope": "https://graph.microsoft.com/.default"}, timeout=TIMEOUT)
		if r.status_code != 200:
			try:
				err = r.json().get("error_description", "").split("\r\n")[0]
			except ValueError:
				err = f"HTTP {r.status_code}"
			raise SyncError(f"Microsoft sign-in failed: {err or r.status_code}")
		body = r.json()
		self._token = body["access_token"]
		frappe.cache.set_value(cache_key, self._token, expires_in_sec=max(cint(body.get("expires_in", 3600)) - 120, 60))
		return self._token

	def call(self, method: str, path: str, json=None) -> tuple[dict, str | None]:
		last = None
		for attempt in range(RETRIES):
			try:
				r = requests.request(method, GRAPH + path, json=json, timeout=TIMEOUT,
					headers={"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"})
			except requests.RequestException as e:
				last = type(e).__name__
				time.sleep(2**attempt)
				continue
			req_id = r.headers.get("request-id")
			if r.status_code in (200, 201):
				return (r.json() if r.content else {}), req_id
			if r.status_code == 401 and attempt == 0:
				frappe.cache.delete_value(f"supabill:graph_token:{self.s.ms_client_id}")
				self._token = None
				continue
			if r.status_code in (429, 500, 502, 503, 504):
				last = f"HTTP {r.status_code}"
				time.sleep(min(flt(r.headers.get("Retry-After")) or 2**attempt, 30))
				continue
			try:
				msg = r.json().get("error", {}).get("message", "")
			except ValueError:
				msg = ""
			hint = {403: " — the app has no access to this file (check Sites.Selected / admin consent)",
				404: " — check the share link and the Excel table name"}.get(r.status_code, "")
			raise SyncError(f"Microsoft Graph {r.status_code}: {msg or 'request failed'}{hint} (request {req_id})")
		raise SyncError(f"Microsoft Graph unreachable ({last})")

	def item_path(self) -> str:
		if self._item:
			return self._item
		item, _ = self.call("GET", f"/shares/{share_id(self.s.workbook_share_link)}/driveItem")
		drive = item.get("parentReference", {}).get("driveId")
		if not drive or not item.get("id"):
			raise SyncError("The share link did not resolve to a workbook")
		self._item = f"/drives/{drive}/items/{item['id']}"
		return self._item

	def table(self) -> str:
		return f"{self.item_path()}/workbook/tables/{requests.utils.quote(self.s.table_name)}"

	def header_and_rows(self) -> tuple[list[str], list[list], int]:
		"""Header names, data rows, and the sheet row number of the first data row."""
		rng, _ = self.call("GET", f"{self.table()}/range")
		values = rng.get("values") or []
		if not values:
			raise SyncError("The Excel table is empty — it needs at least a header row")
		addr = rng.get("address", "")  # e.g. 2026-27!A2:V30
		first_row = int("".join(ch for ch in addr.split("!")[-1].split(":")[0] if ch.isdigit()) or 1)
		return [str(h).strip() for h in values[0]], values[1:], first_row + 1


def _log(status, direction, message, invoice=None, request_id=None, retries=0):
	frappe.get_doc({"doctype": "SB Sync Log", "integration": "Excel", "direction": direction, "status": status,
		"invoice": invoice, "request_id": request_id, "retries": retries, "message": (message or "")[:1000]}
		).insert(ignore_permissions=True)


def _check_header(header: list[str]):
	missing = [c for c in ("Original Invoice Number", *PULL) if c not in header]
	if missing:
		raise SyncError(f"Excel table is missing columns: {', '.join(missing)}")


def row_values(doc, header: list[str], sheet_row: int, sr_no: int) -> list:
	"""One table row in the workbook's own column order. Formula columns stay formulas."""
	pos = {h: i for i, h in enumerate(header)}

	def ref(col):
		return f"{letter(pos[col])}{sheet_row}" if col in pos else None

	wallet = doc.wallet_name_other if doc.wallet == "Others" and doc.wallet_name_other else doc.wallet
	values = {
		"Sr. No.": sr_no, "Original Invoice Number": doc.name, "Upwork Invoice": doc.upwork_invoice or "",
		"Upwork Account Holder": doc.upwork_account_holder or "", "Wallet Reference Invoice Number": doc.wallet_reference or "",
		"Invoice Date": formatdate(doc.invoice_date, "yyyy-mm-dd"), "Client Name": doc.client_name,
		"Description": doc.register_description or "", "Mode of Payment (Wallet Name)": wallet,
		"GST Return": doc.gst_return_period, "Currency": doc.currency,
		"Invoice Amount in Original Currency": flt(doc.grand_total, 2), "CBIC Rate Rs./$": flt(doc.cbic_rate, 4),
		"Received": "", "Net Received": "", "Bank Conversion Charges (In $)": "", "Bank Conversion Charges (In Rs)": "",
		"Payment Status": doc.payment_status or "Pending", "Invoice Status": doc.invoice_status or "Raised",
	}
	if ref("Invoice Date"):
		values["Month"] = f"=MONTH({ref('Invoice Date')})"
	if ref("Invoice Amount in Original Currency") and ref("CBIC Rate Rs./$"):
		values["Invoice Amount in INR"] = f"={ref('Invoice Amount in Original Currency')}*{ref('CBIC Rate Rs./$')}"
	if ref("Received") and ref("Invoice Amount in INR"):
		values["Forex Gain"] = f"={ref('Received')}-{ref('Invoice Amount in INR')}"
	return [values.get(h, "") for h in header]


def push_invoice(name: str):
	"""Background job after submit. Idempotent: an invoice already in the table is not added again."""
	doc = frappe.get_doc("SB Invoice", name)
	s = frappe.get_doc("SupaBill Settings")
	if not s.excel_enabled:
		doc.db_set("excel_sync_status", "Not synced", update_modified=False)
		return
	try:
		g = Graph(s)
		header, rows, first_data_row = g.header_and_rows()
		_check_header(header)
		inv_col = header.index("Original Invoice Number")
		for i, row in enumerate(rows):
			if str(row[inv_col]).strip() == doc.name:
				doc.db_set({"excel_sync_status": "Synced", "excel_row": first_data_row + i,
					"excel_last_synced": now_datetime()}, update_modified=False)
				_log("Skipped", "Push", "Already in the workbook", invoice=name)
				return
		sheet_row = first_data_row + len(rows)
		_, req = g.call("POST", f"{g.table()}/rows", json={"values": [row_values(doc, header, sheet_row, len(rows) + 1)]})
		doc.db_set({"excel_sync_status": "Synced", "excel_row": sheet_row, "excel_last_synced": now_datetime()},
			update_modified=False)
		frappe.db.set_single_value("SupaBill Settings", "excel_last_push", now_datetime())
		_log("Success", "Push", f"Added as row {sheet_row}", invoice=name, request_id=req)
	except SyncError as e:
		doc.db_set("excel_sync_status", "Failed", update_modified=False)
		_log("Failed", "Push", str(e), invoice=name)


def _excel_value(field: str, raw):
	if field == "payment_status":
		return STATUS_MAP.get(str(raw or "").strip().lower(), str(raw).strip() or None)
	if field in ("received_inr", "bank_charges_usd", "bank_charges_inr"):
		if raw in ("", None):
			return None
		try:
			return flt(str(raw).replace(",", "").replace("₹", "").replace("$", ""), 2)
		except (TypeError, ValueError):
			return None
	return str(raw).strip() if raw not in (None, "") else None


def pull(force: bool = False) -> dict:
	"""Read the payment columns back. Excel wins for them; blanks in Excel never wipe SupaBill data."""
	s = frappe.get_doc("SupaBill Settings")
	if not s.excel_enabled:
		return {"ok": False, "message": "Excel sync is turned off in Settings"}
	if not force and s.excel_last_pull:
		elapsed = (now_datetime() - frappe.utils.get_datetime(s.excel_last_pull)).total_seconds() / 60
		if elapsed < max(cint(s.pull_interval_minutes) or 5, 1):
			return {"ok": True, "message": "Read-back not due yet", "updated": 0}
	try:
		g = Graph(s)
		header, rows, first_data_row = g.header_and_rows()
		_check_header(header)
		inv_col = header.index("Original Invoice Number")
		updated = 0
		for i, row in enumerate(rows):
			name = str(row[inv_col]).strip()
			if not name or not frappe.db.exists("SB Invoice", {"name": name, "docstatus": 1}):
				continue
			doc = frappe.get_doc("SB Invoice", name)
			changes = {}
			for col, field in PULL.items():
				val = _excel_value(field, row[header.index(col)])
				if val is None:
					continue
				current = doc.get(field)
				same = flt(current, 2) == flt(val, 2) if isinstance(val, float) else (current or "") == val
				if not same:
					changes[field] = val
			if doc.excel_row != first_data_row + i:
				doc.db_set("excel_row", first_data_row + i, update_modified=False)
			if changes:
				doc.update(changes)
				doc.flags.ignore_permissions = True
				doc.flags.from_excel = True
				doc.save()
				updated += 1
				_log("Success", "Pull", "Updated from Excel: " + ", ".join(sorted(changes)), invoice=name)
		frappe.db.set_single_value("SupaBill Settings", "excel_last_pull", now_datetime())
		msg = f"Read {len(rows)} rows from Excel, updated {updated} invoice{'s' if updated != 1 else ''}"
		if not updated:
			_log("Skipped", "Pull", msg)
		return {"ok": True, "message": msg, "updated": updated}
	except SyncError as e:
		_log("Failed", "Pull", str(e))
		return {"ok": False, "message": str(e)}


def retry_failed():
	"""Re-queues pushes that failed or never ran (e.g. Microsoft was down)."""
	if not frappe.db.get_single_value("SupaBill Settings", "excel_enabled"):
		return
	for name in frappe.get_all("SB Invoice", filters={"docstatus": 1, "excel_sync_status": ("in", ("Failed", "Queued"))},
			pluck="name", limit=50):
		push_invoice(name)


def scheduled():
	"""Every 5 minutes: retry failed pushes, then read back if the interval has passed."""
	retry_failed()
	pull()


def push_register_update(name: str):
	"""Writes register edits made in SupaBill back to the invoice's Excel row (formulas kept)."""
	doc = frappe.get_doc("SB Invoice", name)
	s = frappe.get_doc("SupaBill Settings")
	if not s.excel_enabled or not doc.excel_row:
		return
	try:
		g = Graph(s)
		header, _rows, _first = g.header_and_rows()
		_check_header(header)
		sheet = requests.utils.quote(s.worksheet_name or "Sheet1")
		addr = f"A{doc.excel_row}:{letter(len(header) - 1)}{doc.excel_row}"
		rng, _ = g.call("GET", f"{g.item_path()}/workbook/worksheets/{sheet}/range(address='{addr}')?$select=formulas")
		formulas = (rng.get("formulas") or [[]])[0]
		if len(formulas) < len(header) or str(formulas[header.index("Original Invoice Number")]).strip() != doc.name:
			raise SyncError(f"Row {doc.excel_row} no longer holds {doc.name} — run Sync now to re-match rows")
		fields = {**PULL, "Upwork Invoice": "upwork_invoice", "Upwork Account Holder": "upwork_account_holder",
			"Invoice Status": "invoice_status", "Description": "register_description"}
		for col, field in fields.items():
			if col in header:
				val = doc.get(field)
				formulas[header.index(col)] = "" if val is None else val
		_, req = g.call("PATCH", f"{g.item_path()}/workbook/worksheets/{sheet}/range(address='{addr}')", json={"formulas": [formulas]})
		doc.db_set("excel_last_synced", now_datetime(), update_modified=False)
		_log("Success", "Push", f"Updated row {doc.excel_row}", invoice=name, request_id=req)
	except SyncError as e:
		_log("Failed", "Push", str(e), invoice=name)
