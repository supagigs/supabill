"""Import Wallet: CSV through Frappe Data Import (many wallets), or bank lines read from an invoice PDF (one wallet).

Flow for CSV: template → upload → review (choose Skip / Update / new name per clashing row) →
a Data Import of SB Wallet Import rows is created and started → status is polled.
Flow for PDF: upload → bank lines returned to the wallet form → saved with the normal save_wallet.
"""
from __future__ import annotations

import csv
import io
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from supabill.api.session import user_access
from supabill.supabill import wallet_import as wi


def _manager():
	a = user_access()
	if not (a["has_access"] and a["is_manager"]):
		frappe.throw(_("Only SupaBill Managers can import wallets"), frappe.PermissionError)


def _check_background_jobs():
	"""Data Import needs the scheduler; say so before anything is uploaded or created."""
	from frappe.utils.scheduler import is_scheduler_inactive
	if not (frappe.in_test or frappe.conf.developer_mode) and is_scheduler_inactive():
		frappe.throw(_("Background jobs are switched off on this site (the scheduler is inactive), so a CSV import cannot run. Ask your administrator to enable the scheduler, then try again."),
			title=_("Import not available"))


def _load(v):
	return json.loads(v or "null") if isinstance(v, str) else v


def _uploaded_file(file_url: str):
	"""Reads a file this user just uploaded, then deletes it (the upload is only a carrier)."""
	f = frappe.get_doc("File", {"file_url": file_url})
	if f.owner != frappe.session.user:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	content = f.get_content()
	return f, content if isinstance(content, bytes) else content.encode()


@frappe.whitelist()
def download_template():
	_manager()
	frappe.local.response.filename = "SupaBill_wallet_import_template.csv"
	frappe.local.response.filecontent = ("﻿" + wi.template_csv()).encode()
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def review_csv(file_url: str) -> dict:
	_manager()
	_check_background_jobs()
	f, content = _uploaded_file(file_url)
	try:
		rows = wi.review(wi.read_csv(content))
	finally:
		f.delete(ignore_permissions=True)
	return {"rows": rows, "existing_names": frappe.get_all("SB Wallet", pluck="name"), "counts": {s: sum(r["status"] == s for r in rows) for s in ("new", "exists", "error")}}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def run_csv(rows) -> dict:
	"""Rows from review with the user's choices: action create / update / skip / rename (+ wallet_name)."""
	_manager()
	_check_background_jobs()
	rows = _load(rows) or []
	if not rows:
		frappe.throw(_("Nothing to import"))
	if len(rows) > wi.MAX_ROWS:
		frappe.throw(_("At most {0} wallets per file").format(wi.MAX_ROWS))
	existing = {n.lower() for n in frappe.get_all("SB Wallet", pluck="name")}
	names, out_rows, skipped = set(), [], 0
	for r in rows:
		action = r.get("action")
		values = {f: (r.get("values") or {}).get(f, "") for f, _l in wi.COLUMNS}
		name = (r.get("wallet_name") or values["wallet_name"] or "").strip()
		if action == "skip":
			skipped += 1
			continue
		if action not in ("create", "update", "rename"):
			frappe.throw(_("Row {0}: choose what to do").format(r.get("row")))
		if not name:
			frappe.throw(_("Row {0}: wallet name is required").format(r.get("row")))
		if name.lower() in names:
			frappe.throw(_("Row {0}: {1} is used twice in this import").format(r.get("row"), name))
		names.add(name.lower())
		exists = name.lower() in existing
		if action in ("create", "rename") and exists:
			frappe.throw(_("Row {0}: a wallet called {1} already exists — choose Update, Skip or another name").format(r.get("row"), name))
		if action == "update" and not exists:
			frappe.throw(_("Row {0}: there is no wallet called {1} to update").format(r.get("row"), name))
		values.update({"wallet_name": name, "if_exists": "Update" if action == "update" else "Skip",
			"is_upwork": "1" if wi._truthy(values.get("is_upwork")) else "0"})
		out_rows.append(values)
	if not out_rows:
		return {"data_import": None, "skipped": skipped, "message": _("All rows were skipped")}

	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow([label for _f, label in wi.COLUMNS])
	for v in out_rows:
		w.writerow([v.get(f, "") for f, _l in wi.COLUMNS])
	stamp = frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
	file_doc = frappe.get_doc({"doctype": "File", "file_name": f"wallet-import-{stamp}.csv", "is_private": 1,
		"content": buf.getvalue().encode()}).insert(ignore_permissions=True)
	di = frappe.get_doc({"doctype": "Data Import", "reference_doctype": "SB Wallet Import",
		"import_type": "Insert New Records", "import_file": file_doc.file_url, "mute_emails": 1, "submit_after_import": 0})
	di.insert(ignore_permissions=True)
	file_doc.db_set({"attached_to_doctype": "Data Import", "attached_to_name": di.name})
	if not frappe.in_test:
		frappe.db.commit()  # the background job must see the Data Import and its file
	di.start_import()
	return {"data_import": di.name, "skipped": skipped, "rows": len(out_rows)}


@frappe.whitelist()
def csv_status(data_import: str) -> dict:
	_manager()
	di = frappe.get_doc("Data Import", data_import)
	if di.reference_doctype != "SB Wallet Import":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	logs = frappe.get_all("Data Import Log", filters={"data_import": di.name},
		fields=["success", "docname", "row_indexes", "messages", "exception"], order_by="log_index asc")
	results = frappe.get_all("SB Wallet Import", filters={"name": ("in", [l.docname for l in logs if l.docname] or [""])},
		fields=["name", "wallet_name", "result"])
	by_doc = {r.name: r for r in results}
	failed = []
	for l in logs:
		if not l.success:
			msgs = []
			for m in json.loads(l.messages or "[]"):
				msgs.append(frappe.utils.strip_html(m.get("message") if isinstance(m, dict) else str(m)))
			failed.append({"rows": json.loads(l.row_indexes or "[]"), "message": " ".join(msgs) or _("Could not import this row")})
	done = [by_doc[l.docname] for l in logs if l.success and l.docname in by_doc]
	return {
		"status": di.status, "finished": di.status in ("Success", "Partial Success", "Error", "Timed Out"),
		"created": sum(r.result == "Created" for r in done), "updated": sum(r.result == "Updated" for r in done),
		"skipped": sum((r.result or "").startswith("Skipped") for r in done),
		"wallets": [{"wallet_name": r.wallet_name, "result": r.result} for r in done], "failed": failed,
		"desk_url": f"/app/data-import/{di.name}",
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def read_pdf(file_url: str) -> dict:
	"""Bank lines from one invoice PDF, for the wallet form. Nothing is saved."""
	_manager()
	f, content = _uploaded_file(file_url)
	try:
		found = wi.bank_lines_from_text(wi.pdf_text(content))
	finally:
		f.delete(ignore_permissions=True)
	if not found["details"]:
		frappe.throw(_("No bank details were found in this PDF. If it is a scanned image, type the details in instead."),
			title=_("Nothing found"))
	return found
