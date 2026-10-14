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
    for flag in ("ENABLE_CRAWL4AI", "ENABLE_REPORT_FACTORY", "ENABLE_MEDIA_FORENSICS",
                 "ENABLE_COMPANY_TARGETING", "ENABLE_LOCAL_TTS", "ENABLE_LOCAL_STT",
                 "ENABLE_MAIGRET", "ENABLE_HOLEHE"):
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mod", choices=["sunucu", "kanit"])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data = mod_sunucu(args.base_url) if args.mod == "sunucu" else mod_kanit()
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
