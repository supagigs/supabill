# SupaBill admin guide

## 1. Install on staging first

```bash
./scripts/install.sh --bench ~/frappe-bench --site staging.local --repo https://github.com/supagigs/supabill.git
```

Requirements: Frappe v16, Node 24+, Python 3.14, Redis and a running worker + scheduler (`bench start` in development, supervisor/systemd in production).
Recommended: LibreOffice (`libreoffice-writer`) so the PDF is produced from the Word template and matches it exactly. Without it SupaBill uses an HTML layout that is close but not identical. Settings → Invoice defaults shows which engine is active.

Never install or test on `erp.supagigs.cloud` before staging has passed. The scripts refuse that site unless `--i-know-this-is-production` is given.

## 2. Roles

Give users one of:

- **SupaBill User** — creates invoices, edits register fields, adds/edits clients.
- **SupaBill Manager** — everything, plus cancel, delete, wallets, settings, codes, CBIC rates, Excel sync.

System Managers have full access. Users with neither role see an access message at `/supabill`. Every API call checks the role on the server.

## 3. First-time setup (Settings)

1. **Company**: legal name, address, GSTIN, PAN, IEC, email, phone.
2. **Invoice numbering**: prefix `Supa/26-27/`, next number (e.g. 28), digits 3. For a new financial year change the prefix (e.g. `Supa/27-28/`) and set the next number to 1.
3. **Export / LUT**: LUT ARN and note.
4. **Wallets & banks**: enter each wallet's collection account. Wallets with blank lines cannot be used.
5. **Clients**: add clients with their address, country, wallet, terms, tax treatment and codes.

## 4. CBIC exchange rates (AllRatesToday)

CBIC publishes no official API; it notifies rates on ICEGATE on the 1st and 3rd Thursday of each month. SupaBill fetches the CBIC table from AllRatesToday:

- every Thursday at 20:00 (site time zone) and once a day as a safety net;
- with your API key if saved (Settings → CBIC exchange rates), otherwise from AllRatesToday's key-free endpoint;
- invoices use the **export** rate in force on the invoice date.

Failures (bad key, plan limits, outages, unexpected responses) are shown in Settings and logged in **SB Sync Log**; existing rates are always kept. Rates for past dates require a paid AllRatesToday plan — without it, back-dated invoices use the stored rates (add missing ones by hand).

The key can also be set in `site_config.json` as `allratestoday_api_key`. Rotate it in AllRatesToday and paste the new one into Settings; the old value is replaced.

## 5. Excel sync (Microsoft 365)

SupaBill adds each submitted invoice as a row in an **Excel table** inside the workbook, and every few minutes reads back *Wallet Reference Invoice Number, Received, Bank Conversion Charges ($/Rs) and Payment Status*. For those columns Excel wins; SupaBill never overwrites other cells except in rows it added. Register edits made in SupaBill are written to the same row (formulas kept).

### 5.1 Prepare the workbook

1. Open the register (e.g. `Invoice Register FY 2026-27`) in Excel.
2. Select the header row and all data rows → **Insert → Table** → tick *My table has headers*.
3. **Table Design → Table Name**: e.g. `Register`.
4. Keep the header names exactly as in the sheet (`Original Invoice Number`, `Received`, `Payment Status`, …). Extra columns are fine.

### 5.2 Register an app in Microsoft Entra (Azure)

Done once by a Microsoft 365 admin.

1. **portal.azure.com → Microsoft Entra ID → App registrations → New registration.** Name: `SupaBill`. Supported accounts: *this organisation only*. No redirect URI.
2. Copy the **Application (client) ID** and **Directory (tenant) ID**.
3. **Certificates & secrets → New client secret** → copy the value (shown once).
4. **API permissions → Add → Microsoft Graph → Application permissions**:
   - Preferred: **Files.SelectedOperations.Selected** (or **Sites.Selected** if the file is on a SharePoint site), then grant the app access to just the workbook. This is the least-privilege option; an admin grants file access with Graph (`POST /drives/{drive}/items/{item}/permissions` with `roles: ["write"]` for the app) or PnP PowerShell (`Grant-PnPAzureADAppSitePermission`).
   - Simpler but broader: **Files.ReadWrite.All**. Only use with your security team's approval.
5. **Grant admin consent.**

### 5.3 Connect SupaBill

Settings → Excel sync:

- Tenant ID, Client ID, Client secret (write-only).
- **Workbook share link** — *Share → Copy link* from Excel online.
- Worksheet name (e.g. `2026-27`) and **Excel table name** (e.g. `Register`).
- Tick **Enable Excel sync** → **Save settings** → **Test connection** → **Sync now**.

The sidebar shows the sync state. Failed pushes are retried every 5 minutes; every push/pull is logged in **SB Sync Log** (desk) with the Microsoft request ID.

Troubleshooting:

| Message | Fix |
|---|---|
| Microsoft sign-in failed: AADSTS7000215 | Wrong or expired client secret — create a new one |
| Graph 403 … no access to this file | Grant the app access to the file (5.2 step 4) and admin consent |
| Graph 404 … check the share link and table name | Re-copy the link; check the table name in Table Design |
| Excel table is missing columns: … | A header was renamed — restore the exact name |
| Row N no longer holds … | Someone sorted/moved rows — press Sync now to re-match |

## 6. Wallet import

Managers can import wallets from Wallets & banks → **Import wallet** (PDF or CSV; see the user guide). The CSV import uses Frappe's Data Import on the staging DocType **SB Wallet Import**, so it needs the scheduler enabled and a running worker (`bench --site <site> enable-scheduler`); SupaBill says so if they are off. Each run appears under Data Import in the desk with its log. Uploaded CSV/PDF files are deleted as soon as they are read; the CSV that was actually imported stays attached to the Data Import record as a private file.

## 6a. Backups, updates and rollback

- `./scripts/update.sh --bench ~/frappe-bench --site staging.local [--ref vX.Y.Z]` — stops on local changes, backs up, updates, migrates, builds, health-checks, prints the rollback command.
- Rollback: `git -C apps/supabill checkout <previous>` → `bench --site <site> migrate` → `bench build --app supabill`, or restore the backup.
- Uninstall: `bench --site <site> uninstall-app supabill` (removes SupaBill's DocTypes and data; back up first).

## 7. Data and security notes

- Invoices, clients and wallets live in the site database; generated PDF/DOCX files are attached to each invoice as **private** files.
- Secrets are stored in Frappe's encrypted password store, on a manager-only permission level, and never returned to the browser or written to logs.
- Text on invoices is HTML-escaped before PDF rendering.
- Test helpers (`supabill/supabill/tests/demo_data.py`) create fictional data and are for throwaway sites only.
