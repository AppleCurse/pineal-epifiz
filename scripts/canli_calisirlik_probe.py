#!/usr/bin/env python3
"""Canlı çalışırlık kanıtı — "boş teneke mi?" sorusuna ÖLÇÜM ile cevap.

İki mod:

  **A · `sunucu`** — gerçekten ayakta duran bir sunucuya GERÇEK HTTP istekleri
  atar (``uvicorn backend.api:app``). Uç envanteri canlı ``/openapi.json``'dan
  okunur; her uç için durum kodu ve gövde şekli kaydedilir. Bu mod, "uç var ama
  çalışmıyor" iddiasını sayıyla sınar: 500 mü, dürüst 4xx mi, gerçek 200 mü?

  **B · `kanit`** — süreç içi operatör kabuğu (TestClient = gerçek ASGI yığını).
  Kasa mandalı repo'nun KENDİ onayladığı desenle açılır (oda mandalı; **sahte
  anahtar malzemesi YAZILMAZ** — entegrasyon testlerinin kullandığı desenin
  aynısı). Kapılar açıkken motorun ÜRETTİĞİ GERÇEK ÇIKTILAR toplanır:
  dil tespiti, rapor paketi (markdown/pdf/şema dosyaları), crawl4ai ile gerçek
  sayfa → metin, ajan rostosu, yetenek durum tablosu ve LLM ağ geçidinin
  kimlik bilgisi YOKKEN ne dediği (dürüstlük sınavı).

Çıktı: ``reports/canli_calisirlik_<mod>.json`` (+ `kanit` modunda
``reports/canli_kanit/`` altına gerçek üretilmiş dosyalar).

Kullanım::

    python scripts/canli_calisirlik_probe.py sunucu --base-url http://127.0.0.1:8000
    python scripts/canli_calisirlik_probe.py kanit
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CLIENT_ID = "canli-kanit"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ A · sunucu
def mod_sunucu(base_url: str) -> dict:
    import httpx

    out: dict[str, Any] = {"mod": "sunucu", "base_url": base_url, "zaman": time.time()}
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0) as cli:
        health = cli.get("/health")
        out["health"] = {"status": health.status_code, "body": _kisa(health)}

        schema = cli.get("/openapi.json")
        out["openapi"] = {"status": schema.status_code}
        assert schema.status_code == 200, "canlı /openapi.json okunamadı"
        paths = schema.json().get("paths", {})

        rows: list[dict[str, Any]] = []
        for path, ops in sorted(paths.items()):
            if not path.startswith("/api/"):
                continue
            if "{" in path:  # yol parametresi isteyen uçlar ayrı sınıfta
                rows.append({"path": path, "methods": sorted(ops), "status": None,
                             "not": "yol parametresi gerekir"})
                continue
            for method in sorted(ops):
                if method not in {"get", "post"}:
                    continue
                try:
                    if method == "get":
                        r = cli.get(path)
                    else:
                        # Gövde gerektiren POST'lar 422 döner — bu da DÜRÜST cevaptır
                        # (uç ayakta, sözleşme denetimi çalışıyor; 500 değil).
                        r = cli.post(path, json={})
                    rows.append({
                        "path": path, "methods": [method], "status": r.status_code,
                        "body": _kisa(r),
                    })
                except Exception as exc:
                    rows.append({"path": path, "methods": [method],
                                 "status": None, "hata": f"{type(exc).__name__}: {exc}"})
        out["uclar"] = rows
        out["ozet"] = _ozet(rows)
    return out


def _kisa(resp) -> Any:
    """Gövdenin ŞEKLİ (ilk 240 karakter) — sır sızdırmaz, uçların dili burada."""
    try:
        data = resp.json()
    except Exception:
        text = resp.text or ""
        return {"tur": "metin", "ilk": text[:240]}
    if isinstance(data, dict):
        return {"tur": "nesne", "anahtarlar": sorted(data)[:18],
                "ilk": json.dumps(data, ensure_ascii=False)[:240]}
    return {"tur": type(data).__name__, "ilk": json.dumps(data, ensure_ascii=False)[:240]}


def _ozet(rows: list[dict]) -> dict:
    from collections import Counter

    c = Counter(str(r.get("status")) for r in rows if r.get("status") is not None)
    return {
        "toplam_deneme": len([r for r in rows if r.get("status") is not None]),
        "durum_dagilimi": dict(sorted(c.items())),
        "500_sayisi": c.get("500", 0),
        "200_sayisi": c.get("200", 0),
    }


# ------------------------------------------------------------------- B · kanıt
def mod_kanit() -> dict:
    # Kapılar: motoru gerçekten koşturmak için açılır (operatör senaryosu).
    from agent_core.capabilities.policy import MANAGED_GATE_FLAGS

    for flag in MANAGED_GATE_FLAGS:  # yönetilen TÜM kapılar açık (operatör senaryosu)
        os.environ[flag] = "true"
    os.environ.setdefault("CRAWL4AI_RENDERER", "http")

    from fastapi.testclient import TestClient

    from backend import api
    from agent_core.capabilities.registry import bootstrap, default_registry
    from agent_core.capabilities.policy import PolicyState, PolicyKernel
    from agent_core.capabilities.state import enabled_flags

    out: dict[str, Any] = {"mod": "kanit", "zaman": time.time(),
                           "client_id": CLIENT_ID, "adimlar": []}

    with TestClient(api.app) as client:
        # [KASA MANDALI] Repo'nun onayladığı desen: oda mandalı açılır.
        # Sahte anahtar malzemesi YAZILMAZ; yalnız odanın mandalı kalkar.
        client.get(f"/api/telemetry?client_id={CLIENT_ID}")
        room = api.get_room(CLIENT_ID)
        room["vault"]["or_key"] = True
        out["kasa_mandali"] = "oda mandalı açıldı (sahte anahtar yok)"

        def step(name: str, fn):
            started = time.time()
            try:
                value = fn()
                out["adimlar"].append({"adim": name, "ok": True,
                                       "sure_ms": int((time.time() - started) * 1000),
                                       "sonuc": value})
            except Exception as exc:
                out["adimlar"].append({"adim": name, "ok": False,
                                       "sure_ms": int((time.time() - started) * 1000),
                                       "hata": f"{type(exc).__name__}: {exc}"})

        # 1 · Dil tespiti (yerel/deterministik)
        def _dil():
            r = client.post("/api/language/detect",
                            json={"text": "Mösyö, bu cümle Türkçedir ve kanıt üretir.",
                                  "client_id": CLIENT_ID})
            return {"status": r.status_code, "govde": _kisa_http(r)}

        step("dil_tespiti", _dil)

        # 2 · Rapor fabrikası: hangi format GERÇEKTEN üretilebiliyor
        def _rapor_durum():
            r = client.get("/api/report/status")
            return {"status": r.status_code, "govde": _kisa_http(r)}

        step("rapor_durumu", _rapor_durum)

        # 3 · Gerçek rapor paketi (dosyalar diske yazılır)
        def _rapor_uret():
            r = client.post("/api/report/build", json={
                "title": "Canlı kanıt raporu",
                "client_id": CLIENT_ID,
                "subject": "kapasite denetimi",
                "formats": ["markdown", "pdf", "diagram"],
                # GERÇEK kanonik kanıt şeması (agent_core/domain/evidence_models.py):
                # evidence_id/epistemic_type/source_engine/content zorunlu.
                # Şema dışı satır UYDURULMAZ; reddedilirse raporda "reddedilen" görünür.
                "evidence": [
                    {"evidence_id": "ev_" + "a1b2c3d4e5f6a7b8c9d0",
                     "epistemic_type": "observation",
                     "source_engine": "scripts/canli_calisirlik_probe.py",
                     "source_status": "observed",
                     "content": "Gerçek sunucuya HTTP isteği atıldı ve yanıt alındı."},
                    {"evidence_id": "ev_" + "0f1e2d3c4b5a69788796",
                     "epistemic_type": "observation",
                     "source_engine": "agent_core.services.report_factory",
                     "source_status": "observed",
                     "content": "Rapor paketi diske gerçek dosya yazdı (md/pdf/png + manifest)."},
                ],
            })
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            files = []
            for fmt, row in (body.get("formats") or {}).items() if isinstance(body, dict) else []:
                for entry in (row or {}).get("artifacts") or []:
                    p = REPO / str(entry.get("path") or "")
                    if p.is_file():
                        files.append({"format": fmt, "dosya": str(p.relative_to(REPO)),
                                      "bayt": p.stat().st_size,
                                      "sha256": (entry.get("sha256") or sha256_file(p))[:20],
                                      "muhur_dogrulandi": (entry.get("sha256") or sha256_file(p)) == sha256_file(p)})
            return {"status": r.status_code, "diskte": files,
                    "reddedilen_kanit": {fmt: (row or {}).get("rejected_item_count")
                                         for fmt, row in (body.get("formats") or {}).items()}
                    if isinstance(body, dict) else None}

        step("rapor_uret", _rapor_uret)

        # 4 · Gerçek sayfa → metin (crawl4ai; tek serbest dış alan: github.com)
        def _crawl():
            r = client.post("/api/experimental/crawl/fetch", json={
                "url": "https://github.com/AppleCurse/pineal-epifiz",
                "client_id": CLIENT_ID,
            })
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            markdown = ""
            if isinstance(body, dict):
                markdown = str(body.get("markdown") or body.get("text") or "")
            return {"status": r.status_code, "bayt": len(markdown),
                    "ilk_200": markdown[:200], "govde": _kisa_http(r) if not markdown else None}

        step("gercek_sayfa_metin", _crawl)

        # 5 · Ajan rostosu
        def _ajanlar():
            r = client.get("/api/agents/status")
            return {"status": r.status_code, "govde": _kisa_http(r)}

        step("ajan_rostosu", _ajanlar)

        # 6 · Ses durumu (dürüstlük: motor yokken "hazır" denmemeli)
        def _ses():
            r = client.get("/api/speech/status")
            return {"status": r.status_code, "govde": _kisa_http(r)}

        step("ses_durumu", _ses)

        # 7 · Yetenek tablosu: kapılar açıkken hangisi gerçekten hazır
        def _yetenekler():
            reg = bootstrap(registry=default_registry)
            state = PolicyState(vault_locked=False, rate_ok=True,
                                enabled_flags=enabled_flags(dict(os.environ)))
            kernel = PolicyKernel()
            rows = []
            for row in reg.status(state=state, kernel=kernel):
                rows.append({"id": row["id"], "hazir": row["available"],
                             "karar": row["policy_allowed"], "sebep": row["reason"]})
            return {"kayitli": len(rows),
                    "hazir": sum(1 for r in rows if r["hazir"] and r["karar"] is not False),
                    "satirlar": rows}

        step("yetenek_tablosu", _yetenekler)

        def _gercek():
            return asyncio.run(_gercek_kosumlar(client))

        step("gercek_yetenek_kosumlari", _gercek)

        # 9b · SES uçtan uca: gerçek WAV say → gerçek dosya servis et → dinle
        srv_ses, port_ses, kayit_ses, wav_ses = _taklit_tts_stt()

        def _ses_say():
            r = client.post("/api/speech/say",
                            json={"text": "Mösyö, kanıt cümlesi.", "client_id": CLIENT_ID})
            body = r.json()
            ses = client.get(body.get("url") or "/api/speech/audio/yok")
            return {"durum": r.status_code, "available": body.get("available"),
                    "reason": body.get("reason"), "url": body.get("url"),
                    "audio_durum": ses.status_code, "audio_bayt": len(ses.content),
                    "riff_mi": ses.content[:4] == b"RIFF",
                    "sha256": hashlib.sha256(ses.content).hexdigest()[:16]}

        step("ses_uctan_uca_say", _ses_say)

        def _ses_dinle():
            r = client.post("/api/speech/listen?client_id=" + CLIENT_ID,
                            files={"file": ("kanit.wav", wav_ses, "audio/wav")})
            body = r.json()
            return {"durum": r.status_code, "available": body.get("available"),
                    "transcript": body.get("transcript"), "engine": body.get("engine"),
                    "reason": body.get("reason")}

        step("ses_uctan_uca_dinle", _ses_dinle)
        srv_ses.shutdown()
        out["yerel_uc_kayitlari"] = {"port": port_ses, "istekler": kayit_ses}

    # 8 · LLM ağ geçidi: kimlik bilgisi YOKKEN ne diyor? (dürüstlük sınavı)
    def _beyin():
        import asyncio

        from agent_core.services.llm_gateway import LLMGateway

        gw = LLMGateway()
        try:
            result = asyncio.run(gw.query("ping", agent_name="shadow_executor", task="canli-kanit"))
            return {"yanit_verdi": True, "ozet": str(result)[:200]}
        except Exception as exc:
            return {"yanit_verdi": False, "hata": f"{type(exc).__name__}: {str(exc)[:220]}"}

    out["llm_gecidi_kimliksiz"] = _beyin()
    return out


def _kisa_http(resp) -> Any:
    return _kisa(resp)



# ------------------------------------------------- 9 · gerçek yetenek koşumları
async def _gercek_kosumlar(client) -> dict:
    """[ÖZ] "Kod var" ≠ "çalışıyor": yetenekleri RUNNER üzerinden GERÇEKTEN koşturur.

    Her satır: yetenek id, koştu mu, kanıt üretti mi, payload'da ne var
    (dosya yolu/bayt/sha256 gibi somut çıktı). Uydurma yok: yetenek
    kullanılamazsa `unavailable_reason` aynen yazılır.
    """
    from agent_core.capabilities import CapabilityContext, PolicyState, run_capability
    from agent_core.capabilities.state import enabled_flags

    state = PolicyState(vault_locked=False, rate_ok=True,
                        enabled_flags=enabled_flags(dict(os.environ)))
    isler = [
        ("renderer.report.pdf", {"title": "Gerçek koşum", "subject": "kanıt",
                                 "evidence": []}),
        ("renderer.report.diagram", {"title": "Gerçek koşum", "subject": "kanıt",
                                     "evidence": []}),
        ("extractor.web.crawl4ai", {"url": "https://github.com/AppleCurse/pineal-epifiz"}),
        ("extractor.text.language", {"text": "Bu cümle Türkçe yazılmıştır."}),
        ("extractor.web.trafilatura", {"url": "https://github.com/AppleCurse/pineal-epifiz"}),
        ("extractor.web.scrapling", {"url": "https://github.com/AppleCurse/pineal-epifiz"}),
        ("renderer.report.video", {"title": "Gerçek koşum", "subject": "kanıt",
                                   "evidence": []}),
        ("sensor.identity.holehe", {"email": "test@example.com"}),
    ]
    rows = []
    for cap_id, params in isler:
        # Yeteneğin beklediği girdi adı farklı olabilir: iki yaygın adı dene.
        ctx = CapabilityContext(subject=str(params.get("url") or params.get("email") or
                                           params.get("text") or ""), params=params)
        try:
            result = await run_capability(cap_id, ctx, state=state)
            payload = result.payload
            ozet = payload if isinstance(payload, (str, int, float, bool)) else None
            if isinstance(payload, dict):
                ozet = {k: payload[k] for k in list(payload)[:8]}
            rows.append({
                "yetenek": cap_id,
                "available": bool(result.available),
                "denied_by": result.denied_by,
                "sebep": result.unavailable_reason,
                "kanit_sayisi": len(result.items),
                "sure_ms": result.duration_ms,
                "hata": result.error,
                "payload_ozet": str(ozet)[:400] if ozet is not None else None,
            })
        except Exception as exc:
            rows.append({"yetenek": cap_id, "available": False,
                         "exception": f"{type(exc).__name__}: {exc}"})
    return {"satirlar": rows,
            "calisan": sum(1 for r in rows if r.get("available")),
            "kayitli_toplam": len(rows)}



# ------------------------------------------------- 10 · istek yolu (yerel taklit)
def mod_taklit() -> dict:
    """LLM İSTEK YOLU kanıtı — yerel TAKLİT sağlayıcı (bulut DEĞİL, ücret YOK).

    Amaç: "tel kopuk mu, kimlik mi yok?" ayrımını yapmak. Yerel bir
    OpenAI-uyumlu sahte sunucu ayağa kaldırılır; ağ geçidi ona yönlendirilir ve
    GERÇEK HTTP isteği atılır. İstek gövdesi, yetkilendirme başlığı ve yanıt
    işleme hattı uçtan uca sınanır. **Bu bir bulut sağlayıcı kanıtı DEĞİLDİR**;
    kanıtladığı şey: istek yolu eksiksiz, eksik olan yalnız gerçek sağlayıcı.
    """
    import http.server
    import socketserver
    import threading

    istekler: list[dict] = []

    class _Sunucu(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # sessiz
            return

        def _gonder(self, obj, code=200):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if "models" in self.path:
                self._gonder({"object": "list", "data": [{"id": "taklit-model", "object": "model"}]})
            else:
                self._gonder({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(n).decode("utf-8", "replace")
            istekler.append({
                "yol": self.path,
                "yetki_basligi_var": bool(self.headers.get("authorization")),
                "govde_ilk_160": raw[:160],
            })
            try:
                payload = json.loads(raw or "{}")
            except Exception:
                payload = {}
            self._gonder({
                "id": "chatcmpl-taklit-1", "object": "chat.completion", "created": 0,
                "model": payload.get("model", "bilinmez"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant",
                                         "content": "TAKLIT-YANIT: istek yolu tamam"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Sunucu)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    #: Canlı çağrı kilidi AÇILIR ama hedef YEREL taklittir: dış ağa çıkılmaz.
    os.environ["LIVE_LLM_E2E"] = "1"
    os.environ["NINEROUTER_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
    os.environ["NINEROUTER_API_KEY"] = "taklit-anahtar"
    os.environ["PINEAL_ALLOW_UNPRICED_MODELS"] = "1"

    from agent_core.services.llm_gateway import LLMGateway

    out: dict[str, Any] = {"mod": "taklit", "taklit_port": port,
                           "uyari": ("Bu bir BULUT sağlayıcı kanıtı değildir; yerel "
                                     "taklit sunucuya giden İSTEK YOLU kanıtıdır.")}
    gw = LLMGateway()

    def _cagir(etiket: str, **kwargs):
        try:
            yanit = asyncio.run(gw.query("kanıt amaçlı tek satır yanıt ver", **kwargs))
            out[etiket] = {"yanit": str(yanit)[:200], "basarili": True}
        except Exception as exc:
            out[etiket] = {"hata": f"{type(exc).__name__}: {str(exc)[:200]}", "basarili": False}

    _cagir("duz_cagri", agent_name="shadow_executor")
    _cagir("pineal_rota", model="pineal-general-reasoning")

    #: 3 · Kapalı porta yönlendir: DÜRÜST hata vermeli (sahte başarı YOK).
    os.environ["NINEROUTER_BASE_URL"] = "http://127.0.0.1:1/v1"
    gw2 = LLMGateway()
    try:
        asyncio.run(gw2.query("ping", agent_name="shadow_executor"))
        out["kapali_port"] = {"basarili": True, "uyari": "BEKLENMEDİK: kapalı port yanıt verdi"}
    except Exception as exc:
        out["kapali_port"] = {"basarili": False, "hata": f"{type(exc).__name__}: {str(exc)[:200]}"}

    srv.shutdown()
    out["taklit_sunucuya_ulasan_istek"] = istekler
    out["ozet"] = {
        "taklit_istek_sayisi": len(istekler),
        "duz_cagri_ok": out["duz_cagri"]["basarili"],
        "pineal_rota_ok": out["pineal_rota"]["basarili"],
        "kapali_port_durust_ret": not out["kapali_port"]["basarili"],
    }
    return out

def _taklit_tts_stt():
    """Yerel taklit TTS/STT uçları: sözleşme (istek gövdesi/yanıt) GERÇEK olarak sınanır.

    TTS ucu gerçek bir sinüs WAV döndürür; STT ucu multipart dosyayı alıp
    JSON metin döndürür. Amaç: "motor yok" ile "zincir kopuk" ayrımı.
    """
    import http.server
    import math
    import socketserver
    import struct
    import threading

    rate, saniye = 8000, 0.4
    samples = int(rate * saniye)
    data = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 220 * i / rate)))
                    for i in range(samples))
    wav = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
           + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
           + b"data" + struct.pack("<I", len(data)) + data)

    kayit: list[dict] = []

    class _H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def _gonder(self, govde: bytes, tip: str, code=200):
            self.send_response(code)
            self.send_header("content-type", tip)
            self.send_header("content-length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(n)
            if self.path.startswith("/tts"):
                kayit.append({"uc": "tts", "govde_ilk": raw[:120].decode("utf-8", "replace")})
                self._gonder(wav, "audio/wav")
            else:
                kayit.append({"uc": "stt", "govde_bayt": len(raw),
                              "multipart": b"--" in raw[:200]})
                self._gonder(json.dumps({"text": "taklit transkript: ses yerelde çözüldü"}).encode(),
                             "application/json")

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _H)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    os.environ["ENABLE_LOCAL_TTS"] = "true"
    os.environ["ENABLE_LOCAL_STT"] = "true"
    os.environ["PINEAL_TTS_URL"] = f"http://127.0.0.1:{port}/tts"
    os.environ["PINEAL_STT_URL"] = f"http://127.0.0.1:{port}/stt"
    return srv, port, kayit, wav


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mod", choices=["sunucu", "kanit", "taklit"])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.mod == "sunucu":
        data = mod_sunucu(args.base_url)
    elif args.mod == "taklit":
        data = mod_taklit()
    else:
        data = mod_kanit()
    name = args.out or f"reports/canli_calisirlik_{args.mod}.json"
    path = REPO / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")
    print(json.dumps(data.get("ozet") or data.get("llm_gecidi_kimliksiz") or {},
                     ensure_ascii=False, indent=1))
    print(f"yazıldı: {path} ({path.stat().st_size} bayt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
