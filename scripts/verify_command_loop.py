#!/usr/bin/env python3
"""CANLI KOMUT DÖNGÜSÜ DOĞRULAYICI — "komut → görev → ajan → kanıt → çağrı izi".

Amaç: panelin gördüğü zincirin **gerçekten** çalıştığını tek komutla kanıtlamak.
Bu betik hiçbir veri UYDURMAZ; yalnız çalışan API'den okur ve neyi neden
göremediğini açıkça yazar.

Kullanım (kendi makinende, 9Router + kasa + Playwright hazırken):

    python scripts/verify_command_loop.py --url https://instagram.com/KULLANICI/

Seçenekler:
    --base-url   API kökü (varsayılan http://127.0.0.1:8000)
    --client-id  oda kimliği (varsayılan: verify_<zaman damgası>)
    --timeout    görev bitene kadar beklenecek saniye (varsayılan 300)
    --message    komut metni (varsayılan: "<url> incele")

Çıkış kodu:
    0  → döngü kanıtlandı (görev kimliği üretildi ve görev durumu okunabildi)
    1  → döngü KIRILDI (komut reddedildi / görev kimliği yok / durum okunamadı)
    2  → ön koşul eksik (API erişilemiyor) — bu da bir başarısızlıktır

Kanıt zinciri WS `result` karesinde gelir; bu yüzden betik WS'yi de dinler.
WS yakalama **isteğe bağlıdır**: `websockets` paketi kurulu değilse betik
yine çalışır ve kanıt zincirinin bu modda görülemediğini **açıkça** yazar
(sessizce boş kalmaz). Prod imajında paket kuruludur (`Dockerfile:41`).

Dürüstlük kuralı: her alan ya GERÇEK bir ölçümdür ya da "ÖLÇÜLEMEDİ + sebep".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:  # WS yakalama İSTEĞE BAĞLIDIR (kanıt zinciri WS `result` karesinde gelir)
    import websockets  # type: ignore
except Exception:  # pragma: no cover - paket yoksa betik yine çalışır
    websockets = None  # type: ignore

TIMEOUT = 20
INSUFFICIENT = "ÖLÇÜLEMEDİ"


# ------------------------------------------------------------------ HTTP yardım

def _opener() -> urllib.request.OpenerDirector:
    # Doğrulanmamış SSL: yerel 9Router/özel proxy kurulumlarında sertifika
    # hatası döngüyü yanlışlıkla "bağlantı yok" gibi gösterir.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> Tuple[int, Any]:
    """JSON isteği → (durum kodu, gövde). Hata durumunda gövde None olabilir."""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _opener().open(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:  # ağ hatası
        return 0, f"{type(exc).__name__}: {exc}"
    try:
        return status, json.loads(raw)
    except Exception:
        return status, raw


# ------------------------------------------------------------------ WS yakalama

class WsCapture:
    """WS karelerini toplayan dinleyici (kanıt zinciri `result` karesinde gelir).

    Paket yoksa (`websockets` kurulu değil) betik çalışmaya devam eder ve
    kanıt zincirinin WS olmadan görülemediğini açıkça yazar.
    """

    def __init__(self, base_url: str, client_id: str, api_key: Optional[str] = None):
        self._base = base_url.rstrip("/")
        self._client_id = client_id
        self._api_key = api_key
        self.messages: List[Dict[str, Any]] = []
        self.error: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()

    def start(self, wait: float = 6.0) -> bool:
        """Dinleyiciyi başlatır; bağlantı kurulana kadar bekler.

        Bağlantı kurulamazsa `self.error` yazılır ve False döner — kare
        kaçırmak sessizce yutulmaz.
        """
        if websockets is None:
            self.error = "websockets paketi yok (pip install websockets)"
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(wait)
        if self.error and not self.messages and not self._connected:
            return False
        return True

    _connected = False

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._consume())
        except Exception as exc:  # ağ/WS hatası — sessiz yutulmaz
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._ready.set()
            try:
                loop.close()
            except Exception:
                pass

    async def _consume(self) -> None:
        scheme = "wss" if self._base.startswith("https://") else "ws"
        host = self._base.split("://", 1)[-1]
        url = f"{scheme}://{host}/ws/{urllib.parse.quote(self._client_id)}"
        async with websockets.connect(url) as ws:
            self._connected = True
            self._ready.set()
            if self._api_key:
                await ws.send(json.dumps({"type": "auth", "token": self._api_key}))
            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if isinstance(data, dict):
                    self.messages.append(data)

    def stop(self) -> None:
        """Zarif kapanış: döngü kesilmez, bağlantı normal kapanır."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    # -- toplanan çerçeveden türetilen özetler ------------------------------
    def snapshots(self) -> List[Dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == "snapshot_update"]

    def results(self) -> List[Dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == "result"]

    def last_snapshot(self) -> Dict[str, Any]:
        snaps = self.snapshots()
        return snaps[-1] if snaps else {}

    def evidence_chain(self) -> List[Dict[str, Any]]:
        for frame in reversed(self.results()):
            chain = frame.get("evidence_chain")
            if isinstance(chain, list):
                return chain
        return []


# ------------------------------------------------------------------ biçimleme

def line(head: str, value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return f"  {head}: {INSUFFICIENT} (boş)"
    return f"  {head}: {value}"


def fmt_cost(value: Any) -> str:
    return f"${float(value):.6f}" if isinstance(value, (int, float)) else INSUFFICIENT


def summarize_agents(run: Dict[str, Any]) -> List[str]:
    runs = (run or {}).get("runs") or {}
    out: List[str] = []
    for name in sorted(runs):
        row = runs[name] or {}
        ids = row.get("call_ids") or []
        out.append(
            f"    - {name}: durum={row.get('status')} "
            f"çağrı={len(ids)} kanıt_kimliği={len(row.get('evidence_ids') or [])}"
        )
    return out


# ------------------------------------------------------------------ ana akış

def verify(base_url: str, client_id: str, url: str, message: str, timeout: int) -> int:
    base = base_url.rstrip("/")
    api_key = os.getenv("PINEAL_API_TOKEN") or os.getenv("PINEAL_API_KEY") or None
    problems: List[str] = []

    print("=" * 72)
    print("CANLI KOMUT DÖNGÜSÜ DOĞRULAMASI")
    print("=" * 72)
    print(f"  API      : {base}")
    print(f"  oda      : {client_id}")
    print(f"  hedef URL: {url}")

    # --- 0) API erişilebilir mi? --------------------------------------------
    status, health = http_json(f"{base}/api/aspasia/state?client_id={urllib.parse.quote(client_id)}",
                               api_key=api_key)
    if status == 0:
        print(f"\n[1/5] ÖN KOŞUL: API'ye ulaşılamadı → {health}")
        print("  Sebep: sunucu çalışmıyor ya da adres/port yanlış.")
        print("  Çözüm: uvicorn ile API'yi başlat (bkz. RUNBOOK 'Başlatma').")
        return 2
    if status != 200:
        print(f"\n[1/5] ÖN KOŞUL: /api/aspasia/state → HTTP {status}")
        print(f"  Gövde: {str(health)[:300]}")
        print("  Sebep: yetkilendirme/ortam ayarı (PINEAL_REQUIRE_AUTH).")
        return 2
    registry = (health or {}).get("registry") or []
    print(f"\n[1/5] ÖN KOŞUL: API erişilebilir · kayıtlı ajan: {len(registry)}")

    # --- 0b) WS dinleyicisi (kanıt zinciri orada gelir) ------------------------
    capture = WsCapture(base, client_id, api_key)
    ws_ok = capture.start()
    if not ws_ok:
        print(f"\n[1b/5] WS YAKALAMA: kapalı — {capture.error}")
        print("  Kanıt zinciri yalnız WS `result` karesinde gelir; bu modda görülemez.")

    # --- 1) komut gönder ------------------------------------------------------
    print("\n[2/5] KOMUT: POST /api/aspasia/command")
    status, cmd = http_json(
        f"{base}/api/aspasia/command",
        method="POST",
        payload={"client_id": client_id, "user_message": message},
        api_key=api_key,
    )
    print(f"  HTTP {status} · gövde: {str(cmd)[:400]}")
    if status != 200 or not isinstance(cmd, dict):
        problems.append("komut ucu 200 dönmedi")
        task_id = None
    else:
        task_id = cmd.get("task_id")
        if not cmd.get("accepted"):
            problems.append(f"komut kabul edilmedi (reason={cmd.get('reason')})")
        if cmd.get("accepted") and not task_id:
            problems.append("komut kabul edildi ama görev kimliği üretilmedi")

    # --- 2) görev durumunu izle ------------------------------------------------
    print("\n[3/5] GÖREV DURUMU (poll)")
    deadline = time.time() + max(10, timeout)
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        status, state = http_json(
            f"{base}/api/aspasia/state?client_id={urllib.parse.quote(client_id)}",
            api_key=api_key,
        )
        if status == 200 and isinstance(state, dict):
            last = state
            run = state.get("run") or {}
            if run.get("state") not in (None, "idle") and run.get("is_final"):
                break
        time.sleep(4)
    run = last.get("run") or {}
    snap = capture.last_snapshot()
    if snap and not run.get("status"):
        run = snap
    print(line("görev durumu", run.get("status")))
    print(line("canlı ajan", run.get("current")))
    print(line("planlanan ajanlar", run.get("planned")))
    print("  ajan koşu kayıtları:")
    agent_lines = summarize_agents(run)
    if agent_lines:
        for row in agent_lines:
            print(row)
    else:
        print(f"    - {INSUFFICIENT} (koşu kaydı yok)")

    # --- 3) çağrı izi + kimlik bağı -------------------------------------------
    print("\n[4/5] ÇAĞRI İZİ + KİMLİK BAĞI")
    calls = last.get("calls") or []
    binding = last.get("call_binding") or {}
    print(line("görünen çağrı", len(calls)))
    print(line("günlük toplamı", binding.get("log_total")))
    print(line("koşu çağrısı", binding.get("run_call_count")))
    print(line("bağlı çağrı", binding.get("bound_call_count")))
    missing = binding.get("missing_call_ids") or []
    print(line("günlükte olmayan kimlik", missing or "yok"))
    if binding.get("missing_reason"):
        print(f"  sebep: {binding['missing_reason']}")
    for call in calls[:10]:
        print(
            f"    - {call.get('call_id')} · ajan={call.get('agent_id')} "
            f"· model={call.get('model')} · süre={call.get('duration_ms')} ms "
            f"· maliyet={fmt_cost(call.get('cost_usd'))} "
            f"· bağlı={','.join(call.get('bound_agents') or []) or 'koşuya bağlı değil'}"
        )
    if calls:
        unbound = [c for c in calls if not (c.get("bound_agents") or [])]
        if unbound:
            print(f"  NOT: {len(unbound)} çağrı hiçbir koşuya bağlı değil "
                  "(koşu dışı çağrı — ör. aspasia niyet çağrısı) — bu bir kopukluk DEĞİLDİR.")

    # --- 4) panelin gördüğü alanlar -------------------------------------------
    print("\n[5/5] PANELİN GÖRDÜĞÜ ALANLAR")
    print(line("bütçe (harcanan)", fmt_cost((last.get("budget") or {}).get("spend_usd"))))
    quota = last.get("quota") or {}
    print(line("kota", {k: (v or {}).get("status") for k, v in quota.items()} or "yok"))
    anomalies = last.get("anomalies") or {}
    print(line("anomaliler", anomalies))
    chain = capture.evidence_chain()
    print(line("WS snapshot sayısı", len(capture.snapshots())))
    print(line("WS sonuç karesi", len(capture.results())))
    print(line("kanıt zinciri satırı", len(chain)))
    for row in chain[:20]:
        print(
            f"    - ajan={row.get('agent')} · tür={row.get('evidence_type') or '—'} "
            f"· zaman={row.get('timestamp') or '—'} · sonuç={str(row.get('result'))[:120]}"
        )
    if capture.error:
        print(f"  WS notu: {capture.error}")

    # --- sonuç ------------------------------------------------------------------
    capture.stop()
    print("\n" + "=" * 72)
    if problems:
        print("SONUÇ: DÖNGÜ KIRILDI")
        for problem in problems:
            print(f"  - {problem}")
        print("  Kanıt yukarıdaki ham çıktılardır; hiçbir değer uydurulmadı.")
        return 1
    print("SONUÇ: DÖNGÜ KANITLANDI")
    print(f"  - komut kabul edildi, görev kimliği: {task_id}")
    print(f"  - ajan koşu kaydı: {len(run.get('runs') or {})} ajan")
    print(f"  - çağrı izi: {len(calls)} çağrı görünür, "
          f"{binding.get('bound_call_count')} çağrı koşuya bağlı")
    print(f"  - kanıt zinciri: {len(chain)} satır (WS `result` karesinden)")
    print("  Panelde aynı veriler: /api/aspasia/state + WS snapshot_update")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Canlı komut döngüsü doğrulayıcı")
    parser.add_argument("--base-url", default=os.getenv("PINEAL_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--client-id", default=f"verify_{int(time.time())}")
    parser.add_argument("--url", required=True, help="incelenecek profil URL'si")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    message = args.message or f"{args.url} incele"
    try:
        return verify(args.base_url, args.client_id, args.url, message, args.timeout)
    except KeyboardInterrupt:
        print("\nİptal edildi (sonuç: DOĞRULANMADI — döngü tamamlanmadı).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
