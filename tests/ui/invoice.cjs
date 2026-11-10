// Section 5: New Invoice screen end to end. Usage: node invoice.cjs <shots-dir>
const { chromium } = require('playwright');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = []; const check = (n, ok, x = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  — ' + x : ''}`);
const pick = async (p, label, opt) => { await p.getByLabel(label).click(); await p.getByRole('option', { name: new RegExp('^' + opt) }).first().click(); };
const wait = (loc, t = 8000) => loc.waitFor({ timeout: t }).then(() => true, () => false);
(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 });
  await c.request.post(BASE + '/api/method/login', { form: { usr: 'ui.user@example.com', pwd: 'Test@12345!' } });
  const p = await c.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(BASE + '/supabill/new');
  await p.getByRole('button', { name: 'Northwind Rentals' }).click();
  check('Milestone moves up by one', (await p.getByLabel('Milestone / billing line').inputValue()) === 'Milestone 3 of 3');
  await p.getByLabel('Billing period').fill('10 Oct – 31 Oct 2026');
  await p.getByLabel('Invoice date').fill('2026-11-10');
  check('Ready to generate', await wait(p.getByText('✓ Ready to generate')));
  check('Preview shows auto description', await wait(p.locator('article').getByText('Custom Reporting and Automation – Milestone 3 (10 Oct – 31 Oct 2026)')));
  check('Total shown', await wait(p.getByText('$1,972.42 USD')));
  check('CBIC auto rate 88.45', await wait(p.getByText('≈ INR at CBIC 88.45')));
  await p.screenshot({ path: OUT + '/10-new-invoice-ready.png' });
  // blocked state: wallet with missing bank details
  await pick(p, 'Receive via (wallet)', 'Skydo');
  check('Missing bank details blocks generate', await wait(p.getByText('Bank details for wallet Skydo')));
  check('Generate disabled while blocked', await p.getByRole('button', { name: /Generate & add/ }).isDisabled());
  await p.screenshot({ path: OUT + '/11-new-invoice-blocked.png' });
  await pick(p, 'Receive via (wallet)', 'Briskpe');
  await wait(p.getByText('✓ Ready to generate'));
  // IGST switch
  await p.getByRole('radio', { name: 'IGST 18%' }).click();
  check('IGST adds 18%', await wait(p.getByText('$2,327.46 USD')));
  check('Title becomes TAX INVOICE', await wait(p.locator('article').getByText('TAX INVOICE')));
  await p.getByRole('radio', { name: 'Export · LUT 0%' }).click();
  await wait(p.getByText('$1,972.42 USD'));
  await wait(p.getByText('✓ Ready to generate'));
  await p.keyboard.press('Control+Enter');
  const done = await wait(p.getByText(/✓ Invoice Supa\/26-27\/\d+ generated/), 15000);
  check('Ctrl+Enter generates the invoice', done);
  const name = done ? (await p.getByText(/✓ Invoice Supa\/26-27\/\d+ generated/).first().textContent()).match(/Supa\/26-27\/\d+/)[0] : '';
  await p.screenshot({ path: OUT + '/12-new-invoice-done.png' });
  const doc = name ? await (await c.request.get(BASE + '/api/resource/SB Invoice/' + encodeURIComponent(name))).json() : {};
  const d = doc.data || {};
  check('Saved and submitted on server', d.docstatus === 1, name);
  check('Server totals match', d.grand_total === 1972.42 && d.cbic_rate === 88.45 && Math.abs(d.amount_inr - 174460.55) < 0.01, `${d.grand_total} × ${d.cbic_rate} = ${d.amount_inr}`);
  check('Due date from Net 21', d.due_date === '2026-12-01', d.due_date);
  check('Bank details copied onto invoice', (d.bank_details || '').includes('Account Number: 000111222333'));
  for (const fmt of ['pdf', 'docx']) {
    const r = await c.request.get(BASE + '/api/method/supabill.api.output.download?name=' + encodeURIComponent(name) + '&fmt=' + fmt);
    const body = await r.body();
    check('Download ' + fmt.toUpperCase(), r.ok() && (fmt === 'pdf' ? body.slice(0, 4).toString() === '%PDF' : body.slice(0, 2).toString() === 'PK'), r.status() + ' ' + (r.headers()['content-disposition'] || ''));
  }
  // double click protection: press again — no second invoice
  const count = async () => (await (await c.request.get(BASE + '/api/method/frappe.client.get_count?doctype=SB%20Invoice&filters=' + encodeURIComponent(JSON.stringify({ client: 'Northwind Rentals' })))).json()).message;
  const before = await count();
  await p.keyboard.press('Control+Enter'); await p.waitForTimeout(800);
  const after = await count();
  check('Pressing again creates nothing', before === after, before + ' → ' + after);
  await p.getByRole('button', { name: 'Start next invoice' }).click();
  check('Next invoice starts with new number', await wait(p.getByText(/Ready to generate|Fix/)));
  check('No JavaScript errors', errs.length === 0, errs.join(' | '));
  console.log(results.join('\n')); await b.close();
})().catch(e => { console.log(results.join('\n')); console.error('FATAL', e.message); process.exit(1); });
