# Editing the invoice template

`supabill/templates/docx/invoice_template.docx` is the Supagigs invoice with every value replaced by a placeholder. Open it in Word to change fonts, colours, spacing or wording; keep the placeholders.

| Placeholder | Filled with |
|---|---|
| `{{ legal_name }}`, `{{ display_name }}`, `{{ company_address }}`, `{{ company_email }}`, `{{ company_phone }}`, `{{ gstin }}`, `{{ pan }}`, `{{ iec }}` | Settings → Company |
| `{{ title }}` | INVOICE, or TAX INVOICE for GST |
| `{{ name }}`, `{{ invoice_date }}`, `{{ due_date }}`, `{{ country_of_supply }}`, `{{ purpose_code }}`, `{{ currency }}` | Invoice details |
| `{{ client_name }}`, `{{ billing_address }}`, `{{ attention }}`, `{{ client_email }}` | Bill to |
| `{{ project }}`, `{{ milestone_line }}`, `{{ payment_terms }}`, `{{ payment_method }}` | Project & payment |
| `{%tr for it in items %}` … `{{ it.idx }}`, `{{ it.description }}`, `{{ it.codes }}`, `{{ it.rate }}`, `{{ it.qty }}`, `{{ it.tax }}`, `{{ it.amount }}` … `{%tr endfor %}` | One table row per line item (`codes` = SAC, plus HSN if given) |
| `{{ subtotal }}`, `{{ tax_label }}`, `{{ tax_total }}`, `{{ grand_total }}` | Totals |
| `{% if is_lut %}LUT{% endif %}`, `{{ notes }}` | Notes |
| `{%p for b in bank %}` `{{ b.label }}: {{ b.value }}` `{%p endfor %}` | Wallet bank details, one line each |

Rules: keep each placeholder inside one run (type it in one go, don't format half of it), and keep the `{%tr … %}` / `{%p … %}` lines on their own rows/paragraphs. After editing, run `bench --site <test-site> run-tests --app supabill --module supabill.supabill.tests.test_output` to check the template still renders.
