"""Two processes create invoices at the same time; numbers must never repeat.

Run: bench --site <site> execute supabill.supabill.tests.concurrency_check.run
Creates synthetic invoices, then deletes them and restores the counter.
"""
import multiprocessing as mp

import frappe

N = 6


def _worker(site, sites_path, tag, q):
	frappe.init(site=site, sites_path=sites_path)
	frappe.connect()
	frappe.set_user("Administrator")
	from supabill.supabill.tests.fixtures import payload
	names = []
	for i in range(N):
		d = frappe.get_doc({"doctype": "SB Invoice", **payload()})
		d.insert()
		frappe.db.commit()
		names.append(d.name)
	q.put(names)
	frappe.destroy()


def run():
	from supabill.supabill.tests.fixtures import setup_basics
	setup_basics()
	frappe.db.commit()
	start = frappe.db.get_single_value("SupaBill Settings", "next_invoice_number")
	q = mp.Queue()
	procs = [mp.Process(target=_worker, args=(frappe.local.site, frappe.local.sites_path, t, q)) for t in "AB"]
	for p in procs:
		p.start()
	results = [q.get(timeout=120) for _ in procs]
	for p in procs:
		p.join()
	names = [n for r in results for n in r]
	dupes = len(names) - len(set(names))
	print(f"created {len(names)} invoices in 2 processes, duplicates: {dupes}")
	for n in names:
		frappe.delete_doc("SB Invoice", n, force=1, ignore_permissions=True)
	frappe.db.set_single_value("SupaBill Settings", "next_invoice_number", start)
	frappe.db.commit()
	assert dupes == 0, "duplicate invoice numbers"
	print("PASS: no duplicate numbers")
