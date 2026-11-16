// Cloudflare Pages Function — /ws/* → ws(s)://BACKEND_ORIGIN/ws/* proxy.
// v5.0: Agent Rack canlı köprüsü — Redis Pub/Sub -> WS -> Tauri/Rack
//
// Neden: telemetri/odak WebSocket bağlantısı eski deployment'da
// 404 dönüyordu (statik edge'de WS endpoint'i yok). Bu uç upgrade
// el sıkışmasını yapıp iki ucu çift yönlü pompa ile birleştirir.
// v5.0 eklenti: agent_status_update mesajlarını şeffaf iletir —
// sağdaki Agent Rack slotları (Mirror Truth, Autonomous Verifier vb.)
// Redis üzerinden Ready/Active/Wait anlık değişir.
//
// Kimlik doğrulama yol üzerinden yapılır (/ws/{client_id}); Cloudflare'ın
// istemci WebSocket API'si özel istek başlığı iletmediği için bu tasarım
// header tabanlı auth gerektirmez — bilinçli seçim.
//
// Dürüstlük sözleşmesi: BACKEND_ORIGIN ayarlı değilse 502; upgrade
// değilse 426. Uzak uç bağlanamazsa istemci ucunu KAPATIRIZ (asılı
// bağlantı bırakmayız).

export const onRequest = async (context: any) => {
  const origin: string | undefined = context.env.BACKEND_ORIGIN;
  if (!origin) {
    return new Response(
      JSON.stringify({
        error: {
          code: "BACKEND_ORIGIN_NOT_CONFIGURED",
          message:
            "Bu deployment için BACKEND_ORIGIN secret'ı ayarlanmamış. " +
            "npx wrangler pages secret put BACKEND_ORIGIN",
        },
      }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  const upgrade = (context.request.headers.get("upgrade") || "").toLowerCase();
  if (!upgrade.includes("websocket")) {
    return new Response("Bu uç yalnızca WebSocket upgrade kabul eder.", { status: 426 });
  }

  const requestOrigin = context.request.headers.get("origin");
  const allowedOrigins = String(context.env.WS_ALLOWED_ORIGINS || "").split(",").map((value: string) => value.trim()).filter(Boolean);
  if (!requestOrigin || allowedOrigins.length === 0 || !allowedOrigins.includes(requestOrigin)) {
    return new Response("WebSocket origin reddedildi.", { status: 403 });
  }

  const subpath: string[] = context.params.path || [];
  if (subpath.length !== 1 || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(subpath[0])) {
    return new Response("Geçersiz WebSocket client_id.", { status: 400 });
  }
  const url = new URL(context.request.url);
  const bare = origin.replace(/\/+$/, "");
  let wsTarget: string;
  if (bare.startsWith("https://")) {
    wsTarget = "wss://" + bare.slice("https://".length);
  } else if (bare.startsWith("http://")) {
    wsTarget = "ws://" + bare.slice("http://".length);
  } else if (bare.startsWith("wss://") || bare.startsWith("ws://")) {
    wsTarget = bare;
  } else {
    wsTarget = "wss://" + bare;
  }
  wsTarget += "/ws/" + subpath.join("/") + (url.search || "");

  const upstream: WebSocket = new WebSocket(wsTarget);

  const [pipeEnd, clientEnd] = Object.values(new WebSocketPair()) as [
    WebSocket,
    WebSocket,
  ];
  pipeEnd.accept();

  const guard = (w: WebSocket) => () => {
    if (w.readyState === WebSocket.OPEN || w.readyState === WebSocket.CONNECTING) {
      try {
        w.close();
      } catch {
        /* zaten kapalı */
      }
    }
  };

  // v5.0: Agent Rack mesaj filtresi — agent_status_update, telemetry_update,
  // snapshot_update, result, log tipleri şeffaf iletilir. Hiçbir mesaj
  // sessizce düşürülmez.
  //
  // Agent Rack kare tipi çözümleyicisi: hata ayıklama sayacı bu fonksiyonu
  // kullanır (agent_status_update/telemetry_update/snapshot_update/result/log
  // ve EventBus fallback kareleri).
  const isAgentStatusMessage = (data: string): boolean => {
    try {
      const parsed = JSON.parse(data);
      return (
        parsed.type === "agent_status_update" ||
        parsed.type === "telemetry_update" ||
        parsed.type === "snapshot_update" ||
        parsed.type === "result" ||
        parsed.type === "log" ||
        (parsed.event && parsed.event.agent_name) // EventBus fallback
      );
    } catch {
      return false;
    }
  };

  // EDGE LOG'UNA İÇERİK YAZILMAZ: hata ayıklama logu varsayılan olarak KAPALI,
  // yalnız WS_DEBUG_LOG=1 ile açılır. Açıkken bile payload değil yalnız SAYAÇ
  // ve BOYUT yazılır (kaç kare, kaç bayt); böylece canlı hata ayıklama korunur,
  // mesaj içeriği loglara kopyalanmaz.
  const debugLog = String(context.env?.WS_DEBUG_LOG || "") === "1";
  let forwardedFrames = 0;
  let forwardedBytes = 0;
  let agentStatusFrames = 0;

  // [P0-15 · D-01 · 2026-11-11] İLK MESAJ KAYBI KAPATILDI.
  //
  // Ölçülen kusur: `upstream` hâlâ CONNECTING (0) iken `pipeEnd.accept()`
  // çağrılıp istemciye 101 dönülüyordu. İstemci (App.svelte) bağlantı açılır
  // açılmaz İLK mesaj olarak `{type:"auth", token}` gönderiyor; eski pump
  // `if (to.readyState !== WebSocket.OPEN) return;` yüzünden bu çerçeveyi
  // SESSİZCE çöpe atıyordu → backend 5 sn sonra 1008 ile kapatıyordu.
  //
  // Düzeltme: CONNECTING durumundaki hedefe giden çerçeveler TAMPONLANIR ve
  // `open` olayında SIRAYLA iletilir. Kuyruk TAVANLIDIR: tavan aşılırsa
  // sessiz düşürme yerine bağlantı 1013 ile KAPATILIR (uydurma "çalışıyor"
  // görüntüsü yok). `send` hatası da sessiz yutulmaz: iki uç da kapatılır.
  const MAX_PENDING_FRAMES = 64;
  const MAX_PENDING_BYTES = 256 * 1024;

  const pump = (from: WebSocket, to: WebSocket, label: string) => {
    // Yalnız istemci->upstream yönünde tampon gerekir (istemci erken konuşan
    // taraftır); yine de tek yerden uygulanır: hedef CONNECTING ise tamponla.
    const pending: any[] = [];
    let pendingBytes = 0;
    let closed = false;
    const closeBoth = (code: number) => {
      if (closed) return;
      closed = true;
      // `from` kapanışı YETMEZ: Cloudflare'de `from` bu pump'ın sunucu ucu
      // olabilir ve istemci ucunun kapanma kodunu taşımaz. Bu yüzden pompa
      // çiftinin GÖRÜNÜR ucuna (varsa `peer`) kod açıkça iletilir.
      for (const socket of new Set([from, (from as any).peer, to])) {
        if (!socket) continue;
        try {
          socket.close(code);
        } catch {
          /* zaten kapalı */
        }
      }
      guard(to)();
    };
    to.addEventListener("open", () => {
      while (pending.length > 0) {
        const frame = pending.shift();
        try {
          to.send(frame);
        } catch {
          closeBoth(1011);
          return;
        }
      }
      pendingBytes = 0;
    });
    from.addEventListener("message", (ev: any) => {
      if (to.readyState === WebSocket.CONNECTING) {
        const size = typeof ev.data === "string" ? ev.data.length : 0;
        if (pending.length >= MAX_PENDING_FRAMES || pendingBytes + size > MAX_PENDING_BYTES) {
          // Sessiz düşürme YASAK: tavan aşıldıysa açıkça kapat.
          closeBoth(1013);
          return;
        }
        pending.push(ev.data);
        pendingBytes += size;
        return;
      }
      if (to.readyState !== WebSocket.OPEN) return;
      // Tüm mesajlar şeffaf iletilir — özellikle agent_status_update
      // Agent Rack slotlarının Ready/Active/Wait canlı değişimi için kritik
      if (label === "upstream->client") {
        forwardedFrames += 1;
        if (typeof ev.data === "string") {
          forwardedBytes += ev.data.length;
          if (isAgentStatusMessage(ev.data)) agentStatusFrames += 1;
        }
        if (debugLog && forwardedFrames % 50 === 0) {
          // İÇERİK YOK: yalnız sayaç/boyut. Payload asla loglanmaz.
          console.log(
            `[AgentRack] frames=${forwardedFrames} bytes=${forwardedBytes} ` +
              `agentStatus=${agentStatusFrames}`,
          );
        }
      }
      try {
        to.send(ev.data);
      } catch {
        // Sessiz yutma yok: gönderim başarısızsa iki uç da kapatılır.
        closeBoth(1011);
      }
    });
    from.addEventListener("close", guard(to));
    from.addEventListener("error", guard(to));
  };

  pump(pipeEnd, upstream, "client->upstream");
  pump(upstream, pipeEnd, "upstream->client");

  return new Response(null, { status: 101, webSocket: clientEnd });
};
