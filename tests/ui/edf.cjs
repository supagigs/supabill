// EDF filing and realisation tracker. Needs demo data (export invoices in the current month).
const { chromium } = require('playwright');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = [];
const check = (name, ok, extra = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
async function ctx(b, user) {
  const c = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const r = await c.request.post(BASE + '/api/method/login', { form: { usr: user, pwd: 'Test@12345!' } });
  if (!r.ok()) throw new Error('login failed ' + user);
  return c;
}
(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const errors = [];
  let c = await ctx(b, 'ui.manager@example.com'), p = await c.newPage();
  p.on('pageerror', (e) => errors.push(e.message));
  // make sure the month starts as a draft
  const month = new Date().toISOString().slice(0, 7);
  await p.goto(BASE + '/supabill/edf');
  // Own test data: one export invoice this month, and the month back in draft
  const csrf = await p.evaluate(() => window.csrf_token);
  const H = { 'X-Frappe-CSRF-Token': csrf };
  const ex = await c.request.get(BASE + '/api/resource/SB Client/EDF Test Client');
  if (!ex.ok()) await c.request.post(BASE + '/api/method/supabill.api.setup.save_client', { headers: H, data: { values: {
    client_name: 'EDF Test Client', address: '1 Test Road\nAustin, TX 78701, United States', country: 'United States', currency: 'USD',
    payment_terms_days: 15, wallet: 'Briskpe', purpose_code: 'P0802', sac_code: '998313', tax_treatment: 'Export under LUT' } } });
  const mk = await c.request.post(BASE + '/api/method/supabill.api.invoice.create_invoice', { headers: H, data: { request_id: 'edf-ui-' + Date.now(),
    payload: { client: 'EDF Test Client', invoice_date: new Date().toISOString().slice(0, 10), currency: 'USD', tax_treatment: 'Export under LUT',
      milestone: 'EDF UI test', billing_period: 'this month', items: [{ description: 'EDF UI test', qty: 1, rate: 500, sac_code: '998313' }] } } });
  if (!mk.ok()) throw new Error('could not create test invoice: ' + (await mk.text()).slice(0, 300));
  await c.request.post(BASE + '/api/method/supabill.api.edf.reopen', { headers: H, data: { month } });
  await p.reload();
  await p.getByRole('tab').first().waitFor();
  check('EDF page lists invoice months', (await p.getByRole('tab').count()) >= 1);
  await p.getByRole('tab', { name: new RegExp(new Date().toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })) }).click();
  await p.getByText('2B. Services provided').waitFor();
  const rows = await p.locator('table tbody tr').count();
  check('Current month has export invoices in 2B', rows > 0, rows + ' rows');
  check('Due-date banner shows', await p.getByText(/EDF (is|was) due/).isVisible());
  const remarks = p.getByLabel(/^Remarks for /).first();
  await remarks.fill('UI test remark'); await remarks.press('Tab'); await p.waitForTimeout(700);
  await p.reload(); await p.getByText('2B. Services provided').waitFor();
  check('Remark is saved on the draft', (await p.getByLabel(/^Remarks for /).first().inputValue()) === 'UI test remark');
  const nrv = p.getByLabel(/^Net realisable value for /).first();
  const amt = Number(await nrv.inputValue());
  await nrv.fill(String(amt * 2)); await nrv.press('Tab'); await p.waitForTimeout(700);
  check('Net realisable value above the amount is refused', Number(await p.getByLabel(/^Net realisable value for /).first().inputValue()) === amt);
  await p.screenshot({ path: OUT + '/40-edf-draft.png', fullPage: true });
  const pdf = await c.request.get(BASE + `/api/method/supabill.api.edf.download?month=${month}&fmt=pdf`);
  check('EDF PDF downloads', pdf.ok() && (await pdf.body()).slice(0, 4).toString() === '%PDF');
  const csv = await c.request.get(BASE + `/api/method/supabill.api.edf.download?month=${month}&fmt=csv`);
  check('EDF CSV downloads', csv.ok() && (await csv.text()).includes('Net Realisable value'));
  await p.getByRole('button', { name: 'Mark as filed' }).click();
  await p.getByLabel('Bank / EDPMS reference (optional)').fill('UI-REF-1');
  await p.getByRole('dialog').getByRole('button', { name: 'Mark as filed' }).click();
  await p.getByText(/EDF filed with/).waitFor();
  check('Mark as filed freezes the form', await p.getByLabel(/^Remarks for /).first().isDisabled());
  await p.getByRole('tab').getByText(/✓ Filed/).first().waitFor({ timeout: 5000 }).catch(() => {});
  check('Filed tab shows the date', await p.getByRole('tab').getByText(/✓ Filed/).first().isVisible());
  await p.waitForTimeout(600);
  await p.screenshot({ path: OUT + '/41-edf-filed.png', fullPage: true });
  await p.getByRole('button', { name: 'Reopen' }).click();
  await p.getByRole('dialog').getByRole('button', { name: 'Reopen' }).click();
  await p.getByText(/EDF (is|was) due/).waitFor();
  check('Reopen returns to draft', !(await p.getByLabel(/^Remarks for /).first().isDisabled()));

  // Realisation tracker
  await p.getByRole('link', { name: 'Realisation tracker' }).click(); await p.waitForURL(/realisation/);
  await p.getByText('Open entries').waitFor();
  const irm = p.getByLabel(/^IRM number for /).first();
  const inv = (await irm.getAttribute('aria-label')).replace('IRM number for ', '');
  await irm.fill('IRM-UI-1'); await irm.press('Tab'); await p.waitForTimeout(600);
  await p.getByLabel('EDPMS status for ' + inv).selectOption('Closed'); await p.waitForTimeout(900);
  check('Closed entry leaves the open list', (await p.getByLabel('EDPMS status for ' + inv).count()) === 0);
  await p.getByLabel('Show closed').check(); await p.waitForTimeout(700);
  check('Show closed lists it with its IRM', (await p.getByLabel('IRM number for ' + inv).inputValue()) === 'IRM-UI-1');
  await p.screenshot({ path: OUT + '/42-realisation.png', fullPage: true });
  await p.getByLabel('EDPMS status for ' + inv).selectOption('Open'); await p.waitForTimeout(700);
  await c.close();

  // SupaBill User: can view and edit drafts, cannot file
  c = await ctx(b, 'ui.user@example.com'); p = await c.newPage();
  p.on('pageerror', (e) => errors.push('user: ' + e.message));
  await p.goto(BASE + '/supabill/edf'); await p.getByRole('tab').first().waitFor();
  check('User sees EDF in the sidebar', await p.getByRole('link', { name: 'EDF filing' }).isVisible());
  check('User has no Mark as filed button', (await p.getByRole('button', { name: 'Mark as filed' }).count()) === 0);
  const ucsrf = await p.evaluate(() => window.csrf_token);
  const r = await c.request.post(BASE + '/api/method/supabill.api.edf.mark_filed', { data: { month }, headers: { 'X-Frappe-CSRF-Token': ucsrf } });
  check('User cannot file through the API', r.status() === 403, 'status ' + r.status());
  await c.close();
  check('No page errors', errors.length === 0, errors.join(' | '));
  await b.close();
  console.log(results.join('\n'));
  process.exit(results.some((x) => x.startsWith('FAIL')) ? 1 : 0);
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
