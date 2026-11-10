// Import wallet: CSV (review + Data Import) and invoice PDF. Needs demo data (Briskpe wallet, a submitted invoice).
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = [];
const check = (name, ok, extra = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'sbwi-'));
const MADE = ['UI CSV One', 'UI CSV Renamed', 'UI CSV Two', 'UI PDF Wallet'];

(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, acceptDownloads: true });
  const r0 = await c.request.post(BASE + '/api/method/login', { form: { usr: 'ui.manager@example.com', pwd: 'Test@12345!' } });
  if (!r0.ok()) throw new Error('login failed');
  const p = await c.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.goto(BASE + '/supabill/wallets');
  await p.getByRole('button', { name: 'Import wallet' }).waitFor();
  const H = { 'X-Frappe-CSRF-Token': await p.evaluate(() => window.csrf_token) };
  const cleanup = async () => { for (const n of MADE) await c.request.post(BASE + '/api/method/supabill.api.setup.delete_wallet', { headers: H, data: { name: n } }); };
  await cleanup();

  // ---- CSV
  const tpl = await c.request.get(BASE + '/api/method/supabill.api.wallet_import.download_template');
  const header = (await tpl.text()).replace(/^﻿/, '').trim();
  check('CSV template downloads with the wallet columns', tpl.ok() && header.startsWith('Wallet Name,If Wallet Exists,Paid via Upwork,Settles To,Beneficiary Name'), header.slice(0, 60));
  const cols = header.split(',');
  const line = (o) => cols.map((h) => { const v = o[h] || ''; return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(',');
  const csv = [header,
    line({ 'Wallet Name': 'UI CSV One', 'Beneficiary Name': 'Acme Ltd', 'Account Number': '111222', 'Routing / SWIFT Code': '026000001', 'Account Type': 'Checking', 'Bank Name': 'Bank One', 'Bank Address': '1 Main St', 'Bank Country': 'United States' }),
    line({ 'Wallet Name': 'Briskpe' }),
    line({ 'Wallet Name': 'UI CSV Two', 'Account Number': '333', IBAN: 'DE89 3704', 'Other Details': 'Sort Code: 20-20-15' }),
    line({ 'Wallet Name': 'UI CSV Two', 'Account Number': '444' }),
  ].join('\n') + '\n';
  fs.writeFileSync(path.join(TMP, 'wallets.csv'), csv);
  await p.getByRole('button', { name: 'Import wallet' }).click();
  await p.getByText('From CSV (many wallets)').click();
  await p.getByRole('dialog').getByText('Download CSV template').waitFor();
  await p.getByLabel('CSV file').setInputFiles(path.join(TMP, 'wallets.csv'));
  await p.getByText('wallets.csv').waitFor();
  check('Review lists every row', (await p.getByRole('dialog').locator('tbody tr').count()) === 4);
  const importBtn = p.getByRole('dialog').getByRole('button', { name: /^Import \d+ wallet/ });
  check('Import is blocked while names clash', await importBtn.isDisabled());
  check('Existing wallet row offers Update / Skip / new name', (await p.getByLabel('Action, row 3').locator('option').allInnerTexts()).join('|') === 'Update existing|Skip|Import with a new name');
  await p.screenshot({ path: OUT + '/50-wallet-csv-review.png' });
  await p.getByLabel('Wallet name, row 3').fill('UI CSV Renamed');
  await p.getByLabel('Wallet name, row 5').fill('UI CSV Two B');
  await p.getByLabel('Action, row 5').selectOption('skip');
  check('Resolved rows unblock the import', await importBtn.isEnabled());
  await importBtn.click();
  await p.getByRole('dialog').getByText(/created/).first().waitFor({ timeout: 30000 });
  const done = await p.getByRole('dialog').innerText();
  check('Import result: 3 created, 1 skipped', /3 created/.test(done) && /1 skipped/.test(done), done.replace(/\s+/g, ' ').slice(0, 120));
  await p.screenshot({ path: OUT + '/51-wallet-csv-done.png' });
  await p.getByRole('dialog').getByRole('button', { name: 'Done' }).click();
  await p.getByRole('button', { name: /^UI CSV Two/ }).click();
  check('Imported extras land in the wallet form', (await p.getByRole('textbox', { name: 'IBAN', exact: true }).inputValue()) === 'DE89 3704' && (await p.getByRole('textbox', { name: 'Sort Code', exact: true }).inputValue()) === '20-20-15');
  const ac = await b.newContext();
  await ac.request.post(BASE + '/api/method/login', { form: { usr: 'Administrator', pwd: process.env.SB_ADMIN_PWD || 'admin' } });
  const di = await ac.request.get(BASE + '/api/resource/Data Import?filters=' + encodeURIComponent(JSON.stringify([['reference_doctype', '=', 'SB Wallet Import']])) + '&limit_page_length=1&order_by=creation%20desc&fields=' + encodeURIComponent('["status"]'));
  check('Run is logged in Frappe Data Import', di.ok() && (await di.json()).data?.[0]?.status === 'Success', String(di.status()));
  await ac.close();

  // ---- PDF
  const inv = (await (await c.request.get(BASE + '/api/resource/SB Invoice?filters=' + encodeURIComponent('[["docstatus","=",1],["wallet","=","Briskpe"]]') + '&limit_page_length=1')).json()).data[0].name;
  const pdf = await c.request.get(BASE + '/api/method/supabill.api.output.download?name=' + encodeURIComponent(inv) + '&fmt=pdf');
  fs.writeFileSync(path.join(TMP, 'invoice.pdf'), await pdf.body());
  await p.getByRole('button', { name: 'Import wallet' }).click();
  await p.getByText('From invoice PDF (one wallet)').click();
  await p.getByLabel('Invoice PDF').setInputFiles(path.join(TMP, 'invoice.pdf'));
  await p.getByText('Filled from invoice.pdf').waitFor();
  check('PDF fills the bank lines', (await p.getByRole('textbox', { name: 'Account Number', exact: true }).inputValue()).length > 0 && (await p.getByRole('textbox', { name: 'Bank Name', exact: true }).inputValue()).length > 0);
  check('Wallet name is left for the user', (await p.getByRole('textbox', { name: /^Wallet name/ }).inputValue()) === '');
  await p.screenshot({ path: OUT + '/52-wallet-pdf-filled.png' });
  await p.getByRole('textbox', { name: /^Wallet name/ }).fill('briskpe');
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.getByRole('dialog').getByText('Briskpe already exists').waitFor();
  check('Existing name asks Update / another name', await p.getByRole('dialog').getByRole('button', { name: 'Update Briskpe' }).isVisible());
  await p.getByRole('dialog').getByRole('button', { name: 'Use another name' }).click();
  await p.getByRole('textbox', { name: /^Wallet name/ }).fill('UI PDF Wallet');
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.getByText('Wallet saved').first().waitFor();
  await p.waitForTimeout(800); await p.screenshot({ path: OUT + '/53-wallet-pdf-saved.png' });
  check('PDF wallet saved under the new name', await p.getByRole('button', { name: /^UI PDF Wallet/ }).isVisible());
  // second PDF into the same wallet → Update
  await p.getByRole('button', { name: 'Import wallet' }).click();
  await p.getByText('From invoice PDF (one wallet)').click();
  await p.getByLabel('Invoice PDF').setInputFiles(path.join(TMP, 'invoice.pdf'));
  await p.getByText('Filled from invoice.pdf').waitFor();
  await p.getByRole('textbox', { name: /^Wallet name/ }).fill('UI PDF Wallet');
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.getByRole('dialog').getByRole('button', { name: 'Update UI PDF Wallet' }).click();
  await p.getByText(/Merged into UI PDF Wallet/).waitFor();
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.getByText('Wallet saved').first().waitFor();
  const list = await (await c.request.get(BASE + '/api/method/supabill.api.setup.list_wallets')).json();
  check('Update kept a single wallet', list.message.filter((w) => w.name === 'UI PDF Wallet').length === 1);
  const bad = path.join(TMP, 'blank.pdf');
  const bp = await c.newPage(); await bp.setContent('<h1>Quote 12</h1><p>Thank you for your business.</p>'); await bp.pdf({ path: bad }); await bp.close();
  await p.getByRole('button', { name: 'Import wallet' }).click();
  await p.getByText('From invoice PDF (one wallet)').click();
  await p.getByLabel('Invoice PDF').setInputFiles(bad);
  check('PDF without bank details explains itself', await p.getByText(/No bank details were found|could not be read/).first().waitFor({ timeout: 10000 }).then(() => true, () => false));

  await cleanup();
  check('No page errors', errors.length === 0, errors.join(' | '));
  await b.close();
  console.log(results.join('\n'));
  process.exit(results.some((x) => x.startsWith('FAIL')) ? 1 : 0);
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
