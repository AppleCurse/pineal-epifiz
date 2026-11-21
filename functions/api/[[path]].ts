// Cloudflare Pages Function — /api/* → BACKEND_ORIGIN/api/* HTTP proxy.
//
// Neden: eski deployment'da frontend Cloudflare'da, FastAPI ayrı bir
// kökende (Railway vb.) duruyordu ve /api/* hiçbir yere proxy'lenmediği
// için 404 dönüyordu. Bu catch-all uç tüm /api/* isteklerini
// BACKEND_ORIGIN'e taşıyor.
//
// Dürüstlük sözleşmesi: BACKEND_ORIGIN ayarlı değilse proxy uydurma
// davranış GÖSTERMEZ — 502 + açık hata kodu döner.
//
// Not: Cloudflare Functions dizini wrangler.toml'ın YANINDA (kök)
// olmalıdır; frontend/ içine konursa çalışmaz.

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "cf-connecting-ip",
  "cf-ipcountry",
  "x-forwarded-for",
]);

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

  const subpath: string[] = context.params.path || [];
  const url = new URL(context.request.url);
  const target =
    origin.replace(/\/+$/, "") +
    "/api/" +
    subpath.join("/") +
    (url.search || "");

  const req = context.request;
  const headers = new Headers();
  req.headers.forEach((value: string, key: string) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  // [2026-11-21] Gerçek istemci IP'si KENAR TARAFINDAKİ `cf-connecting-ip`'tir
  // (Cloudflare, müşteri-gönderimini bununla DEĞİŞTİRİR). İsteğe AYNEN
  // `x-forwarded-for` olarak yazarız; istemci-gönderilen XFF zaten HOP_BY_HOP
  // ile silindi, yani backend iki-başlı XFF zinciri GÖRMEZ. Backend bu değeri
  // YALNIZ PINEAL_TRUST_PROXY_HEADERS=true iken okur (bkz. #8). Yoksa başlık
  // hiç yazılmaz (backend soket adresine düşer).
  const edgeClientIp = req.headers.get("cf-connecting-ip");
  if (edgeClientIp) headers.set("x-forwarded-for", edgeClientIp);

  const method = req.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body,
      redirect: "manual",
    });
  } catch (e) {
    return new Response(
      JSON.stringify({
        error: {
          code: "BACKEND_UNREACHABLE",
          message: "Backend kökenine ulaşılamadı: " + String((e as any)?.message || e),
        },
      }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  // Yönlendirmeler (örn. kimlik doğrulama) müdahalesiz geçirilir.
  if (upstream.status >= 300 && upstream.status < 400) {
    const location = upstream.headers.get("location");
    if (location) {
      return new Response(null, { status: upstream.status, headers: { location } });
    }
  }

  const resHeaders = new Headers();
  upstream.headers.forEach((value: string, key: string) => {
    const k = key.toLowerCase();
    if (HOP_BY_HOP.has(k) || k === "content-encoding" || k === "content-length") return;
    resHeaders.set(key, value);
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: resHeaders,
  });
};
