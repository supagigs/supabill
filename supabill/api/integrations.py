"""Manager actions for the integrations. Results are messages safe to show; no secrets."""
import frappe
from frappe import _

from supabill.api.session import user_access
from supabill.supabill import cbic, excel


def _manager():
	a = user_access()
	if not (a["has_access"] and a["is_manager"]):
		frappe.throw(_("Only SupaBill Managers can run integrations"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
@frappe.rate_limit(limit=10, seconds=60)
def sync_cbic_now() -> dict:
	_manager()
	return cbic.sync(raise_errors=True)


@frappe.whitelist(methods=["POST"])
@frappe.rate_limit(limit=10, seconds=60)
def excel_test() -> dict:
	_manager()
	try:
		g = excel.Graph()
		header, rows, first = g.header_and_rows()
		excel._check_header(header)
	except excel.SyncError as e:
		frappe.throw(str(e), title=_("Excel connection failed"))
	return {"ok": True, "message": f"Connected: table '{g.s.table_name}' has {len(rows)} rows and {len(header)} columns"}


@frappe.whitelist(methods=["POST"])
@frappe.rate_limit(limit=10, seconds=60)
def excel_sync_now() -> dict:
	_manager()
	if not frappe.db.get_single_value("SupaBill Settings", "excel_enabled"):
		frappe.throw(_("Turn on Excel sync in Settings first"))
	excel.retry_failed()
	out = excel.pull(force=True)
	if not out["ok"]:
		frappe.throw(out["message"], title=_("Excel sync failed"))
	return out


@frappe.whitelist()
def sync_status() -> dict:
	"""Shown in the sidebar: last push/pull and how many invoices are waiting."""
	if not user_access()["has_access"]:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	s = frappe.get_cached_doc("SupaBill Settings")
	return {
		"enabled": bool(s.excel_enabled), "worksheet": s.worksheet_name, "table": s.table_name,
		"last_push": s.excel_last_push, "last_pull": s.excel_last_pull,
		"waiting": frappe.db.count("SB Invoice", {"docstatus": 1, "excel_sync_status": ("in", ("Queued", "Failed"))}),
		"failed": frappe.db.count("SB Invoice", {"docstatus": 1, "excel_sync_status": "Failed"}),
	}
