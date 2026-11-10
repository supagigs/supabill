# SupaBill

Invoices, sales register and Excel sync for Supagigs — a standalone Frappe v16 app with a Vue 3 frontend at `/supabill`.

- **New invoice** — pick a client, enter the amount, generate. The server checks everything before an invoice can be created (address, amount, wallet bank details, CBIC rate, unique number) and numbers invoices under a lock.
- **PDF and DOCX** in the exact Supagigs invoice layout (generated from the Word template; PDF via LibreOffice when installed).
- **Sales register** with the same 22 columns as the Excel workbook; payment fields are edited inline.
- **Excel sync** with the Microsoft 365 workbook: new invoices are added as table rows, payment columns are read back.
- **EDF filing** (RBI Annex, one per month) and a **realisation tracker** for EDPMS.
- **CBIC exchange rates** from AllRatesToday, picked by invoice date (export rate).
- **Clients, wallets, settings**, SAC/HSN and RBI purpose codes with favourites.

No ERPNext dependency. ERPNext linkage is planned for a later phase.

## Install

On a Frappe v16 bench (Node 24+, Python 3.14), on a **staging site first**:

```bash
./scripts/install.sh --bench ~/frappe-bench --site staging.local --repo https://github.com/supagigs/supabill.git
```

Update later with `./scripts/update.sh --bench ~/frappe-bench --site staging.local [--ref v1.0.0]`.
Both scripts back the site up first and refuse `erp.supagigs.cloud` unless told otherwise.

Optional: `sudo apt install libreoffice-writer` (Linux) or `brew install --cask libreoffice` (Mac) so PDFs match the Word template exactly.

## Docs

- [User guide](docs/user-guide.md)
- [Admin guide](docs/admin-guide.md) — roles, Microsoft 365 / Azure setup, AllRatesToday, backups
- [Test report](docs/test-report.md)
- [Environment used for development](docs/environment.md)

## Development

```bash
cd apps/supabill/frontend && yarn install && yarn dev    # Vite dev server, proxies to bench on :8000
bench --site <test-site> run-tests --app supabill        # backend tests
SB_BASE=http://<site>:<port> tests/ui/run_all.sh shots   # browser tests (needs demo data, see script)
```

Code style: `pre-commit install` (ruff, eslint, prettier, pyupgrade).

Licence: MIT. Third-party: frappe-ui (MIT), docxtpl (LGPL-2.1, used unmodified as a library), python-docx (MIT).
