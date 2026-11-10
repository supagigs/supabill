"""Synthetic demo data for a throwaway site. Bank numbers and clients are fictional.

Run: bench --site <test-site> execute supabill.supabill.tests.demo_data.load
"""
import frappe

from supabill.supabill.install import ensure_codes, ensure_roles


def load():
	ensure_roles()
	ensure_codes()
	s = frappe.get_doc("SupaBill Settings")
	s.update({
		"legal_name": "SupagigsAI Technologies Pvt. Ltd.", "display_name": "SUPAGIGS",
		"company_address": "10th Floor, Building 4, WeWork NESCO IT Park,\nWestern Express Highway, Goregaon East,\nMumbai, Maharashtra 400063",
		"company_email": "billing@example.com", "company_phone": "+91 90000 00000", "gstin": "27AAAAA0000A1Z5",
		"pan": "AAAAA0000A", "iec": "NA", "invoice_prefix": "Supa/26-27/", "number_digits": 3,
		"lut_arn": "AD270000000000T", "default_purpose_code": "P0802", "worksheet_name": "2026-27",
		"excel_enabled": 0, "ms_tenant_id": "", "ms_client_id": "", "workbook_share_link": "", "table_name": "",
		"cbic_provider": "AllRatesToday", "cbic_last_status": "", "cbic_last_sync": None,
		"excel_last_push": None, "excel_last_pull": None,
		"lut_note": "Supply meant for Export under Letter of Undertaking (ARN. {ARN}) without payment of Integrated Tax. Whether the tax is payable on the reverse charge basis – No",
	})
	from supabill.supabill.calc import format_invoice_number
	n = 28
	while frappe.db.exists("SB Invoice", format_invoice_number("Supa/26-27/", n, 3)):
		n += 1
	s.next_invoice_number = n
	s.flags.ignore_permissions = True
	s.save()
	wallets = {
		"Briskpe": [("Beneficiary Name", "SUPAGIGS"), ("Account Number", "000111222333"), ("ACH Routing Code", "000000000"),
			("Account Type", "Checking"), ("Bank Name", "Demo Community Bank"), ("Bank Address", "1 Demo Plaza, New York, NY 10001, US"),
			("Bank Country", "United States")],
		"Skydo": [("Beneficiary Name", "SUPAGIGS"), ("Account Number", ""), ("SWIFT", "")],
	}
	for name, rows in wallets.items():
		if not frappe.db.exists("SB Wallet", name):
			frappe.get_doc({"doctype": "SB Wallet", "wallet_name": name, "details": [{"label": a, "value": b} for a, b in rows]}).insert()
	if not frappe.db.exists("SB Wallet", "Upwork"):
		frappe.get_doc({"doctype": "SB Wallet", "wallet_name": "Upwork", "is_upwork": 1}).insert()
	clients = [
		{"client_name": "Northwind Rentals", "address": "700 Harbor Street\nStamford, CT 06902, United States", "country": "United States",
			"contact_person": "Jamie Rivera", "email": "ap@northwind.example", "project": "Custom Reporting and Automation",
			"currency": "USD", "payment_terms_days": 21, "wallet": "Briskpe", "purpose_code": "P0802", "sac_code": "998313",
			"last_milestone": "Milestone 2 of 3", "last_billing_period": "1 Oct – 9 Oct 2026", "last_amount": 1972.42},
		{"client_name": "Contoso Books", "address": "12 Fleet Lane\nLondon EC4A 1AA, United Kingdom", "country": "United Kingdom",
			"contact_person": "Priya Shah", "email": "finance@contoso.example", "project": "Monthly bookkeeping", "currency": "USD",
			"payment_terms_days": 15, "wallet": "Briskpe", "purpose_code": "P1005", "sac_code": "998222",
			"last_milestone": "Monthly bookkeeping", "last_billing_period": "Oct 2026", "last_amount": 450},
	]
	for c in clients:
		if not frappe.db.exists("SB Client", c["client_name"]):
			frappe.get_doc({"doctype": "SB Client", **c}).insert()
	for d, r in (("2026-10-03", 87.85), ("2026-10-17", 88.10), ("2026-11-07", 88.45)):
		if not frappe.db.exists("SB CBIC Rate", f"USD-{d}"):
			frappe.get_doc({"doctype": "SB CBIC Rate", "currency": "USD", "effective_from": d, "export_rate": r,
				"source": "Sample"}).insert()
	frappe.db.commit()
	print("demo data loaded")
