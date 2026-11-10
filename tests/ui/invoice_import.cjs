// Import invoices into the Sales Register: PDF/Word files and CSV, with per-row review. Needs demo data.
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = [];
const check = (name, ok, extra = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'sbii-'));
const TAG = 'UIIMP' + Date.now().toString(36).toUpperCase();

(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  if (!(await c.request.post(BASE + '/api/method/login', { form: { usr: 'ui.manager@example.com', pwd: 'Test@12345!' } })).ok()) throw new Error('login');
  const p = await c.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.goto(BASE + '/supabill/register');
  await p.getByRole('button', { name: 'Import invoices' }).waitFor();
  const H = { 'X-Frappe-CSRF-Token': await p.evaluate(() => window.csrf_token) };
  const get = async (u) => (await (await c.request.get(BASE + u)).json());

  // source invoice: newest export invoice of a test client, saved as PDF and DOCX
  const src = (await get('/api/resource/SB Invoice?filters=' + encodeURIComponent('[["docstatus","=",1],["tax_treatment","=","Export under LUT"],["imported","=",0]]') + '&order_by=creation%20desc&limit_page_length=1&fields=' + encodeURIComponent('["name","grand_total","wallet","received_inr"]'))).data[0];
  for (const ext of ['pdf', 'docx']) {
    const r = await c.request.get(BASE + `/api/method/supabill.api.output.download?name=${encodeURIComponent(src.name)}&fmt=${ext}`);
    fs.writeFileSync(path.join(TMP, `old.${ext}`), await r.body());
  }
  const bp = await c.newPage(); await bp.setContent('<p>A photo would have no text. This page has no invoice words.</p>'); await bp.pdf({ path: path.join(TMP, 'blank.pdf') }); await bp.close();

  // ---- PDF / Word files
  await p.getByRole('button', { name: 'Import invoices' }).click();
  await p.getByText('From PDF / Word files').click();
  await p.getByLabel('Invoice files').setInputFiles([path.join(TMP, 'old.pdf'), path.join(TMP, 'old.docx'), path.join(TMP, 'blank.pdf')]);
  const dlg = p.getByRole('dialog');
  await dlg.getByText(/2 invoices/).waitFor({ timeout: 30000 });
  check('Two readable files listed, one reported as not read', await dlg.getByText(/Not read: blank\.pdf/).isVisible());
  check('Number read from the PDF', (await p.getByLabel('Invoice number, old.pdf').inputValue()) === src.name);
  check('Existing number defaults to Skip with Update / new number offered',
    (await p.getByLabel('Action, old.pdf').inputValue()) === 'skip' &&
    (await p.getByLabel('Action, old.pdf').locator('option').allInnerTexts()).join('|') === 'Update register fields|Skip|Import with a new number');
  check('Wallet matched from the printed bank details', (await p.getByLabel('Wallet, old.pdf').inputValue()) === src.wallet);
  const importBtn = dlg.getByRole('button', { name: /^Import \d+ invoice/ });
  await p.getByLabel('Invoice number, old.pdf').fill(TAG + '/1');
  await p.getByLabel('Invoice number, old.docx').fill(TAG + '/1');
  check('Same new number twice is blocked', await importBtn.isDisabled() && await dlg.getByText('This number is used by another row').first().isVisible());
  await p.getByLabel('Invoice number, old.docx').fill(src.name);
  await p.getByLabel('Action, old.docx').selectOption('update');
  check('Resolved rows unblock the import', await importBtn.isEnabled());
  await p.screenshot({ path: OUT + '/60-invoice-import-review.png' });
  await importBtn.click();
  await dlg.getByText(/created/).first().waitFor({ timeout: 60000 });
  const done = (await dlg.innerText()).replace(/\s+/g, ' ');
  check('Files import: 1 created, 1 updated', /1 created/.test(done) && /1 updated/.test(done), done.slice(0, 140));
  await dlg.getByRole('button', { name: 'Done' }).click();
  const made = (await get(`/api/resource/SB Invoice/${encodeURIComponent(TAG + '/1')}`)).data;
  check('Imported invoice keeps its number and amount, marked imported', made && made.docstatus === 1 && made.imported === 1 && made.grand_total === src.grand_total);
  const orig = await c.request.get(BASE + `/api/method/supabill.api.output.download?name=${encodeURIComponent(TAG + '/1')}&fmt=pdf`);
  check('Downloading it returns the original PDF', orig.ok() && (await orig.body()).equals(fs.readFileSync(path.join(TMP, 'old.pdf'))));
  await p.getByLabel('Search register').fill(TAG);
  await p.waitForTimeout(800);
  check('Imported invoice shows in the register', await p.getByText(TAG + '/1').first().isVisible());

  // ---- CSV
  const tpl = await c.request.get(BASE + '/api/method/supabill.api.invoice_import.download_template');
  const header = (await tpl.text()).replace(/^﻿/, '').trim();
  check('CSV template downloads', tpl.ok() && header.startsWith('Invoice Number,If Invoice Exists,Invoice Date'));
  const cols = header.split(',');
  const line = (o) => cols.map((h) => { const v = o[h] || ''; return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(',');
  const base = { 'Invoice Date': '15/04/2026', Currency: 'USD', 'Amount Before Tax': '750', Wallet: src.wallet, 'CBIC Rate': '85.25', Description: 'Imported by UI test', 'SAC Code': '998313' };
  fs.writeFileSync(path.join(TMP, 'inv.csv'), [header,
    line({ ...base, 'Invoice Number': TAG + '/2', Client: 'UI Import Client ' + TAG, 'Client Address': '9 Test Lane, Pune', 'Client Country': 'India', 'Received (INR)': '64000', 'Payment Status': 'Received' }),
    line({ ...base, 'Invoice Number': TAG + '/1', Client: 'Northwind Rentals' }),
  ].join('\n') + '\n');
  await p.getByRole('button', { name: 'Import invoices' }).click();
  await p.getByText('From CSV').click();
  await p.getByLabel('CSV file').setInputFiles(path.join(TMP, 'inv.csv'));
  await dlg.getByText(/2 invoices/).waitFor({ timeout: 30000 });
  check('New client offered as “Create new”', (await p.getByLabel('Client, row 2').locator('option').first().innerText()).startsWith('Create new: UI Import Client'));
  check('Number imported a moment ago is now “Exists”', (await p.getByLabel('Action, row 3').inputValue()) === 'skip');
  await p.screenshot({ path: OUT + '/61-invoice-import-csv.png' });
  await dlg.getByRole('button', { name: /^Import 1 invoice$/ }).click();
  await dlg.getByText(/created/).first().waitFor({ timeout: 60000 });
  check('CSV import: 1 created, 1 skipped', /1 created/.test(await dlg.innerText()) && /1 skipped/.test(await dlg.innerText()));
  await dlg.getByRole('button', { name: 'Done' }).click();
  const csvInv = (await get(`/api/resource/SB Invoice/${encodeURIComponent(TAG + '/2')}`)).data;
  check('CSV invoice has its register values', csvInv && csvInv.received_inr === 64000 && csvInv.payment_status === 'Received' && csvInv.cbic_rate === 85.25);
  check('New client created', !!(await get(`/api/resource/SB Client/${encodeURIComponent('UI Import Client ' + TAG)}`)).data);
  await c.close();

  // SupaBill User: no import
  const u = await b.newContext();
  await u.request.post(BASE + '/api/method/login', { form: { usr: 'ui.user@example.com', pwd: 'Test@12345!' } });
  const up = await u.newPage(); await up.goto(BASE + '/supabill/register'); await up.getByRole('button', { name: 'Export .csv' }).waitFor();
  check('SupaBill User sees no Import invoices', (await up.getByRole('button', { name: 'Import invoices' }).count()) === 0);
  await u.close();
  check('No page errors', errors.length === 0, errors.join(' | '));
  await b.close();
  console.log(results.join('\n'));
  process.exit(results.some((x) => x.startsWith('FAIL')) ? 1 : 0);
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
