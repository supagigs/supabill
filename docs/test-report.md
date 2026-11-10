# SupaBill test report

## 1.3.0rc1 — Invoice import (10 Nov 2026)

| Check | Result |
|---|---|
| Backend tests incl. 12 new (`test_invoice_import.py`): template, values (amounts, day-first dates), create through Data Import with the counter untouched, update / skip / renumber, unresolved clash refused, new client, review errors, SupaBill PDF and DOCX round trip, another layout by keywords, original file kept and downloaded, unreadable file, manager-only | **76 / 76 pass** |
| Browser tests incl. 18 new (`tests/ui/invoice_import.cjs`) | **108 / 108 pass** on the development bench and on the clean install upgraded with `update.sh` (imports ran on the real background worker) |

Found and fixed while testing: Data Import commits its rows, so the backend tests now remove what they import; the EDF browser test re-selects its month after a reload and uses a unique remark per run.

## 1.2.0rc1 — Wallet import (10 Nov 2026)

| Check | Result |
|---|---|
| Backend tests incl. 12 new (`test_wallet_import.py`): template header, review, create/update/skip/rename through Data Import, merge rule, PDF parsing (SupaBill and other layouts), manager-only, uploads readable only by their owner | **64 / 64 pass** |
| Browser tests incl. 15 new (`tests/ui/wallet_import.cjs`) | **90 / 90 pass** |

Found and fixed while testing: the import row linked to its wallet, which stopped imported wallets from being deleted (now plain text). Note: backend tests leave the test invoice prefix in Settings; run `demo_data.load` before the browser tests.

## 1.1.0rc1 — EDF section (10 Nov 2026)

| Check | Result |
|---|---|
| Backend tests including 10 new EDF/realisation tests (`test_edf.py`) | **All pass** on both benches |
| Browser tests incl. 16 new EDF checks (`tests/ui/edf.cjs`) | **75 / 75 pass** on both benches |
| Upgrade of the clean-install bench with `scripts/update.sh --source` (backup, migrate adds the new DocTypes and fields, build, health check) | **Pass** (609c3d5 → 023257e) |

EDF checks: month list, 2B rows from export invoices only, due banner, edits saved and kept on refresh, net realisable value above the amount refused, PDF and CSV download, mark as filed freezes the form, reopen, realisation close/reopen with IRM, SupaBill User can prepare but not file (UI and API), no page errors. The register forex check was made data-independent (it compared against a fixed row). Security: EDF HTML is escaped (test), filing is manager-only on the server.

---

# SupaBill 1.0.0rc1 — test report

Run: 10 Nov 2026 13:48 UTC. Tester: Claude (automated). All data synthetic.

## Environments

| | Development bench | Clean-install bench (E2E) |
|---|---|---|
| Path | /home/frappe/frappe-bench | /home/frappe/bench-e2e |
| Frappe | 16.55.2 | 16.56.0 |
| Site / port | supabill.local :8001 | e2e.local :8002 (created fresh for this run) |
| Python / Node | 3.14.6 / 24.22.2 | same |
| MariaDB / Redis | 10.11.14 / 7.0.15 | same server, separate database and Redis ports |

Both are throwaway sites in an isolated workspace. `erp.supagigs.cloud` was never contacted.

## Results

| Check | Result |
|---|---|
| Fresh install with `scripts/install.sh` (backup, get-app, pip deps, install, build, health check) | **Pass** |
| Update with `scripts/update.sh` (local-change check, backup, fast-forward, migrate, build, health check) | **Pass** (bf5e0a2 → 7f215e6) |
| `update.sh` refuses a non-fast-forward update | **Pass** (seen after the history clean-up below) |
| Backend unit + integration tests (`bench run-tests --app supabill`) | **48 / 48 pass** on both benches |
| Two processes creating invoices at once (`tests/concurrency_check.py`) | **Pass** — 12 invoices, 0 duplicate numbers |
| Browser tests (`tests/ui/run_all.sh`, Playwright/Chromium) on the clean install | **59 / 59 pass** |
| Background job attaches PDF + DOCX to each invoice (private files) | **Pass** |
| Security review (below) | **Pass**, 2 issues found and fixed |

### Browser checks (59)

```
PASS  Guest is sent to login with redirect
PASS  Manager lands on New invoice
PASS  Manager sees 5 nav items
PASS  Manager opens Settings
PASS  Dark mode switch sets data-theme
PASS  Dark mode survives reload
PASS  Collapse toggle present
PASS  Unknown route shows 404
PASS  User does not see Wallets/Settings
PASS  User blocked from Settings
PASS  Server refuses User editing Settings via API
PASS  No-role user sees access message
PASS  Phone shows bottom tab bar
PASS  No horizontal scroll on phone
PASS  No JavaScript errors
PASS  Milestone moves up by one
PASS  Ready to generate
PASS  Preview shows auto description
PASS  Total shown
PASS  CBIC auto rate 88.45
PASS  Missing bank details blocks generate
PASS  Generate disabled while blocked
PASS  IGST adds 18%
PASS  Title becomes TAX INVOICE
PASS  Ctrl+Enter generates the invoice
PASS  Saved and submitted on server
PASS  Server totals match
PASS  Due date from Net 21
PASS  Bank details copied onto invoice
PASS  Download PDF
PASS  Download DOCX
PASS  Pressing again creates nothing
PASS  Next invoice starts with new number
PASS  No JavaScript errors
PASS  Client added
PASS  Client edited
PASS  New invoice opens with that client
PASS  Wallet saved and complete
PASS  Settings saved
PASS  Key shown only as saved
PASS  LUT ARN persisted
PASS  API key never sent back to the browser
PASS  HSN code added as favourite
PASS  Manual CBIC rate added
PASS  Fetch CBIC reports a clear result
PASS  User sees no Delete for clients
PASS  Server refuses wallet change by User
PASS  No JavaScript errors
PASS  Register lists invoices
PASS  Client filter
PASS  Received sets payment status
PASS  Forex gain calculated
PASS  Saved on server
PASS  Search by invoice number
PASS  CSV export has Excel headers and rows
PASS  User cannot cancel
PASS  Manager cancels an invoice
PASS  Cancelled row stays, marked
PASS  No JavaScript errors
```

### Backend test coverage
Numbering (format, row lock, skipping used numbers, settings refusing a used number) · totals for LUT / IGST / CGST+SGST · GST quarter · CBIC rate by date and manual override · blocking checks (address, amount, wallet bank details, CBIC rate) · submit locks content, register fields stay editable · payment status and forex/net calculations · idempotent create · register filters/search/totals · cancel needs manager · role permission matrix · session API · secrets write-only and never returned · client/wallet rename and guarded delete · codes and favourites · DOCX contains every value and no leftover placeholders · PDF via LibreOffice and via the HTML fallback · download permissions · attach job idempotent · HTML escaping · Excel push with formulas, no duplicate rows, pull where Excel wins and blanks never wipe, write-back keeping formulas, 429/503 retry, 403 and bad sign-in messages without secrets, retry of failed pushes · CBIC keyed sync, key-free fallback on 401, 403 / bad JSON / schema change / empty table / 500 keep existing rates, manual mode · every API module imports.

## Security review

- All 28 whitelisted methods check the SupaBill role on the server; writes are POST-only; none allow guests. Integration triggers are rate-limited (10/min).
- Permission bypasses exist only in background jobs and system writes (attach files, sync logs, Excel/CBIC updates).
- **Fixed:** SupaBill Users could see the masked secret fields through the standard REST API (revealing only their length). Secrets moved to a manager-only permission level; verified absent for users.
- **Fixed:** invoice text was not HTML-escaped in the PDF template (wkhtmltopdf). Autoescape on; test added.
- **Fixed before publishing:** values from the real Supagigs invoice (bank account, client contact, PAN/GSTIN) and a thumbnail preview inside the Word template were removed from the code and from the entire git history, along with the author name in the template's properties.
- Secrets never appear in API responses, logs, Excel or the ZIP (checked in tests and by search).

## Bugs found by this run and fixed
1. `frappe.rate_limit` is not exported in Frappe 16.56 → import from `frappe.rate_limiter` (found only on the clean bench). An import smoke test now guards against this.
2. CBIC sync committed inside the request, leaking test data → removed (Frappe commits at request/job end).

## Not verified (needs your environment)

| Item | Why | How to verify |
|---|---|---|
| Live Excel sync with your Microsoft 365 workbook | No Azure app registration yet; this workspace cannot reach Microsoft Graph | Admin guide §5, then Settings → Test connection / Sync now on staging |
| Live AllRatesToday CBIC fetch | Workspace network blocks allratestoday.com (the app reports "unreachable" correctly) | Settings → Fetch latest CBIC rates on staging |
| Microsoft permission `Files.SelectedOperations.Selected` grant steps | Depends on your tenant | Follow admin guide §5.2 with your M365 admin |
| PDF on your server | Depends on LibreOffice being installed there; otherwise the HTML layout is used | Settings shows the active PDF engine |
| Real email delivery | Not in v1 scope | — |

## Release status
**1.0.0rc1 (release candidate).** All automated checks pass. It becomes 1.0.0 after the live Excel and CBIC checks pass on your staging site.
