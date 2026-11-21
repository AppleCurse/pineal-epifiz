// LinkedIn uzantısının SAF çekirdeğini (extensions/chrome-linkedin/core.js)
// Node ile ölçen test — ek bağımlılık YOK, tarayıcı gerekmez.
//
// Neden burada: core.js [2026-11-11 SAHTE SONUÇ TEMİZLİĞİ] ile "browser-
// bağımsız çekirdek" diye yazıldı ama testinin adı (tests/edge/
// linkedin_extension.mjs) depoya hiç inmedi; canlı content.js eski
// davranışı taşıyordu. Bu betik o boşluğu kapatır: çekirdeğin dürüstlük
// sözleşmesini ÖLÇER.
//
// Çalıştırma: node tests/edge/linkedin_extension.mjs
// (Python test paketi bunu ayrıca çağırır: tests/unit/test_edge_linkedin_extension.py)

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const require = createRequire(join(REPO, "package.json"));
const core = require(join(REPO, "extensions", "chrome-linkedin", "core.js"));

const results = [];
const check = (name, fn) => {
  fn();
  results.push(`PASS ${name}`);
};

// ── 1 · Hedef tespiti UYDURULMAZ ─────────────────────────────────
check("ad yoksa hedef yoktur (uydurma 'LinkedIn Profili' YOK)", () => {
  const t = core.extractProfileData({ name: "", title: "", url: "https://www.linkedin.com/in/ornek/" });
  assert.equal(t.name, "");
  assert.equal(t.hasTarget, false);
  assert.equal(t.display, core.TARGET_MISSING_TEXT);
});

check("ad + geçerli /in/ URL'si → hasTarget true, display ad (title)", () => {
  const t = core.extractProfileData({
    name: "Ada Lovelace",
    title: "Mühendis",
    canonical: "https://www.linkedin.com/in/adalovelace/?originalSubdomain=tr",
  });
  assert.equal(t.hasTarget, true);
  assert.equal(t.display, "Ada Lovelace (Mühendis)");
  assert.equal(t.url, "https://www.linkedin.com/in/adalovelace/", "query atılmalı");
});

// ── 2 · URL kapısı ───────────────────────────────────────────────
for (const [url, expected] of [
  ["https://www.linkedin.com/in/someone/", true],
  ["https://linkedin.com/in/someone", true],
  ["https://www.linkedin.com/posts/someone_konu-123", false], // /in/ dışı profil değil
  ["https://www.linkedin.com/in/", false],
  ["https://evil.example.com/in/someone/", false],
  ["https://www.linkedin.com.evil.com/in/x/", false],
  ["ftp://www.linkedin.com/in/x/", false],
  ["not-a-url", false],
]) {
  check(`isLinkedInProfileUrl(${JSON.stringify(url)}) → ${expected}`, () => {
    assert.equal(core.isLinkedInProfileUrl(url), expected);
  });
}

// ── 3 · planAnalysis: hedef yoksa istek KURULMAZ ─────────────────
check("clientId yoksa ok:false", () => {
  const plan = core.planAnalysis({ hasTarget: true, url: "https://www.linkedin.com/in/x/" }, "  ");
  assert.equal(plan.ok, false);
});

check("hedef yoksa istek GÖNDERİLMEZ ve nedeni söylenir", () => {
  const target = core.extractProfileData({ name: "", url: "https://www.linkedin.com/in/x/" });
  const plan = core.planAnalysis(target, "ext_123");
  assert.equal(plan.ok, false);
  assert.match(plan.reason, /GÖNDERİLMEDİ/);
});

check("geçerli hedef + clientId → ok:true, gövde sözleşmeye uygun", () => {
  const target = core.extractProfileData({ name: "Ada", url: "https://www.linkedin.com/in/ada/" });
  const plan = core.planAnalysis(target, "ext_123");
  assert.equal(plan.ok, true);
  assert.equal(plan.body.client_id, "ext_123");
  assert.equal(plan.body.url, "https://www.linkedin.com/in/ada/");
  assert.equal(plan.body.scraper_type, "cross");
  assert.deepEqual(Object.keys(plan.body).sort(), ["client_id", "envies", "playlist", "rituals", "scraper_type", "url"]);
});

// ── 4 · normalizeGraph: düğüm yoksa uydurma yok ──────────────────
check("graf + düğümler → state 'graph', sayılar sunucudan aynen", () => {
  const view = core.normalizeGraph({
    available: true,
    node_count: 2,
    edge_count: 1,
    machine_note: "makine izi",
    nodes: [
      { kind: "target", label: "Ada", evidence_count: 3 },
      { kind: "signal", label: "geç yazı", evidence_count: 7 },
    ],
  });
  assert.equal(view.state, "graph");
  assert.match(view.note, /2 düğüm · 1 kenar/);
  assert.match(view.note, /makine izi/);
  assert.equal(view.nodes[1].evidence, 7);
});

check("boş graf + bilinen sebep → REASON_TEXT eşlemesi", () => {
  const view = core.normalizeGraph({ available: false, reason: "no_evidence" });
  assert.equal(view.state, "empty");
  assert.equal(view.note, core.REASON_TEXT.no_evidence);
  assert.equal(view.nodes.length, 0);
});

check("boş graf + BİLİNMEYEN sebep → ham sebep gösterilir (uydurma teşhis yok)", () => {
  const view = core.normalizeGraph({ available: false, reason: "vault_locked_şifre" });
  assert.match(view.note, /vault_locked_şifre/);
});

check("sebep hiç yoksa 'bildirilmedi' denir", () => {
  const view = core.normalizeGraph({ available: false });
  assert.match(view.note, /bildirilmedi/);
});

// ── 5 · normalizeError / serverError: dürüst hata metni ──────────
for (const [status, pattern] of [
  [401, /KİMLİK/],
  [403, /ODA/],
  [423, /KASA/],
  [429, /HIZ/],
  [451, /ÇOCUK/],
]) {
  check(`serverError(${status}) operatör diline çevrilir`, () => {
    assert.match(core.serverError(status, { error: { message: "m" } }), pattern);
  });
}

check("serverError bilinmeyen status → kod ve mesaj aynen", () => {
  const out = core.serverError(500, { error: { code: "X", message: "patladı" } });
  assert.match(out, /500/);
  assert.match(out, /patladı/);
});

// ── 6 · İçerik UYDURULMAZ (salt metin sözleşmeleri) ──────────────
check("graf düğümü label'ı trim edilir, boş label '—' olur", () => {
  const view = core.normalizeGraph({
    available: true,
    nodes: [{ kind: "signal", label: "", evidence_count: Number.NaN }],
  });
  assert.equal(view.nodes[0].label, "—");
  assert.equal(view.nodes[0].evidence, 0);
});

console.log(results.join("\n"));
console.log("LINKEDIN_EXT_OK");
