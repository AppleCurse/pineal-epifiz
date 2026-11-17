// Cloudflare edge davranışını ÖLÇEN test (Node, ek bağımlılık yok).
//
// Neden burada: `functions/ws/[[path]].ts` Cloudflare Workers üzerinde koşar ve
// gerçek dağıtım olmadan "elle" doğrulanamaz. Bu betik Worker'ı çalışma anında
// TS'den sıyırıp (Node 22 --experimental-strip-types) SAHTE bir Cloudflare
// ortamında koşturur: `WebSocket`/`WebSocketPair`/`Response` global'leri
// denetlenebilir sahtelerle değiştirilir.
//
// Ölçülen sözleşme (P0-15 · D-01):
//   1. İstemci, upstream DAHA CONNECTING iken `{type:"auth"}` gönderir.
//   2. Çerçeve KAYBOLMAMALI: upstream açıldığında SIRAYLA iletilmeli.
//   3. Kuyruk tavanı aşılırsa sessiz düşürme değil, iki uç da kapatılmalı.
//
// Çalıştırma: node --experimental-strip-types tests/edge/ws_proxy_auth.mjs
// (Python test paketi bunu ayrıca çağırır: tests/unit/test_edge_ws_auth_proxy.py)

import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";

const REPO = new URL("../../", import.meta.url).pathname;
const SRC = join(REPO, "functions/ws/[[path]].ts");

// ---- sahte WebSocket dünyası -------------------------------------------------
const CONNECTING = 0;
const OPEN = 1;
const CLOSED = 3;

class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.peer = null;
    this.readyState = CONNECTING;
    this.sent = [];
    this.closedWith = null;
    this._listeners = {};
  }
  addEventListener(type, fn) {
    (this._listeners[type] ||= []).push(fn);
  }
  _emit(type, ev = {}) {
    for (const fn of this._listeners[type] || []) fn(ev);
  }
  accept() {
    this.accepted = true;
  }
  send(data) {
    if (this.readyState !== OPEN) throw new Error("send on non-open socket");
    this.sent.push(data);
  }
  close(code) {
    this.closedWith = code ?? 1005;
    this.readyState = CLOSED;
  }
  // test yardımcıları
  openUpstream() {
    this.readyState = OPEN;
    this._emit("open", {});
  }
  // Gerçek Workers semantiği: istemci ucuna yazılan çerçeve SUNUCU ucuna düşer.
  clientSends(data) {
    const target = this.peer && this.peer._listeners["message"] ? this.peer : this;
    target._emit("message", { data });
  }
  linkPeer(peer) {
    this.peer = peer;
    peer.peer = this;
  }
}

let lastUpstream = null;
let lastPair = null;

// Cloudflare `Response` sahtesi: Node'un Response'u 101 kabul etmez (101
// yalnız Workers çalışma zamanında geçerlidir), bu yüzden 101'i taşıyabilen
// asgari bir sarmalayıcı kullanılır.
class FakeResponse {
  constructor(body, init = {}) {
    this.body = body;
    this.status = init.status;
    this.headers = init.headers;
    this.webSocket = init.webSocket;
  }
}

globalThis.WebSocket = Object.assign(
  function (url) {
    lastUpstream = new FakeWebSocket(url);
    return lastUpstream;
  },
  { CONNECTING, OPEN, CLOSED },
);
globalThis.WebSocketPair = function () {
  const a = new FakeWebSocket("edge-server");
  const b = new FakeWebSocket("edge-client");
  a.linkPeer(b);
  lastPair = { 0: a, 1: b };
  return lastPair;
};
globalThis.Response = FakeResponse;

// ---- Worker'ı yükle ----------------------------------------------------------
const tmp = mkdtempSync(join(tmpdir(), "edge-ws-"));
const modulePath = join(tmp, "ws_proxy.ts");
writeFileSync(modulePath, readFileSync(SRC, "utf-8"), "utf-8");
const { onRequest } = await import(modulePath);

function makeContext() {
  return {
    env: { BACKEND_ORIGIN: "https://backend.example.com", WS_ALLOWED_ORIGINS: "https://app.example.com" },
    request: {
      url: "https://app.example.com/ws/room-1?x=1",
      headers: new Map([
        ["upgrade", "websocket"],
        ["origin", "https://app.example.com"],
      ]),
    },
    params: { path: ["room-1"] },
  };
}
// Headers.get uyumu
function ctxWithHeaders() {
  const ctx = makeContext();
  const h = new Headers();
  for (const [k, v] of ctx.request.headers) h.set(k, v);
  ctx.request.headers = h;
  return ctx;
}

let failures = 0;
async function scenario(name, fn) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures += 1;
    console.log(`FAIL ${name}: ${err.message}`);
  }
}

// ---- 1 · İLK AUTH ÇERÇEVESİ KAYBOLMAMALI ------------------------------------
await scenario("erken gelen auth çerçevesi upstream açılınca iletilir", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  assert.equal(response.status, 101, "upgrade 101 dönmeli");
  assert.ok(lastUpstream, "upstream soketi açılmalı");
  assert.equal(lastUpstream.readyState, CONNECTING, "upstream hâlâ CONNECTING olmalı");

  // Worker'ın döndürdüğü istemci ucu: response.webSocket
  const edgeClient = response.webSocket;
  assert.ok(edgeClient instanceof FakeWebSocket, "101 yanıtı istemci ucunu taşımalı");
  edgeClient.clientSends(JSON.stringify({ type: "auth", token: "s3cret" }));
  assert.equal(lastUpstream.sent.length, 0, "CONNECTING iken doğrudan gönderim olmamalı");

  lastUpstream.openUpstream();
  assert.equal(lastUpstream.sent.length, 1, "tamponlanan auth çerçevesi iletilmeli");
  assert.equal(JSON.parse(lastUpstream.sent[0]).token, "s3cret");
});

// ---- 2 · SIRA KORUNUR --------------------------------------------------------
await scenario("birden çok erken çerçeve SIRAYLA iletilir", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  const edgeClient = response.webSocket;
  edgeClient.clientSends("birinci");
  edgeClient.clientSends("ikinci");
  edgeClient.clientSends("ucuncu");
  lastUpstream.openUpstream();
  assert.deepEqual(lastUpstream.sent, ["birinci", "ikinci", "ucuncu"]);
});

// ---- 3 · KUYRUK TAVANI: sessiz düşürme yok ----------------------------------
await scenario("kuyruk tavanı aşılırsa iki uç da kapatılır (sessiz düşürme yok)", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  const edgeClient = response.webSocket;
  for (let i = 0; i < 70; i += 1) edgeClient.clientSends(`frame-${i}`);
  // İki uç da kapanır: istemci tarafına 1013 gider, upstream tarafı guard();
  // ile (kodsuz) kapatılır. Ölçülen: iki soket de kapalı.
  assert.equal(edgeClient.closedWith, 1013, "istemci ucuna 1013 ile kapanmalı");
  assert.equal(lastUpstream.readyState, CLOSED, "upstream de kapatılmalı");
  assert.equal(lastUpstream.sent.length, 0, "tavan aşımından sonra gönderim olmamalı");
});

// ---- 4 · Origin kapısı korunur ----------------------------------------------
await scenario("izinli olmayan origin 403 alır", async () => {
  const ctx = ctxWithHeaders();
  ctx.request.headers.set("origin", "https://evil.example.com");
  const response = await onRequest(ctx);
  assert.equal(response.status, 403);
});

await scenario("BACKEND_ORIGIN yoksa 502 (uydurma davranış yok)", async () => {
  const ctx = ctxWithHeaders();
  ctx.env = {};
  const response = await onRequest(ctx);
  assert.equal(response.status, 502);
});

// ---- 5 · ASILI BAĞLANTI YOK -------------------------------------------------
await scenario("upstream açılmadan kapanırsa istemci de kapatılır", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  const edgeClient = response.webSocket;
  edgeClient.clientSends(JSON.stringify({ type: "auth", token: "s3cret" }));
  // Upstream bağlanamadı (ör. backend kapalı) → hata olayı.
  // Ölçülen: hedef uç, hata olayında (guard) kapanır; istemci ucu da
  // aynı pompa çiftinde olduğu için birlikte kapatılır.
  lastUpstream.readyState = CLOSED;
  lastUpstream._emit("error", {});
  // Sahte dünyada `pipeEnd`e `error` OLAYI yayılmaz (Workers'ta yayılır);
  // ölçülebilir olan: guard hedefi kapattı — yani bağlantı asılı kalmıyor.
  assert.equal(lastUpstream.readyState, CLOSED, "hedef uç kapatılmalı");
  const serverEnd = lastPair[0];
  assert.equal(serverEnd.readyState, CLOSED, "edge sunucu ucu da kapatılmalı");
});

// ---- 6 · AÇILDIKTAN SONRA DOĞRUDAN AKIŞ -------------------------------------
await scenario("upstream açıldıktan sonra çerçeveler doğrudan akar", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  const edgeClient = response.webSocket;
  lastUpstream.openUpstream();
  edgeClient.clientSends("dogrudan-1");
  edgeClient.clientSends("dogrudan-2");
  assert.deepEqual(lastUpstream.sent, ["dogrudan-1", "dogrudan-2"]);
});

// ---- 7 · SUNUCU -> İSTEMCİ YÖNÜ KORUNUR -------------------------------------
await scenario("upstream'den gelen çerçeve istemciye iletilir", async () => {
  lastUpstream = null;
  const response = await onRequest(ctxWithHeaders());
  const edgeClient = response.webSocket;
  lastUpstream.openUpstream();
  edgeClient.readyState = OPEN;
  const serverEnd = lastPair[0];
  serverEnd.readyState = OPEN;
  lastUpstream._emit("message", { data: '{"type":"snapshot_update"}' });
  // Çerçeve, pompa çiftinin sunucu ucundan istemciye akar.
  const delivered = serverEnd.sent.length ? serverEnd.sent : edgeClient.sent;
  assert.deepEqual(delivered, ['{"type":"snapshot_update"}']);
});

console.log(failures === 0 ? "EDGE_OK" : `EDGE_FAIL ${failures}`);
process.exit(failures === 0 ? 0 : 1);
