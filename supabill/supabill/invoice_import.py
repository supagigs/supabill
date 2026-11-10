"""Bulk import of past invoices into the Sales Register.

Same approach and rules as the wallet import:
- CSV: template with one row per invoice, review screen, then Frappe Data Import on the staging
  DocType SB Invoice Import.
- PDF / Word: values are found by keywords printed on the invoice ("Invoice No", "Bill To",
  "Total Due", …). There is no OCR and no AI: a scanned PDF has no text and cannot be read.
- A number that already exists: Skip, Update (register columns only; blank cells keep current
  values) or import under another number — chosen per row in the review.
"""
from __future__ import annotations

import csv
import io
import re

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from supabill.supabill import wallet_import as wi
from supabill.supabill.doctype.sb_invoice.sb_invoice import REGISTER_FIELDS

COLUMNS = [
	("invoice_number", "Invoice Number"), ("if_exists", "If Invoice Exists"), ("invoice_date", "Invoice Date"),
	("due_date", "Due Date"), ("client", "Client"), ("create_client", "Create Client If Missing"),
	("client_address", "Client Address"), ("client_country", "Client Country"), ("client_email", "Client Email"),
	("attention", "Attention"), ("currency", "Currency"), ("amount", "Amount Before Tax"),
	("tax_treatment", "Tax Treatment"), ("total", "Total As Printed"), ("description", "Description"),
	("sac_code", "SAC Code"), ("hsn_code", "HSN Code"), ("purpose_code", "Purpose Code"), ("wallet", "Wallet"),
	("project", "Project"), ("milestone", "Milestone"), ("billing_period", "Billing Period"),
	("cbic_rate", "CBIC Rate"), ("wallet_reference", "Wallet Reference"), ("upwork_invoice", "Upwork Invoice"),
	("upwork_account_holder", "Upwork Account Holder"), ("received_inr", "Received (INR)"),
	("bank_charges_usd", "Bank Charges ($)"), ("bank_charges_inr", "Bank Charges (Rs)"),
	("payment_status", "Payment Status"), ("invoice_status", "Invoice Status"), ("irm_number", "IRM Number"),
	("edpms_status", "EDPMS Status"), ("bank_details", "Bank Details As Printed"),
]
TEMPLATE_COLUMNS = [c for c in COLUMNS if c[0] != "bank_details"]
HIDDEN = [("source_file", "Source File")]  # set by PDF/Word imports only
MAX_ROWS = 500
MAX_FILES = 50
TAXES = {"lut": "Export under LUT", "export under lut": "Export under LUT", "igst": "IGST 18%", "igst 18%": "IGST 18%",
	"cgst": "CGST + SGST 9+9", "cgst + sgst": "CGST + SGST 9+9", "cgst + sgst 9+9": "CGST + SGST 9+9"}
PAY = {"pending": "Pending", "partially received": "Partially received", "partial": "Partially received", "received": "Received"}
INV_STATUS = {"raised": "Raised", "sent": "Sent"}
NUM_FIELDS = ("received_inr", "bank_charges_usd", "bank_charges_inr")


def template_csv() -> str:
	buf = io.StringIO()
	csv.writer(buf).writerow([label for _f, label in TEMPLATE_COLUMNS])
	return buf.getvalue()


def _norm(s: str) -> str:
	return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def read_csv(content: bytes | str) -> list[dict]:
	text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("﻿")
	rows = list(csv.reader(io.StringIO(text)))
	if not rows:
		frappe.throw(_("The file is empty"))
	by = {_norm(label): f for f, label in COLUMNS} | {_norm(f): f for f, _l in COLUMNS}
	header = [by.get(_norm(h)) for h in rows[0]]
	if "invoice_number" not in header:
		frappe.throw(_("The file has no “Invoice Number” column. Download the template and keep its header row."))
	out = []
	for i, r in enumerate(rows[1:], start=2):
		if not any(c.strip() for c in r):
			continue
		row = {f: (r[j].strip() if j < len(r) else "") for j, f in enumerate(header) if f}
		row["row"] = i
		out.append(row)
	if len(out) > MAX_ROWS:
		frappe.throw(_("At most {0} invoices per file").format(MAX_ROWS))
	return out


# ---------------- values ----------------

def parse_amount(v) -> float | None:
	s = str(v or "").strip()
	if not s:
		return None
	neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
	s = re.sub(r"[^0-9.,]", "", s)
	if not s:
		return None
	if "," in s and "." not in s and re.search(r",\d{2}$", s):  # 1.234,56 style without dots
		s = s.replace(",", ".")
	s = s.replace(",", "")
	try:
		n = float(s)
	except ValueError:
		return None
	return -n if neg else n


def parse_date(v):
	"""Day first (Indian style) for numeric dates; month names in any order."""
	s = str(v or "").strip()
	if not s:
		return None
	from dateutil import parser
	try:
		if re.match(r"^\d{4}-\d{2}-\d{2}", s):
			return getdate(s[:10])
		return parser.parse(s, dayfirst=True, fuzzy=True).date()
	except (ValueError, OverflowError):
		return None


def _country(v: str) -> str | None:
	if not v:
		return None
	name = frappe.db.get_value("Country", {"name": v.strip()}) or frappe.db.get_value("Country", {"code": v.strip().lower()})
	aliases = {"usa": "United States", "us": "United States", "u.s.a.": "United States", "united states of america": "United States",
		"uk": "United Kingdom", "u.k.": "United Kingdom", "uae": "United Arab Emirates"}
	return name or aliases.get(v.strip().lower())


# ---------------- review ----------------

def _wallets() -> dict:
	out = {}
	for w in frappe.get_all("SB Wallet", fields=["name"]):
		out[w.name] = {d.label.lower(): (d.value or "") for d in frappe.get_all("SB Wallet Detail",
			filters={"parent": w.name, "parenttype": "SB Wallet"}, fields=["label", "value"])}
	return out


def match_wallet(name: str, bank_details: str, wallets: dict) -> str | None:
	"""By wallet name, else by an account number / IBAN printed in the bank details."""
	if name:
		hit = next((w for w in wallets if w.lower() == name.strip().lower()), None)
		if hit:
			return hit
	norm = lambda x: re.sub(r"[\s-]", "", x or "").upper()  # noqa: E731
	printed = {norm(l.partition(":")[2]) for l in (bank_details or "").split("\n") if ":" in l}
	printed.discard("")
	if not printed:
		return None
	for w, details in wallets.items():
		for label, value in details.items():
			if any(k in label for k in ("account", "iban", "a/c")) and "type" not in label and "name" not in label:
				if len(norm(value)) >= 3 and norm(value) in printed:
					return w
	return None


def review(rows: list[dict]) -> dict:
	clients = {n.lower(): n for n in frappe.get_all("SB Client", pluck="name")}
	existing = set(frappe.get_all("SB Invoice", filters={"docstatus": ("<", 2)}, pluck="name"))
	wallets = _wallets()
	counts: dict[str, int] = {}
	for r in rows:
		k = (r.get("invoice_number") or "").strip().lower()
		counts[k] = counts.get(k, 0) + 1
	out = []
	for r in rows:
		v = {f: (r.get(f) or "") for f, _l in COLUMNS + HIDDEN}
		number = v["invoice_number"].strip()
		errors, warnings = [], []
		date = parse_date(v["invoice_date"])
		amount = parse_amount(v["amount"])
		currency = v["currency"].strip().upper()
		tax = TAXES.get(v["tax_treatment"].strip().lower(), "" if v["tax_treatment"].strip() else "Export under LUT")
		if not number:
			errors.append(_("Invoice number is missing"))
		elif counts[number.lower()] > 1:
			errors.append(_("{0} appears more than once in this import — give one of them another number").format(number))
		if not date:
			errors.append(_("Invoice date is missing or not a date"))
		if not amount or amount <= 0:
			errors.append(_("Amount before tax is missing"))
		if not currency or not frappe.db.exists("Currency", currency):
			errors.append(_("Currency is missing or unknown"))
		if not tax:
			errors.append(_("Tax treatment must be Export under LUT, IGST 18% or CGST + SGST 9+9"))
		client = clients.get(v["client"].strip().lower()) if v["client"].strip() else None
		if not v["client"].strip():
			errors.append(_("Client is missing"))
		elif not client and not (v["client_address"] or "").strip():
			warnings.append(_("New client has no address — add one in the file or pick an existing client"))
		wallet = match_wallet(v["wallet"], v["bank_details"], wallets)
		if not wallet:
			errors.append(_("Choose the wallet (none matched “{0}”)").format(v["wallet"] or _("the bank details")))
		country = _country(v["client_country"]) if v["client_country"] else None
		if v["client_country"] and not country:
			warnings.append(_("Country “{0}” is not recognised and will be left blank").format(v["client_country"]))
		total = parse_amount(v["total"])
		if amount and total and tax:
			rate = {"Export under LUT": 0, "IGST 18%": 0.18, "CGST + SGST 9+9": 0.18}[tax]
			if abs(round(amount * (1 + rate), 2) - total) > 0.05:
				warnings.append(_("Printed total {0} differs from the calculated {1}").format(f"{total:,.2f}", f"{amount * (1 + rate):,.2f}"))
		for f in NUM_FIELDS:
			if v[f] and parse_amount(v[f]) is None:
				errors.append(_("{0} is not a number").format(dict(COLUMNS)[f]))
		if v["payment_status"] and v["payment_status"].strip().lower() not in PAY:
			errors.append(_("Payment status must be Pending, Partially received or Received"))
		exists = number in existing
		action = ("update" if (v["if_exists"] or "").lower() == "update" else "skip") if exists else "create"
		v.update({"invoice_number": number, "invoice_date": str(date) if date else v["invoice_date"],
			"amount": f"{amount:.2f}" if amount else v["amount"], "currency": currency, "tax_treatment": tax or v["tax_treatment"],
			"client_country": country or "", "wallet": wallet or ""})
		out.append({"row": r.get("row"), "file": r.get("file"), "invoice_number": number, "original": number,
			"status": "exists" if exists else "new", "action": action, "client": client or "",
			"client_label": v["client"].strip(), "new_client": not client, "wallet": wallet or "",
			"errors": errors, "warnings": warnings, "values": v,
			"summary": {"date": v["invoice_date"], "amount": amount, "currency": currency, "tax": tax, "total": total}})
	return {"rows": out, "existing_numbers": sorted(existing), "clients": sorted(clients.values()), "wallets": sorted(wallets)}


# ---------------- apply (from Data Import) ----------------

def _register_values(doc) -> dict:
	out = {}
	for f in ("wallet_reference", "upwork_invoice", "upwork_account_holder", "irm_number"):
		if (doc.get(f) or "").strip():
			out[f] = doc.get(f).strip()
	for f in NUM_FIELDS:
		n = parse_amount(doc.get(f))
		if n is not None:
			out[f] = n
	if (doc.payment_status or "").strip():
		out["payment_status"] = PAY[doc.payment_status.strip().lower()]
	if (doc.invoice_status or "").strip().lower() in INV_STATUS:
		out["invoice_status"] = INV_STATUS[doc.invoice_status.strip().lower()]
	if (doc.edpms_status or "").strip().title() in ("Open", "Closed"):
		out["edpms_status"] = doc.edpms_status.strip().title()
	if (doc.description or "").strip():
		out["register_description"] = doc.description.strip()[:140]
	return {k: v for k, v in out.items() if k in REGISTER_FIELDS}


def _client(doc) -> str:
	name = frappe.db.get_value("SB Client", {"client_name": doc.client.strip()}) or frappe.db.get_value("SB Client", doc.client.strip())
	if name:
		return name
	if not cint(doc.create_client):
		frappe.throw(_("Client {0} does not exist. Choose an existing client or tick Create Client If Missing.").format(doc.client))
	c = frappe.get_doc({"doctype": "SB Client", "client_name": doc.client.strip(), "address": doc.client_address,
		"country": _country(doc.client_country), "email": (doc.client_email or "").strip() or None,
		"contact_person": doc.attention, "currency": doc.currency, "wallet": doc.wallet,
		"tax_treatment": TAXES.get((doc.tax_treatment or "").lower()), "purpose_code": doc.purpose_code or None,
		"sac_code": doc.sac_code, "project": doc.project}).insert()
	return c.name


def apply_row(doc) -> None:
	"""Called on insert of an SB Invoice Import row: creates, updates register columns, or skips."""
	number = (doc.invoice_number or "").strip()
	if not number:
		frappe.throw(_("Invoice number is required"))
	existing = frappe.db.get_value("SB Invoice", {"name": number, "docstatus": ("<", 2)})
	if existing:
		if (doc.if_exists or "Skip") != "Update":
			doc.result, doc.invoice = "Skipped (exists)", existing
			_drop_source(doc)
			return
		inv = frappe.get_doc("SB Invoice", existing)
		if inv.docstatus != 1:
			frappe.throw(_("{0} is not a submitted invoice").format(existing))
		values = _register_values(doc)
		values.pop("register_description", None)  # keep the existing description on updates
		for k, v in values.items():
			inv.set(k, v)
		inv.save()
		doc.result, doc.invoice = "Updated", inv.name
		_drop_source(doc)
		return
	if frappe.db.exists("SB Invoice", number):
		frappe.throw(_("{0} belongs to a cancelled invoice; import it under another number").format(number))
	date = parse_date(doc.invoice_date)
	due = parse_date(doc.due_date)
	tax = TAXES.get((doc.tax_treatment or "").strip().lower(), "Export under LUT")
	inv = frappe.new_doc("SB Invoice")
	inv.flags.import_name = number
	inv.update({
		"client": _client(doc), "invoice_date": date, "payment_terms_days": max(date_diff(due, date), 0) if due else 0,
		"currency": doc.currency.strip().upper(), "wallet": doc.wallet, "tax_treatment": tax,
		"purpose_code": doc.purpose_code or None, "project": doc.project, "milestone": doc.milestone,
		"billing_period": doc.billing_period, "imported": 1, "bank_details": doc.bank_details or None,
	})
	for f, src in (("billing_address", "client_address"), ("client_email", "client_email"), ("attention", "attention")):
		if (doc.get(src) or "").strip():
			inv.set(f, doc.get(src).strip())
	country = _country(doc.client_country)
	if country:
		inv.client_country = country
	if flt(doc.cbic_rate) > 0:
		inv.cbic_rate, inv.cbic_rate_source = flt(doc.cbic_rate), "Manual"
	inv.append("items", {"description": (doc.description or doc.project or _("Imported invoice")).strip(),
		"sac_code": doc.sac_code, "hsn_code": doc.hsn_code, "qty": 1, "rate": flt(doc.amount, 2)})
	inv.update(_register_values(doc))
	inv.insert()
	inv.submit()
	if doc.source_file:
		f = frappe.get_doc("File", {"file_url": doc.source_file})
		f.db_set({"attached_to_doctype": "SB Invoice", "attached_to_name": inv.name})
		inv.db_set("original_file", doc.source_file, update_modified=False)
	doc.result, doc.invoice = "Created", inv.name


def _drop_source(doc):
	if doc.source_file:
		for name in frappe.get_all("File", filters={"file_url": doc.source_file, "attached_to_name": ("is", "not set")}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True)


# ---------------- PDF / Word keywords ----------------

LABELS = {
	"invoice_number": r"invoice\s*(?:no\.?|number|num|#)|inv(?:oice)?\.?\s*#|bill\s*(?:no\.?|number)",
	"invoice_date": r"invoice\s*date|date\s*of\s*(?:issue|invoice)|issue\s*date|dated|billing\s*date",
	"due_date": r"due\s*date|payment\s*due|due\s*by|pay\s*by",
	"currency": r"currency",
	"purpose_code": r"purpose\s*code",
	"subtotal": r"sub\s*-?\s*total|amount\s*before\s*tax|taxable\s*(?:value|amount)",
	"total": r"total\s*due|grand\s*total|total\s*amount|amount\s*due|balance\s*due|invoice\s*total|total\s*payable",
	"upwork_invoice": r"upwork\s*invoice",
	"billing_period": r"billing\s*period|service\s*period|period",
	"email": r"e-?mail",
	"attention": r"attn\.?|attention|contact\s*person",
}
BILL_TO = re.compile(r"^\s*(bill(?:ed)?\s*to|invoice\s*to|sold\s*to|customer|client)\s*:?\s*(.*)$", re.I)
BLOCK_END = re.compile(r"^\s*(attn|attention|e-?mail|phone|tel|contact|gstin|vat|tax\s*id|project|invoice|ship\s*to|from|payment|#|item|description)\b", re.I)
CUR_SIGNS = [("₹", "INR"), ("Rs", "INR"), ("€", "EUR"), ("£", "GBP"), ("A$", "AUD"), ("C$", "CAD"), ("$", "USD")]
CODES = ("USD", "INR", "EUR", "GBP", "AUD", "CAD", "SGD", "AED", "CHF", "JPY", "NZD")


def document_text(content: bytes, filename: str) -> str:
	name = (filename or "").lower()
	if name.endswith(".pdf"):
		return wi.pdf_text(content)
	if name.endswith(".docx"):
		from docx import Document as Docx
		try:
			d = Docx(io.BytesIO(content))
		except Exception:
			frappe.throw(_("{0} could not be read as a Word file").format(filename))
		lines = [p.text for p in d.paragraphs]

		def walk(tables):
			for t in tables:
				for row in t.rows:
					seen = []
					for cell in row.cells:
						if cell._tc in seen:  # merged cells repeat
							continue
						seen.append(cell._tc)
						lines.extend(p.text for p in cell.paragraphs)
						walk(cell.tables)  # nested tables (e.g. the invoice details block)
		walk(d.tables)
		for s in d.sections:
			lines.extend(p.text for p in s.footer.paragraphs)
		return "\n".join(x for l in lines for x in l.split("\n"))
	frappe.throw(_("{0}: only PDF and Word (.docx) files can be read").format(filename))


def _after_label(lines: list[str], pattern: str, need: str | None = None) -> str | None:
	"""Value on the same line after the label (with or without a colon), or on the next line.
	With ``need`` (a regex), a same-line value that does not match it (e.g. "(USD)") is joined with the next line."""
	rx = re.compile(rf"(?:^|\b)(?:{pattern})(?![A-Za-z])\s*[:\-–]?\s*(.*)$", re.I)
	for i, l in enumerate(lines):
		m = rx.search(l)
		if not m:
			continue
		v = m.group(1).strip(" :\t")
		if v and need and not re.search(need, v):
			nxt = next((x.strip() for x in lines[i + 1:i + 3] if x.strip()), "")
			return f"{v} {nxt}" if re.search(need, nxt) else v
		if v:
			return v
		nxt = next((x.strip() for x in lines[i + 1:i + 3] if x.strip()), "")
		if nxt and not re.search(r":\s*$", nxt):
			return nxt
	return None


def _money(s: str | None) -> tuple[float | None, str | None]:
	if not s:
		return None, None
	cur = next((c for c in CODES if re.search(rf"\b{c}\b", s)), None)
	if not cur:
		cur = next((code for sign, code in CUR_SIGNS if sign in s), None)
	m = re.search(r"\(?-?[\d][\d,]*(?:\.\d+)?\)?", s.replace(" ", ""))
	return (parse_amount(m.group(0)) if m else None), cur


def extract(text: str) -> dict:
	"""Invoice fields found by keyword. Every value is shown in the review before anything is saved."""
	lines = [l.strip() for l in (text or "").replace("\r", "").split("\n")]
	nonblank = [l for l in lines if l]
	v: dict[str, str] = {}
	found: list[str] = []

	def put(field, value, label):
		if value not in (None, "") and not v.get(field):
			v[field] = str(value).strip()
			found.append(label)

	num = _after_label(nonblank, LABELS["invoice_number"])
	if num:
		put("invoice_number", num.split()[0].strip(".,;"), "Invoice No")
	d = _after_label(nonblank, LABELS["invoice_date"])
	put("invoice_date", parse_date(d) if d else None, "Invoice date")
	dd = _after_label(nonblank, LABELS["due_date"])
	put("due_date", parse_date(dd) if dd else None, "Due date")
	cur = _after_label(nonblank, LABELS["currency"])
	if cur:
		code = next((c for c in CODES if c in cur.upper()), None)
		put("currency", code, "Currency")
	pc = _after_label(nonblank, LABELS["purpose_code"])
	if pc:
		m = re.search(r"\bP\d{4}\b", pc.upper())
		put("purpose_code", m.group(0) if m else None, "Purpose code")
	sac = re.search(r"\b(99\d{4})\b", text or "")
	put("sac_code", sac.group(1) if sac else None, "SAC code")
	total, tcur = _money(_after_label(nonblank, LABELS["total"], need=r"\d"))
	sub, scur = _money(_after_label(nonblank, LABELS["subtotal"], need=r"\d"))
	put("total", f"{total:.2f}" if total else None, "Total")
	put("currency", tcur or scur, "Currency (from total)")
	low = (text or "").lower()
	if "letter of undertaking" in low or re.search(r"\blut\b", low):
		tax = "Export under LUT"
	elif re.search(r"\bcgst\b", low) and re.search(r"\bsgst\b", low):
		tax = "CGST + SGST 9+9"
	elif re.search(r"\bigst\b", low) and not re.search(r"igst[^\n]{0,20}\b0(\.0+)?\s*%", low):
		tax = "IGST 18%"
	else:
		tax = "Export under LUT" if (v.get("currency") or "INR") != "INR" else ""
	put("tax_treatment", tax, "Tax treatment")
	rate = {"Export under LUT": 0, "IGST 18%": 0.18, "CGST + SGST 9+9": 0.18}.get(tax, 0)
	amount = sub or (round(total / (1 + rate), 2) if total else None)
	put("amount", f"{amount:.2f}" if amount else None, "Amount" if sub else "Amount (from total)")
	put("upwork_invoice", _after_label(nonblank, LABELS["upwork_invoice"]), "Upwork invoice")

	# Bill-to block: name on the first line, address until contact lines or the next heading
	for i, l in enumerate(nonblank):
		m = BILL_TO.match(l)
		if not m:
			continue
		block = ([m.group(2).strip()] if m.group(2).strip() else []) + nonblank[i + 1:i + 9]
		name, addr = None, []
		for b in block:
			if BLOCK_END.match(b) or (b.isupper() and len(b) < 40 and not name is None and ":" not in b and len(addr) > 0):
				break
			if name is None:
				name = b
			else:
				addr.append(b)
		put("client", name, "Bill to")
		if addr:
			put("client_address", "\n".join(addr[:5]), "Client address")
			for a in reversed(addr):
				c = _country(a.split(",")[-1].strip()) or _country(a)
				if c:
					put("client_country", c, "Client country")
					break
		for b in block:
			if re.match(r"^\s*(attn|attention)\b", b, re.I):
				put("attention", b.split(":", 1)[-1].strip(), "Attention")
			em = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", b)
			if em:
				put("client_email", em.group(0), "Client email")
		break
	# Project / milestone / billing period (as SupaBill prints them)
	for i, l in enumerate(nonblank):
		if re.match(r"^project(\s*&\s*payment)?\s*:?$", l, re.I) and i + 1 < len(nonblank):
			nxt = nonblank[i + 1]
			if "billing period:" not in nxt.lower() and not re.match(r"^payment\b", nxt, re.I):
				put("project", nxt, "Project")
				nxt = nonblank[i + 2] if i + 2 < len(nonblank) else ""
			ms, _sep, per = nxt.partition("Billing period:")
			ms = ms.strip(" –-")
			if ms and ":" not in ms:
				put("milestone", ms, "Milestone")
			put("billing_period", per.strip(), "Billing period")
			break
	if not v.get("billing_period"):
		put("billing_period", _after_label(nonblank, r"billing\s*period"), "Billing period")
	# Line description: the row after the items header (#, Description …)
	for i, l in enumerate(nonblank):
		if not re.search(r"\b(item\s*description|description)\b", l, re.I):
			continue
		for j in range(i + 1, min(i + 12, len(nonblank))):  # first item row starts with "1"
			cur = nonblank[j]
			if re.match(r"^(sub\s*-?\s*total|total)", cur, re.I):
				break
			m = re.match(r"^1(?:\s+(.*)|$)", cur)
			if not m:
				continue
			desc = m.group(1) or (nonblank[j + 1] if j + 1 < len(nonblank) else "")
			if re.search(r"[–-]\s*$", desc) and j + 1 < len(nonblank) and m.group(1):
				desc = desc.rstrip() + " " + nonblank[j + 1]  # wrapped on two lines
			desc = re.split(r"\s(?:99\d{4})\b|\s[\$₹€£]\s?\d|\s\d[\d,]*\.\d{2}\b", desc)[0].strip()
			desc = re.sub(r"\s+\d+(?:\.\d+)?$", "", desc).strip(" –-")  # trailing quantity column
			if desc:
				put("description", desc, "Description")
			break
		break
	bank = wi.bank_lines_from_text(text)
	if bank["details"]:
		v["bank_details"] = "\n".join(f"{d['label']}: {d['value']}" for d in bank["details"])
		found.append("Bank details")
	return {"values": v, "found": found}
