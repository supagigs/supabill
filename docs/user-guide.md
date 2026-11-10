# SupaBill user guide

Open **/supabill** on your Frappe site and sign in. You need the **SupaBill User** or **SupaBill Manager** role.

| | SupaBill User | SupaBill Manager |
|---|---|---|
| Create invoices, download PDF/DOCX | ✓ | ✓ |
| Update payment fields in the register | ✓ | ✓ |
| Add and edit clients | ✓ | ✓ |
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

## Clients

Each client stores the bill-to details and the defaults for its invoices (project, currency, terms, wallet, tax treatment, purpose code, SAC/HSN). **New invoice →** starts an invoice for that client. Clients with invoices can be disabled but not deleted.

## Wallets & banks (managers)

Each wallet is a collection account. Its bank details print under **Bank transfer details**. A wallet with an empty detail line is marked *details missing* and cannot be used for an invoice until it is filled in. Tick **Paid via Upwork** for wallets that need no bank details.

## Settings (managers)

- **Company** — header and FROM block.
- **Invoice numbering** — prefix, next number, digits. A number already used is refused.
- **Defaults**, **Export / LUT** (renew the ARN each year), **AD bank & signatory**.
- **SAC & HSN codes** and **Purpose codes** — star favourites so they appear first.
- **CBIC exchange rates** — fetched automatically; add a rate by hand from the ICEGATE notification if needed.
- **Excel sync** — see the admin guide.

Secrets (Microsoft client secret, AllRatesToday key) are write-only: SupaBill shows only whether one is saved.
