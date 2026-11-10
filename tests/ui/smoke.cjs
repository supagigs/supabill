const { chromium, devices } = require('playwright');
const BASE = process.env.SB_BASE || 'http://supabill.local:8001', OUT = process.argv[2] || '.';
const results = [];
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`); };
async function ctx(browser, user, opts = {}) {
  const c = await browser.newContext({ ...opts });
  if (user) {
    const r = await c.request.post(BASE + '/api/method/login', { form: { usr: user, pwd: user === 'Administrator' ? 'admin' : 'Test@12345!' } });
    if (!r.ok()) throw new Error('login failed ' + user + ' ' + r.status());
  }
  return c;
}
(async () => {
  const b = await chromium.launch({ args: ['--host-resolver-rules=MAP *.local 127.0.0.1', '--no-proxy-server'] });
  const errors = [];
  // Guest
  let c = await ctx(b, null), p = await c.newPage();
  await p.goto(BASE + '/supabill/register');
  check('Guest is sent to login with redirect', p.url().includes('/login') && p.url().includes('redirect-to'), p.url());
  await c.close();
  // Manager desktop
  c = await ctx(b, 'ui.manager@example.com', { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }); p = await c.newPage();
  p.on('pageerror', e => errors.push('manager: ' + e.message));
  await p.goto(BASE + '/supabill'); await p.waitForSelector('nav');
  check('Manager lands on New invoice', p.url().endsWith('/supabill/new'), p.url());
  const navM = await p.locator('nav a').allInnerTexts();
  check('Manager sees 5 nav items', ['New invoice','Sales register','Clients','Wallets & banks','Settings'].every(x => navM.join('|').includes(x)), navM.join(', '));
  await p.screenshot({ path: OUT + '/01-manager-desktop-light.png' });
  await p.getByRole('link', { name: 'Settings' }).click(); await p.waitForURL(/settings/);
  check('Manager opens Settings', (await p.title()).startsWith('Settings'), await p.title());
  await p.getByText('SupaBill', { exact: true }).first().click();
  await p.getByText('Dark mode').click(); await p.waitForTimeout(400);
  check('Dark mode switch sets data-theme', (await p.evaluate(() => document.documentElement.dataset.theme)) === 'dark');
  await p.reload(); await p.waitForSelector('nav');
  check('Dark mode survives reload', (await p.evaluate(() => document.documentElement.dataset.theme)) === 'dark');
  await p.screenshot({ path: OUT + '/02-manager-settings-dark.png' });
  await p.getByText('SupaBill', { exact: true }).first().click(); await p.getByText('Light mode').click(); await p.waitForTimeout(300);
  // collapse toggle
  const collapse = p.getByText('Collapse', { exact: true });
  if (await collapse.count()) { await collapse.first().click(); await p.waitForTimeout(300); await p.screenshot({ path: OUT + '/03-manager-collapsed.png' }); await collapse.count(); await p.getByText('Expand', { exact: true }).click(); }
  check('Collapse toggle present', (await collapse.count()) > 0);
  await p.goto(BASE + '/supabill/nope'); check('Unknown route shows 404', await p.getByText('This page doesn’t exist').waitFor({ timeout: 8000 }).then(() => true, () => false));
  await c.close();
  // User desktop
  c = await ctx(b, 'ui.user@example.com', { viewport: { width: 1440, height: 900 } }); p = await c.newPage();
  p.on('pageerror', e => errors.push('user: ' + e.message));
  await p.goto(BASE + '/supabill/register'); await p.waitForSelector('nav');
  const navU = await p.locator('nav a').allInnerTexts();
  check('User does not see Wallets/Settings', !navU.join('|').includes('Settings') && !navU.join('|').includes('Wallets'), navU.join(', '));
  await p.goto(BASE + '/supabill/settings'); await p.waitForURL(/no-access/);
  check('User blocked from Settings', await p.getByText('Managers only').waitFor({ timeout: 8000 }).then(() => true, () => false));
  await p.screenshot({ path: OUT + '/04-user-managers-only.png' });
  const apiStatus = await p.evaluate(async () => (await fetch('/api/method/frappe.client.set_value', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': window.csrf_token, 'Content-Type': 'application/json' }, body: JSON.stringify({ doctype: 'SupaBill Settings', name: 'SupaBill Settings', fieldname: 'legal_name', value: 'Hacked' }) })).status);
  check('Server refuses User editing Settings via API', apiStatus === 403, 'HTTP ' + apiStatus);
  await c.close();
  // No-role user
  c = await ctx(b, 'ui.norole@example.com', { viewport: { width: 1280, height: 800 } }); p = await c.newPage();
  await p.goto(BASE + '/supabill/new'); await p.waitForURL(/no-access/);
  check('No-role user sees access message', await p.getByText('You don’t have access to SupaBill').waitFor({ timeout: 8000 }).then(() => true, () => false));
  await p.screenshot({ path: OUT + '/05-norole.png' });
  await c.close();
  // Phone
  c = await ctx(b, 'ui.manager@example.com', { ...devices['iPhone 14'] }); p = await c.newPage();
  p.on('pageerror', e => errors.push('phone: ' + e.message));
  await p.goto(BASE + '/supabill/clients'); await p.waitForTimeout(800);
  const tabs = await p.locator('nav a').count();
  check('Phone shows bottom tab bar', tabs >= 4, tabs + ' tabs');
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check('No horizontal scroll on phone', !overflow);
  await p.screenshot({ path: OUT + '/06-phone-clients.png' });
  await c.close();
  check('No JavaScript errors', errors.length === 0, errors.join(' | '));
  console.log(results.join('\n'));
  await b.close();
})().catch(e => { console.log(results.join('\n')); console.error('FATAL', e.message); process.exit(1); });
