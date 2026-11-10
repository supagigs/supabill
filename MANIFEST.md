# SupaBill — release manifest

- **Version:** 1.0.0rc1 (release candidate)
- **Repository:** https://github.com/supagigs/supabill (branch `main`, tag `v1.0.0-rc1`)
- **Compatibility:** Frappe v16 (tested 16.55.2 and 16.56.0), Python 3.14, Node 24+, MariaDB 10.6+, Redis. No ERPNext dependency.
- **Python dependency:** docxtpl 0.20.x (pulls python-docx). **Optional system package:** LibreOffice (exact PDFs).
- **Frontend:** Vue 3.5, frappe-ui 1.1.0, Vite 6, TypeScript; built by `bench build --app supabill`.

## Included (plan sections 1–10)
1. Bench setup and app scaffold · 2. Data model and roles · 3. Vue app shell · 4. Invoice engine API · 5. New Invoice screen · 6. PDF and DOCX output · 7. Clients, Wallets, Settings · 8. Sales register · 9. Excel (Microsoft Graph) and CBIC (AllRatesToday) integrations · 10. Security, tests, scripts, docs.

## Not included (later phases)
ERPNext linkage, dashboard, EDF filing and realisation tracker, emailing invoices, e-invoicing.

## Known limitations
- Live Excel and CBIC connections are untested until credentials exist (see docs/test-report.md).
- HSN appears in the DOCX in the SAC column ("998313 / HSN 8471"); the PDF/HTML layout has its own HSN column.
- The main JS bundle is ~560 kB (frappe-ui); acceptable for an internal tool.
- Back-dated CBIC lookups need a paid AllRatesToday plan; otherwise stored or manual rates are used.

## Files
`scripts/install.sh`, `scripts/update.sh` · `docs/` (user guide, admin guide, template guide, test report, environment, screenshots) · `tests/ui/` (browser tests).
