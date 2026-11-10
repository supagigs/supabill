"""Import invoices into the Sales Register: CSV (many rows) or PDF/Word files (one invoice per file).

Both end in the same review and then a Frappe Data Import of SB Invoice Import rows, like the
wallet import. Managers only.
"""
from __future__ import annotations

import csv
import io
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from supabill.api.wallet_import import _check_background_jobs, _manager, _uploaded_file
from supabill.supabill import invoice_import as ii


def _load(v):
	return json.loads(v or "null") if isinstance(v, str) else v


@frappe.whitelist()
def download_template():
	_manager()
	frappe.local.response.filename = "SupaBill_invoice_import_template.csv"
	frappe.local.response.filecontent = ("﻿" + ii.template_csv()).encode()
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def review_csv(file_url: str) -> dict:
	_manager()
	_check_background_jobs()
	f, content = _uploaded_file(file_url)
	try:
		return ii.review(ii.read_csv(content))
	finally:
		f.delete(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def review_files(file_urls) -> dict:
	"""One invoice per PDF/Word file. The files are kept (private) so they can be attached to the invoices."""
	_manager()
	_check_background_jobs()
	urls = _load(file_urls) or []
	if not urls:
		frappe.throw(_("Choose at least one file"))
	if len(urls) > ii.MAX_FILES:
		frappe.throw(_("At most {0} files at a time").format(ii.MAX_FILES))
	rows, unread = [], []
	for i, url in enumerate(urls, start=1):
		f, content = _uploaded_file(url)
		try:
			text = ii.document_text(content, f.file_name)
		except frappe.ValidationError as e:
			unread.append({"file": f.file_name, "message": str(e)})
			f.delete(ignore_permissions=True)
			continue
		got = ii.extract(text)
		if not got["found"]:
			unread.append({"file": f.file_name, "message": _("No invoice details were found. Scanned (image) files have no text and cannot be read.")})
			f.delete(ignore_permissions=True)
			continue
		got["values"]["source_file"] = f.file_url
		rows.append({**got["values"], "row": i, "file": f.file_name, "_found": got["found"]})
	out = ii.review(rows)
	for r, src in zip(out["rows"], rows):
		r["found"] = src["_found"]
	out["unread"] = unread
	return out


@frappe.whitelist(methods=["POST"])
def discard_files(file_urls) -> dict:
	"""Deletes uploaded files that were not imported (review cancelled)."""
	_manager()
	n = 0
	for url in _load(file_urls) or []:
		for name in frappe.get_all("File", filters={"file_url": url, "owner": frappe.session.user,
				"attached_to_name": ("is", "not set")}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True)
			n += 1
	return {"deleted": n}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def run_import(rows) -> dict:
	"""Rows from review with the user's choices: action create / update / skip / renumber, client, wallet."""
	_manager()
	_check_background_jobs()
	rows = _load(rows) or []
	if not rows:
		frappe.throw(_("Nothing to import"))
	if len(rows) > ii.MAX_ROWS:
		frappe.throw(_("At most {0} invoices per import").format(ii.MAX_ROWS))
	existing = set(frappe.get_all("SB Invoice", pluck="name"))
	wallets = set(frappe.get_all("SB Wallet", pluck="name"))
	clients = {n.lower() for n in frappe.get_all("SB Client", pluck="name")}
	seen, out_rows, skipped, drop = set(), [], 0, []
	cols = ii.COLUMNS + ii.HIDDEN
	for r in rows:
		v = {f: str((r.get("values") or {}).get(f, "") or "") for f, _l in cols}
		action = r.get("action")
		number = (r.get("invoice_number") or v["invoice_number"]).strip()
		ref = r.get("file") or r.get("row")
		if action == "skip":
			skipped += 1
			if v["source_file"]:
				drop.append(v["source_file"])
			continue
		if action not in ("create", "update", "renumber"):
			frappe.throw(_("{0}: choose what to do").format(ref))
		if not number:
			frappe.throw(_("{0}: invoice number is required").format(ref))
		if number.lower() in seen:
			frappe.throw(_("{0}: {1} is used twice in this import").format(ref, number))
		seen.add(number.lower())
		exists = number in existing
		if action in ("create", "renumber") and exists:
			frappe.throw(_("{0}: invoice {1} already exists — choose Update, Skip or another number").format(ref, number))
		if action == "update" and not exists:
			frappe.throw(_("{0}: there is no invoice {1} to update").format(ref, number))
		if action != "update":
			wallet = (r.get("wallet") or v["wallet"]).strip()
			if wallet not in wallets:
				frappe.throw(_("{0}: choose a wallet").format(ref))
			client = (r.get("client") or "").strip()
			if client:
				if client.lower() not in clients:
					frappe.throw(_("{0}: client {1} does not exist").format(ref, client))
				v.update(client=client, create_client="0")
			else:
				if not v["client"].strip():
					frappe.throw(_("{0}: choose a client").format(ref))
				v["create_client"] = "1"
			v["wallet"] = wallet
		v.update(invoice_number=number, if_exists="Update" if action == "update" else "Skip")
		out_rows.append(v)
	for url in drop:
		ii._drop_source(frappe._dict(source_file=url))
	if not out_rows:
		return {"data_import": None, "skipped": skipped}
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow([label for _f, label in cols])
	for v in out_rows:
		w.writerow([v.get(f, "") for f, _l in cols])
	stamp = frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
	file_doc = frappe.get_doc({"doctype": "File", "file_name": f"invoice-import-{stamp}.csv", "is_private": 1,
		"content": buf.getvalue().encode()}).insert(ignore_permissions=True)
	di = frappe.get_doc({"doctype": "Data Import", "reference_doctype": "SB Invoice Import",
		"import_type": "Insert New Records", "import_file": file_doc.file_url, "mute_emails": 1}).insert(ignore_permissions=True)
	file_doc.db_set({"attached_to_doctype": "Data Import", "attached_to_name": di.name})
	if not frappe.in_test:
		frappe.db.commit()
	di.start_import()
	return {"data_import": di.name, "skipped": skipped, "rows": len(out_rows)}


@frappe.whitelist()
def import_status(data_import: str) -> dict:
	_manager()
	di = frappe.get_doc("Data Import", data_import)
	if di.reference_doctype != "SB Invoice Import":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	logs = frappe.get_all("Data Import Log", filters={"data_import": di.name},
		fields=["success", "docname", "row_indexes", "messages"], order_by="log_index asc")
	done = {r.name: r for r in frappe.get_all("SB Invoice Import", filters={
		"name": ("in", [l.docname for l in logs if l.docname] or [""])}, fields=["name", "invoice_number", "result"])}
	failed = []
	for l in logs:
		if not l.success:
			msgs = [frappe.utils.strip_html(m.get("message") if isinstance(m, dict) else str(m)) for m in json.loads(l.messages or "[]")]
			failed.append({"rows": json.loads(l.row_indexes or "[]"), "message": " ".join(msgs) or _("Could not import this row")})
	rows = [done[l.docname] for l in logs if l.success and l.docname in done]
	return {
		"status": di.status, "finished": di.status in ("Success", "Partial Success", "Error", "Timed Out"),
		"created": sum(r.result == "Created" for r in rows), "updated": sum(r.result == "Updated" for r in rows),
		"skipped": sum((r.result or "").startswith("Skipped") for r in rows),
		"invoices": [{"invoice_number": r.invoice_number, "result": r.result} for r in rows], "failed": failed,
	}
