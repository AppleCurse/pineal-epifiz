#!/usr/bin/env node
/**
 * PINEAL · GERÇEK TARAYICI SMOKE
 *
 * Neden var: `npm run check` yalnız tip/şablon doğrular; jsdom testleri de
 * gerçek bir tarayıcı değildir. Bu betik Vite dev sunucusunu GERÇEK Chromium
 * ile açar, beş yüzeyi tek tek gezer, gerçek düğmelere basar ve ağ katmanını
 * (Vite proxy → FastAPI) tarayıcı origin'inden ölçer.
 *
 * 2026-11-11'de bu betik üç gerçek hata buldu:
 *   1) LiveControlPanel `position: fixed; inset: 0` ile tüm görünümü kaplayıp
 *      yüzey sekme çubuğunu örtüyordu → kullanıcı CANLI SİSTEM'den çıkamıyordu.
 *   2) `apiFetch('/health')` Vite proxy'sinde yoktu → telemetri paneli
 *      geliştirmede her zaman "offline" görünüyordu.
 *   3) Kanıt grafı yalnız bileşenin kendi başlatma düğmesinden gelen görev
 *      kimliğini kullanıyordu → ATLAS yüzeyinden başlatılan görevde graf boş
 *      kalıyordu.
 *
 * KULLANIM
 *   node tools/browser-smoke/smoke.mjs
 *   BASE=http://127.0.0.1:1420 TASK_ID=op_... CHROME_PATH=/yol/chromium \
 *   LD_LIBRARY_PATH=/yol/nss node tools/browser-smoke/smoke.mjs
 *
 * GEREKSİNİMLER
 *   - Çalışan Vite dev sunucusu (npm run dev → port 1420)
 *   - Çalışan backend (uvicorn backend.api:app → port 8000)
 *   - Bir Chromium ikilisi. `playwright-core` + `@sparticuz/chromium` paketleri
 *     kendi Chromium'larını getirir; sistemde kurulu bir Chromium varsa
 *     CHROME_PATH ile verin.
 *
 * ÇIKTI
 *   .smoke/ altında ekran görüntüleri + report.json (git dışında tutulur).
 */
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:1420';
const TASK = process.env.TASK_ID || '';
const OUT = process.env.OUT_DIR || path.resolve(process.cwd(), '.smoke');
fs.mkdirSync(OUT, { recursive: true });

async function loadBrowser() {
  const { chromium: pw } = await import('playwright-core');
  let executablePath = process.env.CHROME_PATH;
  const args = ['--no-sandbox', '--disable-dev-shm-usage'];
  if (!executablePath) {
    const mod = await import('@sparticuz/chromium');
    const chromium = mod.default ?? mod;
    executablePath = await chromium.executablePath();
    args.push(...chromium.args);
  }
  return { pw, executablePath, args };
}

const { pw, executablePath, args } = await loadBrowser();
const browser = await pw.launch({ executablePath, args, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
const page = await ctx.newPage();

const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => pageErrors.push(String(e)));
page.on('requestfailed', (r) => failedRequests.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText}`));

const report = { base: BASE, taskId: TASK, steps: [] };
let failures = 0;
const step = (name, data = {}) => {
  report.steps.push({ name, ...data });
  console.log('STEP', name, JSON.stringify(data));
};
const check = (name, ok, data = {}) => {
  if (!ok) failures += 1;
  step(name, { ok, ...data });
};

const tab = (i) => page.locator('.surface-tabs button').nth(i).evaluate((el) => el.click());

try {
  const resp = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  check('goto', resp?.status() === 200, { status: resp?.status() });
  await page.waitForSelector('.unified-shell', { timeout: 20000 });
  await page.waitForTimeout(2000);
  step('shell_mounted', { title: await page.title() });

  // ---- 1) ATLAS OBSERVATORY (varsayılan yüzey) ----
  const observatory = await page.locator('.surface-stage').innerText();
  check('observatory_rendered', observatory.length > 100, { chars: observatory.length });
  await page.screenshot({ path: path.join(OUT, '01-observatory.png') });

  // ---- 2) KOMUTA (AtlasPinealCockpit) ----
  const tabCount = await page.locator('.surface-tabs button').count();
  check('surface_tabs', tabCount === 5, { count: tabCount });
  await tab(1);
  await page.waitForSelector('.agent-matrix-chip', { timeout: 15000 });
  await page.waitForTimeout(600);
  const chips = page.locator('button.agent-matrix-chip');
  check('command_surface', (await chips.count()) === 12, { agentChips: await chips.count() });

  // Klavye erişilebilirliği: 2026-11-11'de div'lere role/tabindex eklendi.
  const stations = page.locator('[role="button"].sovereign-station');
  check('keyboard_stations', (await stations.count()) === 2, { count: await stations.count() });
  await stations.first().focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  check('keyboard_enter_works', (await stations.first().getAttribute('aria-pressed')) === 'true');
  await chips.nth(3).click();
  await page.waitForTimeout(250);
  check('chip_click_selected', (await chips.nth(3).getAttribute('aria-pressed')) === 'true');
  await page.screenshot({ path: path.join(OUT, '02-command.png') });

  // ---- 3) KANIT RADARI (gerçek graf) ----
  await tab(2);
  await page.waitForTimeout(1500);
  const evidence = await page.locator('.surface-stage').innerText();
  check('evidence_surface', evidence.length > 200, { chars: evidence.length });
  await page.screenshot({ path: path.join(OUT, '03-evidence.png') });

  // ---- 4) CANLI SİSTEM — panel sekme çubuğunu ÖRTMEMELİ ----
  await tab(3);
  await page.waitForTimeout(1200);
  const tabsAfterLive = await page.locator('.surface-tabs button:nth-child(1)').isVisible();
  check('live_panel_does_not_cover_tabs', tabsAfterLive, {
    note: 'position:fixed regresyonu — panel tüm görünümü kaplamamalı',
  });
  const liveText = await page.locator('.surface-stage').innerText();
  check('live_surface', liveText.length > 200, { chars: liveText.length });
  await page.screenshot({ path: path.join(OUT, '04-live.png') });

  // ---- 5) MUHAREBE MASASI ----
  await tab(4);
  await page.waitForTimeout(1200);
  const warroom = await page.locator('.surface-stage').innerText();
  check('warroom_surface', warroom.length > 200, { chars: warroom.length });
  await page.screenshot({ path: path.join(OUT, '05-warroom.png') });

  // ---- 6) Tarayıcı origin'inden proxy → backend ----
  const proxy = await page.evaluate(async (taskId) => {
    const out = {};
    const health = await fetch('/health');
    out.health = health.status;
    if (taskId) {
      const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/graph?client_id=browser-smoke`);
      out.graphStatus = res.status;
      const body = await res.json();
      out.graph = {
        available: body.available,
        nodes: (body.nodes || []).length,
        edges: (body.edges || []).length,
        node_count: body.node_count,
        edge_count: body.edge_count,
      };
    }
    return out;
  }, TASK);
  check('browser_health_via_proxy', proxy.health === 200, { status: proxy.health });
  if (TASK) check('browser_graph_via_proxy', proxy.graph?.available === true, proxy.graph || {});

  // ---- 7) WebSocket (tarayıcıdan, proxy üzerinden) ----
  const ws = await page.evaluate(() => new Promise((resolve) => {
    const url = `ws://${location.host}/ws/browser-smoke-${Date.now()}`;
    let done = false;
    const finish = (r) => { if (!done) { done = true; try { window.__smokeWs?.close(); } catch {} resolve(r); } };
    const socket = new WebSocket(url);
    window.__smokeWs = socket;
    socket.onopen = () => finish({ opened: true, url });
    socket.onerror = () => finish({ opened: false, url, error: 'ws_error' });
    socket.onclose = (e) => finish({ opened: false, url, close: e.code });
    setTimeout(() => finish({ opened: false, url, error: 'timeout' }), 8000);
  }));
  check('browser_websocket', ws.opened === true, ws);
} catch (err) {
  failures += 1;
  step('EXCEPTION', { message: String(err) });
  try { await page.screenshot({ path: path.join(OUT, '99-error.png'), fullPage: true }); } catch {}
}

// Google Fonts gibi üçüncü taraf istekler kapalı ağlarda düşer; bunlar ürün
// hatası değildir, raporda ayrı işaretlenir.
const externalOnly = (u) => /^https?:\/\/(?!127\.0\.0\.1|localhost)/.test(u);
report.consoleErrors = consoleErrors;
report.pageErrors = pageErrors;
report.failedRequests = failedRequests;
report.failedExternalOnly = failedRequests.every((f) => externalOnly(f.split(' ')[1] || ''));
report.failures = failures;
report.pass = failures === 0;

await browser.close();
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));

console.log('\n===== SUMMARY =====');
console.log('steps     :', report.steps.length);
console.log('failures  :', failures);
console.log('pageErrors:', pageErrors.length);
console.log('net fails :', failedRequests.length, report.failedExternalOnly ? '(yalnız harici)' : '');
if (failedRequests.length) console.log(failedRequests.slice(0, 5).join('\n'));
console.log('rapor     :', path.join(OUT, 'report.json'));
process.exit(failures === 0 ? 0 : 1);
