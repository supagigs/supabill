"""Wallet import: CSV rows (one per wallet) and bank details read from an invoice PDF.

Both feed the same wallet structure used by the Wallets form: a name, flags and a list of
bank lines (label + value). Nothing here writes a wallet except ``apply_row``.
"""
from __future__ import annotations

import csv
import io
import re

import frappe
from frappe import _

# CSV column → bank line label. The first seven are the wallet form's standard lines and are
# always written (blank values show as "details missing"); the rest only when filled.
STANDARD = [
	("beneficiary_name", "Beneficiary Name"),
	("account_number", "Account Number"),
	("routing_swift_code", "Routing / SWIFT Code"),
	("account_type", "Account Type"),
	("bank_name", "Bank Name"),
	("bank_address", "Bank Address"),
	("bank_country", "Bank Country"),
]
OPTIONAL = [("iban", "IBAN"), ("ifsc_code", "IFSC Code")]
META = [("wallet_name", "Wallet Name"), ("if_exists", "If Wallet Exists"), ("is_upwork", "Paid via Upwork"),
	("settles_to", "Settles To")]
COLUMNS = META + STANDARD + OPTIONAL + [("other_details", "Other Details")]
MAX_ROWS = 500
MAX_PDF_BYTES = 10 * 1024 * 1024


def template_csv() -> str:
	buf = io.StringIO()
	csv.writer(buf).writerow([label for _f, label in COLUMNS])
	return buf.getvalue()


def _truthy(v) -> int:
	return 1 if str(v or "").strip().lower() in ("1", "yes", "y", "true") else 0


def parse_other(text: str) -> list[dict]:
	out = []
	for line in (text or "").replace("\r", "").split("\n"):
		label, sep, value = line.partition(":")
		if sep and label.strip():
			out.append({"label": label.strip(), "value": value.strip()})
	return out


def details_from_row(row: dict) -> list[dict]:
	"""Bank lines for a wallet, in the wallet form's order."""
	if row.get("is_upwork") and not any((row.get(f) or "").strip() for f, _l in STANDARD + OPTIONAL):
		return []
	lines = [{"label": label, "value": (row.get(f) or "").strip()} for f, label in STANDARD]
	lines += [{"label": label, "value": (row.get(f) or "").strip()} for f, label in OPTIONAL if (row.get(f) or "").strip()]
	seen = {l["label"].lower() for l in lines}
	for extra in parse_other(row.get("other_details")):
		if extra["label"].lower() not in seen:
			lines.append(extra)
			seen.add(extra["label"].lower())
	return lines


def read_csv(content: bytes | str) -> list[dict]:
	"""Rows keyed by field name. Headers match the template labels (case and spacing ignored)."""
	text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("﻿")
	rows = list(csv.reader(io.StringIO(text)))
	if not rows:
		frappe.throw(_("The file is empty"))
	norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
	by_label = {norm(label): f for f, label in COLUMNS} | {norm(f): f for f, _l in COLUMNS}
	header = [by_label.get(norm(h)) for h in rows[0]]
	if "wallet_name" not in header:
		frappe.throw(_("The file has no “Wallet Name” column. Download the template and keep its header row."))
	unknown = [h for h, f in zip(rows[0], header) if h.strip() and not f]
	out = []
	for i, r in enumerate(rows[1:], start=2):
		if not any(c.strip() for c in r):
			continue
		row = {f: (r[j].strip() if j < len(r) else "") for j, f in enumerate(header) if f}
		row["row"] = i
		out.append(row)
	if len(out) > MAX_ROWS:
		frappe.throw(_("At most {0} wallets per file").format(MAX_ROWS))
	if unknown:
		frappe.msgprint(_("Ignored columns: {0}").format(", ".join(unknown)), alert=True)
	return out


def review(rows: list[dict]) -> list[dict]:
	"""Marks each row new / exists / error so the user can choose Skip, Update or a new name."""
	existing = {n.lower(): n for n in frappe.get_all("SB Wallet", pluck="name")}
	counts: dict[str, int] = {}
	for r in rows:
		key = (r.get("wallet_name") or "").strip().lower()
		counts[key] = counts.get(key, 0) + 1
	out = []
	for r in rows:
		name = (r.get("wallet_name") or "").strip()
		errors = []
		if not name:
			errors.append(_("Wallet name is missing"))
		elif counts[name.lower()] > 1:
			errors.append(_("The name {0} appears more than once in this file — rename one of them").format(name))
		elif len(name) > 140:
			errors.append(_("Wallet name is too long"))
		details = details_from_row({**r, "is_upwork": _truthy(r.get("is_upwork"))})
		labels = [d["label"].lower() for d in details]
		if len(labels) != len(set(labels)):
			errors.append(_("A bank line label appears twice"))
		match = existing.get(name.lower()) if name else None
		out.append({
			"row": r.get("row"), "wallet_name": name, "is_upwork": _truthy(r.get("is_upwork")),
			"settles_to": r.get("settles_to") or "", "details": details,
			"status": "error" if errors else ("exists" if match else "new"), "existing": match,
			"action": "update" if match and (r.get("if_exists") or "").lower() == "update" else ("skip" if match else "create"),
			"errors": errors, "values": {f: r.get(f, "") for f, _l in COLUMNS},
		})
	return out


def merge_details(current: list[dict], incoming: list[dict]) -> list[dict]:
	"""Update rule: a filled imported value replaces the line with the same label; a blank one keeps the current value."""
	out = [{"label": d["label"], "value": d.get("value") or ""} for d in current]
	index = {d["label"].strip().lower(): d for d in out}
	for d in incoming:
		key = d["label"].strip().lower()
		if key in index:
			if (d.get("value") or "").strip():
				index[key]["value"] = d["value"].strip()
		elif (d.get("value") or "").strip():  # blank new lines are not added, so a complete wallet stays complete
			line = {"label": d["label"].strip(), "value": d["value"].strip()}
			out.append(line)
			index[key] = line
	return out


def apply_row(doc) -> None:
	"""Called on insert of an SB Wallet Import row (from Data Import): creates, updates or skips."""
	name = (doc.wallet_name or "").strip()
	if not name:
		frappe.throw(_("Wallet name is required"))
	row = doc.as_dict()
	details = details_from_row(row)
	existing = frappe.db.get_value("SB Wallet", name)
	if existing:
		if (doc.if_exists or "Skip") != "Update":
			doc.result, doc.wallet = "Skipped (exists)", existing
			return
		w = frappe.get_doc("SB Wallet", existing)
		if doc.is_upwork:
			w.is_upwork = 1
		if doc.settles_to:
			w.settles_to = doc.settles_to
		w.set("details", merge_details([d.as_dict() for d in w.details], details))
		w.save()
		doc.result, doc.wallet = "Updated", w.name
		return
	w = frappe.new_doc("SB Wallet")
	w.update({"wallet_name": name, "is_upwork": doc.is_upwork,
		"settles_to": doc.settles_to or frappe.db.get_single_value("SupaBill Settings", "ad_bank_name") or ""})
	w.set("details", details)
	w.insert()
	doc.result, doc.wallet = "Created", w.name


# ---------------- PDF ----------------

HEADING = re.compile(r"^\s*(bank(ing)?\s+(transfer\s+|account\s+|payment\s+|wire\s+)?(details|information|info)|payment\s+(details|information|instructions)|remit(tance)?\s+(to|details|information)|wire\s+(transfer\s+)?(details|instructions))\s*:?\s*$", re.I)
BANK_LABEL = re.compile(r"(beneficiary|account|a/c|acct|bank|branch|routing|aba|ach|swift|bic|iban|ifsc|sort\s*code|bsb|transit|institution|payee|receiver|intermediary|wire|micr)", re.I)
STOP = re.compile(r"^\s*(notes?|terms|thank|total|sub\s*total|invoice|bill\s+to|from|signature|authori[sz]ed|declaration)\b", re.I)


def _is_heading(line: str) -> bool:
	s = line.strip()
	return bool(s) and ":" not in s and (s.isupper() or HEADING.match(s)) and len(s) < 60


def pdf_text(content: bytes) -> str:
	import pypdf
	if len(content) > MAX_PDF_BYTES:
		frappe.throw(_("The PDF is larger than 10 MB"))
	if not content.startswith(b"%PDF"):
		frappe.throw(_("This is not a PDF file"))
	try:
		reader = pypdf.PdfReader(io.BytesIO(content))
		if reader.is_encrypted:
			reader.decrypt("")
		return "\n".join((p.extract_text() or "") for p in reader.pages[:10])
	except Exception:
		frappe.throw(_("The PDF could not be read. Is it password-protected or damaged?"))


def bank_lines_from_text(text: str) -> dict:
	"""Finds bank lines (Label: value). Prefers a 'Bank details' block; otherwise keeps bank-like labels only."""
	lines = [l.rstrip() for l in (text or "").replace("\r", "").split("\n")]
	start = next((i for i, l in enumerate(lines) if HEADING.match(l.strip())), None)
	found: list[dict] = []
	if start is not None:
		block = []
		for l in lines[start + 1:]:
			s = l.strip()
			if not s:
				continue
			if (_is_heading(s) and not HEADING.match(s)) or STOP.match(s) or "|" in s:
				break
			block.append(s)
		found = _pairs(block, bank_only=False)
	if not found:
		found = _pairs([l.strip() for l in lines if l.strip()], bank_only=True)
	seen, out = set(), []
	for d in found:
		k = d["label"].lower()
		if k not in seen and d["value"]:
			seen.add(k)
			out.append(d)
	return {"details": out, "block_found": start is not None}


def _pairs(block: list[str], bank_only: bool) -> list[dict]:
	out: list[dict] = []
	pending_label = None
	for s in block:
		label, sep, value = s.partition(":")
		label, value = label.strip(), value.strip()
		if sep and 0 < len(label) <= 40 and not re.search(r"https?$", label, re.I):
			if bank_only and not BANK_LABEL.search(label):
				pending_label = None
				continue
			if value:
				out.append({"label": label, "value": value})
				pending_label = None
			else:
				pending_label = label
		elif pending_label:
			out.append({"label": pending_label, "value": s})
			pending_label = None
		elif out and not bank_only:
			out[-1]["value"] = f"{out[-1]['value']} {s}".strip()  # wrapped value, e.g. a long address
	return out
