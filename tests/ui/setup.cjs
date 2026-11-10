// Section 7: Clients, Wallets and Settings screens. Usage: node setup.cjs <shots-dir>
const { chromium } = require('playwright');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = []; const check = (n, ok, x = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  — ' + x : ''}`);
const wait = (loc, t = 8000) => loc.waitFor({ timeout: t }).then(() => true, () => false);
const stamp = Date.now().toString(36).slice(-4);
async function login(b, user) {
  const c = await b.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 });
  await c.request.post(BASE + '/api/method/login', { form: { usr: user, pwd: 'Test@12345!' } });
  return c;
}
(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const errs = [];
  let c = await login(b, 'ui.manager@example.com'); let p = await c.newPage(); p.on('pageerror', e => errs.push(e.message));
  const bodies = []; p.on('response', async r => { if (r.url().includes('/api/method/supabill')) { try { bodies.push(await r.text()); } catch {} } });
  // Clients
  await p.goto(BASE + '/supabill/clients?new=1');
  const cname = 'Initech ' + stamp;
  await p.getByLabel('Client / company name').fill(cname);
  await p.getByLabel('Billing address').fill('5 Office Park\nAustin, TX 78701, United States');
  await p.getByLabel('Country (for EDF)').fill('United States');
  await p.getByLabel('Default project').fill('Data migration');
  await p.getByRole('button', { name: 'Add client' }).click();
  check('Client added', await wait(p.getByRole('cell', { name: new RegExp(cname) })));
  await p.getByLabel('Default project').fill('Data migration phase 2');
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  check('Client edited', await wait(p.getByRole('row', { name: new RegExp(cname) }).getByRole('cell', { name: 'Data migration phase 2' })));
  await p.screenshot({ path: OUT + '/20-clients.png' });
  await p.getByRole('button', { name: 'New invoice →' }).click();
  await p.waitForURL(/\/new/);
  check('New invoice opens with that client', await wait(p.locator('button.chip.on', { hasText: cname })));
  // Wallets
  await p.goto(BASE + '/supabill/wallets');
  await p.getByRole('button', { name: 'New wallet' }).click();
  const wname = 'Wise ' + stamp;
  await p.getByLabel('Wallet name').fill(wname);
  const values = p.locator('form input[placeholder^="Enter"]');
  const n = await values.count();
  for (let i = 0; i < n; i++) await values.nth(i).fill('V' + i);
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  check('Wallet saved and complete', await wait(p.locator('nav[aria-label="Wallets"] button', { hasText: wname }).filter({ hasText: '✓ complete' })));
  await p.screenshot({ path: OUT + '/21-wallets.png' });
  // Settings
  await p.goto(BASE + '/supabill/settings');
  await p.getByLabel('LUT ARN').fill('AD27TEST' + stamp);
  await p.getByLabel('AllRatesToday API key').fill('art_live_ui_secret_' + stamp);
  await p.getByRole('button', { name: 'Save settings' }).first().click();
  check('Settings saved', await wait(p.getByText('Settings saved')));
  check('Key shown only as saved', await wait(p.getByText('Saved on the server — type a new value to replace it').first()));
  await p.reload(); await wait(p.getByLabel('LUT ARN'));
  check('LUT ARN persisted', (await p.getByLabel('LUT ARN').inputValue()) === 'AD27TEST' + stamp);
  check('API key never sent back to the browser', !bodies.some(t => t.includes('art_live_ui_secret_')) && !(await p.content()).includes('art_live_ui_secret_'));
  const code = String(8400 + Math.floor(Math.random() * 99));
  await p.getByLabel('Code type').click(); await p.getByRole('option', { name: 'HSN' }).click();
  await p.getByLabel('New code').fill(code); await p.getByLabel('Description', { exact: true }).fill('Test goods');
  await p.locator('section', { hasText: 'SAC & HSN codes' }).getByRole('button', { name: '+ Add' }).click();
  check('HSN code added as favourite', await wait(p.getByText(`${code} added as a favourite`)));
  await p.getByLabel('Effective from').locator('input').first().fill('2026-12-03'); await p.keyboard.press('Enter');
  await p.getByLabel('Export rate').fill('89.12');
  await p.locator('section', { hasText: 'CBIC exchange rates' }).getByRole('button', { name: '+ Add' }).click();
  check('Manual CBIC rate added', await wait(p.getByRole('cell', { name: '89.12' })));
  await p.getByRole('button', { name: 'Fetch latest CBIC rates' }).click();
  const status = p.locator('section', { hasText: 'CBIC exchange rates' }).getByText(/Stored \d+ rates|unreachable|rejected|refused/).first();
  const fetched = await wait(status, 90000);
  check('Fetch CBIC reports a clear result', fetched, fetched ? (await status.textContent()).slice(0, 110) : '');
  await p.screenshot({ path: OUT + '/22-settings.png', fullPage: true });
  await c.close();
  // User role
  c = await login(b, 'ui.user@example.com'); p = await c.newPage(); p.on('pageerror', e => errs.push(e.message));
  await p.goto(BASE + '/supabill/clients');
  await wait(p.getByRole('cell', { name: new RegExp(cname) }));
  await p.getByRole('cell', { name: new RegExp(cname) }).click();
  check('User sees no Delete for clients', (await p.getByRole('button', { name: 'Delete' }).count()) === 0);
  const r = await p.evaluate(async () => (await fetch('/api/method/supabill.api.setup.save_wallet', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token, 'Content-Type': 'application/json' }, body: JSON.stringify({ values: { wallet_name: 'Hack' } }) })).status);
  check('Server refuses wallet change by User', r === 403, 'HTTP ' + r);
  await c.close();
  check('No JavaScript errors', errs.length === 0, errs.join(' | '));
  console.log(results.join('\n')); await b.close();
})().catch(e => { console.log(results.join('\n')); console.error('FATAL', e.message); process.exit(1); });
