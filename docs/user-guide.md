# SupaBill user guide

Open **/supabill** on your Frappe site and sign in. You need the **SupaBill User** or **SupaBill Manager** role.

| | SupaBill User | SupaBill Manager |
|---|---|---|
| Create invoices, download PDF/DOCX | ✓ | ✓ |
| Update payment fields in the register | ✓ | ✓ |
| Add and edit clients | ✓ | ✓ |
| Prepare EDFs, update the realisation tracker | ✓ | ✓ |
| Mark an EDF as filed or reopen it | | ✓ |
| Cancel invoices, delete clients | | ✓ |
| Wallets & banks, Settings, codes, CBIC rates, Excel sync | | ✓ |

## Create an invoice

1. **New invoice** → click the client. SupaBill fills in the address, project, wallet, terms, purpose code and last amount, and moves the milestone on by one (Milestone 2 of 3 → 3 of 3).
   Use **Repeat last for this client** for retainers that bill the same thing every month.
2. Type the **billing period**. Check the **amount** under Items.
3. Look at the card above the preview:
   - **Ready to generate** — go ahead.
   - **Fix … before generating** — red items block the invoice (for example a wallet with missing bank details, or no CBIC rate for that date). Grey items are optional.
4. Press **Generate & add to register** (or **Ctrl + Enter**). Pressing it twice never creates two invoices.
5. Download the **PDF** or **DOCX**, open it in the register, or **Start next invoice**.

Good to know:
- The line description is built from project + milestone + billing period. Type your own text to override it.
- **Tax treatment**: *Export · LUT 0%* for exports (the LUT note is added automatically), *IGST 18%* or *CGST + SGST 9+9* for Indian clients. GST invoices are titled "TAX INVOICE".
- The **CBIC rate** is the export rate notified for the invoice date (label "Auto"). Type a rate to override it ("Manual"); click *use notified rate* to go back.
- The invoice keeps a copy of the wallet's bank details as they were when it was generated.
- After an invoice is generated its content is locked. Only register fields can change. A manager can cancel it; a cancelled invoice stays in the register.

## Sales register

The register has the same columns as the Excel workbook. Dashed cells are the ones filled in later:

- **Wallet ref. no.**, **Received (₹)** (the INR credited in IDFC FIRST Bank), **Bank charges**, **Payment status**, **Invoice status**, Upwork fields.
- Entering **Received** sets the payment status (Received if it covers at least 95% of the INR amount, otherwise Partially received). You can still pick the status yourself.
- **Forex gain** = Received − Amount in INR. **Net received** = Received − Bank charges (₹).
- **Overdue** appears when an unpaid invoice is past its due date.
- Filter by month, client, wallet or payment status; search by invoice number, client or wallet ref; **Export .csv** downloads exactly what is shown.
- The **Excel** column shows whether the row is in the workbook (✓ row 31), waiting (Queued) or failed.

Edits here are written back to Excel; edits your team makes in Excel come back here within a few minutes.

## EDF filing

**EDF filing** prepares one Export Declaration Form per invoice month for all export (LUT) invoices, in the RBI Annex layout. All wallets settle into IDFC FIRST Bank, so there is one form per month.

1. Pick the month. The banner shows the due date (30 days after month-end) and how many days are left.
2. Fix anything listed under **Fill in before filing** (AD code, branch address, signatory, client country or address).
3. Choose the type of export and category of exporter. In the table, lower the **net realisable value** where a wallet deducts fees, and add a contract number or remarks if needed. The amount, client and SAC come from the invoice.
4. Download the **PDF** (A4 portrait) or CSV and submit it to the bank.
5. A manager presses **Mark as filed** and adds the bank or EDPMS reference. The form is then frozen and each invoice is linked to it. **Reopen** puts it back to draft.

A draft follows the register: new or cancelled invoices in that month are added or dropped automatically, and your edits are kept.

## Realisation tracker

Lists every export invoice until its EDPMS entry is closed, soonest deadline first. **Realise by** is the invoice date plus the realisation period (9 months by default, Settings → AD bank). Add the **IRM number** when IDFC FIRST credits the payment and set **EDPMS** to Closed once the full value is realised; the realised date is filled in. "Paid, not closed" counts invoices marked Received in the register that are still open here.

### Import invoices (managers)

**Import invoices** (top right of the register) adds earlier invoices to the register.

- **From PDF / Word files** — choose one or more invoice PDFs or .docx files, one invoice per file. SupaBill looks for the words printed next to each value — *Invoice No*, *Invoice Date*, *Due Date*, *Bill To*, *Sub Total*, *Total Due*, *Currency*, *Purpose Code*, the SAC code, *LUT* / *IGST* / *CGST*, and the bank details — and reads the value beside or below them. No OCR or AI is used, so scanned (image) files are listed as *not read*. Numeric dates are read day first (15/04/2026).
- **From CSV** — download the template and fill one row per invoice. Required: Invoice Number, Invoice Date, Client, Currency, Amount Before Tax, Wallet.

In the review, every row shows what was found. For each row you can change the **invoice number**, choose **Create**, **Skip**, **Update register fields** (for a number that already exists — only wallet ref, received, charges and statuses change; blank cells keep current values) or **Import with a new number**, pick the **client** (an existing one, or *Create new* from the details on the invoice) and the **wallet** (matched automatically by the account number printed on the invoice). The import stays blocked until every row is resolved.

Imported invoices keep their own number (your next invoice number is unchanged), are locked like generated ones, are marked *Imported*, keep the original file (Download PDF/DOCX returns it), and are added to the Excel workbook when Excel sync is on. The import runs through Frappe's Data Import.

## Clients

Each client stores the bill-to details and the defaults for its invoices (project, currency, terms, wallet, tax treatment, purpose code, SAC/HSN). **New invoice →** starts an invoice for that client. Clients with invoices can be disabled but not deleted.

## Wallets & banks (managers)

Each wallet is a collection account. Its bank details print under **Bank transfer details**. A wallet with an empty detail line is marked *details missing* and cannot be used for an invoice until it is filled in. Tick **Paid via Upwork** for wallets that need no bank details.

### Import wallet

**Import wallet** (top right) adds wallets without typing every line.

- **From invoice PDF (one wallet)** — choose an invoice PDF that shows the bank details. SupaBill reads the "Label: value" lines (it looks for a *Bank transfer details* block first) and fills the form. Check each line, type the wallet name and press **Save**. If the name already exists you can **Update** that wallet (lines you filled replace its values, the rest stay) or **Use another name**. Scanned (image-only) PDFs cannot be read.
- **From CSV (many wallets)** — download the template, fill one row per wallet and upload it as CSV. *Wallet Name* is required; *Paid via Upwork* = Yes for wallets without bank details; extra lines go in *Other Details* as `Label: value`, one per line. A review screen lists every row. For a name that already exists choose **Update existing**, **Skip**, or type a new name; the import stays blocked until every clash is resolved. When updating, blank cells keep the wallet's current values.

The CSV import runs through Frappe's Data Import, so each run is also logged under Data Import in the desk (System Managers).

## Settings (managers)

- **Company** — header and FROM block.
- **Invoice numbering** — prefix, next number, digits. A number already used is refused.
- **Defaults**, **Export / LUT** (renew the ARN each year), **AD bank & signatory**.
- **SAC & HSN codes** and **Purpose codes** — star favourites so they appear first.
- **CBIC exchange rates** — fetched automatically; add a rate by hand from the ICEGATE notification if needed.
- **Excel sync** — see the admin guide.

Secrets (Microsoft client secret, AllRatesToday key) are write-only: SupaBill shows only whether one is saved.
