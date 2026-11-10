# Changelog

## 1.2.0rc1 — 10 Nov 2026
- **Import wallet** (managers) on Wallets & banks:
  - **From invoice PDF** — reads the bank lines from a text PDF into the wallet form (one wallet per PDF); nothing is saved until Save.
  - **From CSV** — template with one row per wallet; review screen to choose Update / Skip / new name for each name that already exists; runs through Frappe Data Import (staging DocType SB Wallet Import).
  - On update, filled values replace the wallet's lines; blank cells keep the current values.

## 1.1.0rc1 — 10 Nov 2026
- **EDF filing**: one consolidated Export Declaration Form per invoice month in the RBI Annex layout, built from the month's export (LUT) invoices. Due-date banner (30 days after month-end), editable net realisable value / contract / remarks, PDF and CSV, mark as filed (managers) with bank/EDPMS reference, reopen.
- **Realisation tracker**: every export invoice with its realise-by date (9 months by default, set in Settings), IRM number and EDPMS open/closed status.
- New invoice fields: realise by, IRM no., EDPMS status, realised on, EDF link. New DocTypes: SB EDF, SB EDF Line. Settings: place and realisation period.

## 1.0.0rc1 — 10 Nov 2026
First release candidate: invoice creation with PDF/DOCX in the Supagigs layout, clients, wallets, settings, codes, sales register, Excel sync (Microsoft Graph) and CBIC rates (AllRatesToday). Standalone Frappe v16 app.
