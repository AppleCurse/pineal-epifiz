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

  const subpath: string[] = context.params.path || [];
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
  // [PROD AUDIT 2026-10-11 · P1] Bu fonksiyon TANIMLIYDI AMA HİÇ ÇAĞRILMIYORDU
  // (ölü kod). Aşağıdaki hata ayıklama sayacı artık bunu GERÇEKTEN kullanır.
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

  // [PROD AUDIT 2026-10-11 · P1] EDGE LOG'UNA İÇERİK YAZILMAZ.
  //
  // Ölçülen kusur: pompa, upstream->client yönündeki HER agent_status_update
  // karesinin İLK 200 KARAKTERİNİ koşulsuz olarak Cloudflare edge loguna
  // basıyordu (`console.log("[AgentRack] Forwarding: " + ev.data.slice(0,200))`).
  // Bu kareler hedef kişi hakkında toplanan telemetriyi/ajan meta verisini
  // taşır; yani üçüncü kişilerin kişisel verisi, operatörün kontrolü
  // dışındaki bir sağlayıcının (Cloudflare) loglarına kopyalanıyordu. Projenin
  // kendi tüzüğü (docs/PINEAL_TUZUK.md Madde 3 ve backend'deki redact_text
  // disiplini) sır/içerik sızıntısını yasaklar; edge katmanı bu disiplinin
  // dışında kalmıştı.
  //
  // Yeni davranış: hata ayıklama logu VARSAYILAN OLARAK KAPALI ve yalnız
  // WS_DEBUG_LOG=1 ile açılır. Açıkken bile İÇERİK değil, yalnız SAYAÇ ve
  // BOYUT yazılır (kaç kare, kaç bayt, tip dağılımı). Böylece canlı hata
  // ayıklama yeteneği korunur, veri minimizasyonu bozulmaz.
  const debugLog = String(context.env?.WS_DEBUG_LOG || "") === "1";
  let forwardedFrames = 0;
  let forwardedBytes = 0;
  let agentStatusFrames = 0;

  const pump = (from: WebSocket, to: WebSocket, label: string) => {
    from.addEventListener("message", (ev: any) => {
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
      to.send(ev.data);
    });
    from.addEventListener("close", guard(to));
    from.addEventListener("error", guard(to));
  };

  pump(pipeEnd, upstream, "client->upstream");
  pump(upstream, pipeEnd, "upstream->client");

  return new Response(null, { status: 101, webSocket: clientEnd });
};
