"""E5 · DENEYSEL MOTOR YOKKEN "ÇALIŞIYOR" GÖRÜNTÜSÜ YOK (Md.1 uydurma yasağı).

ÖLÇÜM (2026-10-07, kasa açık + motorlar kapalı):

    $ TestClient(...).post("/api/experimental/maigret/scan", ...)
    200  {"available": false, "reason": "disabled"}
    200  {"available": false, "reason": "disabled"}   # holehe
    200  {"available": false, "reason": "disabled"}   # crawl4ai

Gövde dürüsttü ama **HTTP seviyesi "istek işlendi" diyordu**. Motorun kendisi
YOKKEN doğan bu görüntü, arayüzün/istemcinin boş bir süreci başarılmış bir iş
gibi okumasına açık kapı bırakır.

Bu sözleşme dosyası üç şeyi birden kilitler:

1. **MOTOR YOK → 400.** `disabled` · `library_missing` · `dependency_broken` ·
   `db_unavailable` sebeplerinde yanıt 400 `MOTOR_UNAVAILABLE` olur; dürüst
   gövde (`available:false` + `reason`) KAYBOLMAZ, üzerine makine-okunur `error`
   eklenir.
2. **MOTOR VAR AMA SONUÇ DÜRÜSTÇE YOK → 200.** `timeout` · `scan_error` ·
   `network_error` · `no_record` · `provider_errors` bir BAŞARISIZLIK değil,
   dürüst bir SONUÇTUR; bunları 400'e çevirmek "her şeyi reddeden kapı"
   yazmak olurdu. Bu ayrım ölçülmeden E5 "tamam" sayılmaz.
3. **YAPISAL DENETİM.** Deneysel motor uçlarından birine kapı eklemeyi unutmak
   mümkün değil: uç, kapıyı çağırmıyorsa test kırmızı yanar. Salt-okunur
   envanter ucu (`/api/experimental/stealth`) gerekçesiyle muaftır.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_core.services.crawl_enricher import CrawlFetchResult
from agent_core.services.holehe_scanner import HoleheScanResult
from agent_core.services.maigret_scanner import MaigretScanResult
from agent_core.services.socid_enricher import SocidRecord
from backend import api
from backend.api import app

# ─────────────────────────────────────────────────────────────────────────────
# Envanter: deneysel MOTOR uçları ve her birinin motor kaynağı
# ─────────────────────────────────────────────────────────────────────────────

#: (path, gövde, motor fonksiyonunun monkeypatch hedefi, monte edilecek sonuç üreticisi)
ENGINE_ENDPOINTS = [
    (
        "/api/experimental/maigret/scan",
        {"username": "soxoj"},
        "agent_core.services.maigret_scanner.scan_username",
    ),
    (
        "/api/experimental/holehe/scan",
        {"email": "a@b.com"},
        "agent_core.services.holehe_scanner.scan_email",
    ),
    (
        "/api/experimental/crawl/fetch",
        {"url": "https://example.com/a"},
        "agent_core.services.crawl_enricher.fetch_readable",
    ),
    (
        "/api/experimental/socid/extract",
        {"url": "https://x.com/alper"},
        "agent_core.services.socid_enricher.extract_profile",
    ),
]

ENGINE_IDS = [p for p, _, _ in ENGINE_ENDPOINTS]

#: Motor/kapı YOKLUĞU sebepleri — 400 üretir (sözleşme: `ENGINE_UNAVAILABLE_REASONS`).
ENGINE_LEVEL_REASONS = ("disabled", "library_missing", "dependency_broken", "db_unavailable")

#: Motor ÇALIŞTI ama sonuç dürüstçe yok — 200 KALIR.
RUNTIME_REASONS = ("timeout", "scan_error", "network_error", "no_record", "provider_errors")

#: Salt-okunur envanter ucu: motor çağırmaz, hedef materyali işlemez.
#: (Kasa muafiyetindeki gerekçeyle aynı: tarayıcı başlatmaz, binary indirmez.)
EXEMPT_ROUTES = {
    "/api/experimental/stealth": (
        "Salt-okunur envanter: hangi stealth motorunun kullanılacağını ve "
        "kullanılabilirliğini RAPORLAR — motor çağırmaz, hedef materyali "
        "işlemez. 400 dönmek operatörün teşhis ekranını bozardı."
    ),
}


def _fake_result(path: str, **kwargs):
    """Uca uygun sahte sonuç nesnesi (motorun gerçek modeliyle)."""
    if "maigret" in path:
        return MaigretScanResult(requested_username="soxoj", **kwargs)
    if "holehe" in path:
        return HoleheScanResult(requested_email="a@b.com", **kwargs)
    if "crawl" in path:
        return CrawlFetchResult(requested_url="https://example.com/a", **kwargs)
    return SocidRecord(source_url="https://x.com/alper", **kwargs)


def _call(client: TestClient, path: str, body: dict):
    return client.post(path, json={**body, "client_id": "e5"})


@pytest.fixture
def _engine_open(monkeypatch):
    """Kasa kapısı AÇIK (E5'in konusu motor kapısıdır, kasa değil)."""
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)


# ─────────────────────────────────────────────────────────────────────────────
# 1) MOTOR YOK → 400 MOTOR_UNAVAILABLE (dürüst gövde korunur)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path,body,target", ENGINE_ENDPOINTS, ids=ENGINE_IDS)
@pytest.mark.parametrize("reason", ENGINE_LEVEL_REASONS)
def test_engine_unavailable_reason_returns_400(
    monkeypatch, _engine_open, path, body, target, reason
):
    """Motor/kapı yokluğu HTTP seviyesinde de görünür: 400 + MOTOR_UNAVAILABLE."""

    async def _fake(*_a, **_k):
        return _fake_result(path, available=False, reason=reason)

    monkeypatch.setattr(target, _fake)
    with TestClient(app) as client:
        r = _call(client, path, body)

    assert r.status_code == 400, f"{path} ({reason}) → {r.status_code}: {r.text[:200]}"
    payload = r.json()
    assert payload["error"]["code"] == "MOTOR_UNAVAILABLE"
    assert payload["error"]["reason"] == reason
    # DÜRÜST SÖZLEŞME KAYBOLMADI: istemci hâlâ makine-okunur sebebi okuyabilir.
    assert payload["available"] is False
    assert payload["reason"] == reason
    # Mesaj net: iş YAPILMADI (boş sonuç da yok).
    assert "ÇALIŞTIRILMADI" in payload["error"]["message"]


def test_engine_disabled_by_default_is_400(monkeypatch, _engine_open):
    """Varsayılan hâl (hiçbir ENABLE_* yok): 200 değil 400.

    Ölçümün birebir tekrarı: bu uç eskiden 200 + `available:false` dönüyordu.
    """
    for env in ("ENABLE_MAIGRET", "ENABLE_HOLEHE", "ENABLE_CRAWL4AI"):
        monkeypatch.delenv(env, raising=False)
    with TestClient(app) as client:
        for path, body, _ in ENGINE_ENDPOINTS:
            r = _call(client, path, body)
            if "socid" in path:
                continue  # socid'in kapısı yok (ENABLE_SOCID yoktur) — ayrı ölçülür
            assert r.status_code == 400, f"{path} → {r.status_code}"
            assert r.json()["error"]["reason"] == "disabled"


# ─────────────────────────────────────────────────────────────────────────────
# 2) MOTOR ÇALIŞTI, SONUÇ DÜRÜSTÇE YOK → 200 (kapı "her şeyi reddetmiyor")
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path,body,target", ENGINE_ENDPOINTS, ids=ENGINE_IDS)
@pytest.mark.parametrize("reason", RUNTIME_REASONS)
def test_honest_runtime_failure_stays_200(
    monkeypatch, _engine_open, path, body, target, reason
):
    """`timeout`/`scan_error`/... bir SONUÇTUR: 200 + available:false kalır.

    Bu test olmadan "motor yokken 400" kuralı "her sonuçta 400"a kayabilirdi;
    o zaman dürüst boş sonuçlar da hata gibi görünürdü (Md.1 ihlali).
    """

    async def _fake(*_a, **_k):
        return _fake_result(path, available=False, reason=reason)

    monkeypatch.setattr(target, _fake)
    with TestClient(app) as client:
        r = _call(client, path, body)

    assert r.status_code == 200, f"{path} ({reason}) → {r.status_code}: {r.text[:200]}"
    payload = r.json()
    assert payload["available"] is False
    assert payload["reason"] == reason
    assert "error" not in payload


@pytest.mark.parametrize("path,body,target", ENGINE_ENDPOINTS, ids=ENGINE_IDS)
def test_successful_engine_run_stays_200(monkeypatch, _engine_open, path, body, target):
    """Motor çalışıp sonuç verdiyse akış normaldir (kapı şeffaf)."""

    async def _fake(*_a, **_k):
        return _fake_result(path, available=True)

    monkeypatch.setattr(target, _fake)
    with TestClient(app) as client:
        r = _call(client, path, body)

    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
    assert r.json()["available"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 3) YAPISAL DENETİM — kapıyı unutmak mümkün değil
# ─────────────────────────────────────────────────────────────────────────────


def _experimental_routes():
    rows = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        endpoint = getattr(route, "endpoint", None)
        if not path.startswith("/api/experimental/") or endpoint is None:
            continue
        rows.append((path, endpoint))
    return sorted(rows, key=lambda r: r[0])


def _engine_route_paths():
    """Hedef materyali işleyen (motor çağıran) deneysel uçlar."""
    return {path for path, _, _ in ENGINE_ENDPOINTS}


def test_route_inventory_is_not_empty():
    """Denetim boş bir tabloya karşı koşup "yeşil" olmasın."""
    assert len(_experimental_routes()) >= 4, [p for p, _ in _experimental_routes()]


def test_every_engine_route_calls_the_gate_or_is_exempt():
    """Her deneysel uç kapıdan geçer; muafiyet yalnız gerekçeli listede olur.

    İki kapı vardır ve ikisi de aynı kuralı uygular — *çalışmayan çağrı 200
    dönmez*: `_engine_unavailable_response` (motor kapalı → 400) ve
    `_module_unavailable_response` (modül/ajan yüklü değil → 503).
    """
    missing = []
    for path, endpoint in _experimental_routes():
        if path in EXEMPT_ROUTES:
            continue
        source = inspect.getsource(endpoint)
        if (
            "_engine_unavailable_response(" not in source
            and "_module_unavailable_response(" not in source
        ):
            missing.append(path)
    assert not missing, (
        "Dürüstlük kapısı olmayan deneysel uçlar: "
        f"{missing} — ya `_engine_unavailable_response(...)` / "
        "`_module_unavailable_response(...)` ekleyin ya da EXEMPT_ROUTES'a "
        "gerekçe yazın."
    )


def test_exempt_route_exists_and_has_a_reason():
    """Hayalet muafiyet yok: liste gerçek bir route'a karşılık gelir."""
    paths = {p for p, _ in _experimental_routes()}
    for path, reason in EXEMPT_ROUTES.items():
        assert path in paths, f"{path} route tablosunda yok"
        assert len(reason) > 30, f"{path} için gerekçe cılız"


# ─────────────────────────────────────────────────────────────────────────────
# 5) MODÜL/AJAN YOKLUĞU → 503 (E5'in kardeş kuralı: çalışmayan çağrı 200 dönmez)
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_shadow_module_is_503_not_200(monkeypatch):
    """`shadow_executor` yokken "Shadow Protocol yüklü değil" artık 200 değil."""
    monkeypatch.setattr(api, "shadow_executor", None)
    with TestClient(app) as client:
        r = client.post("/api/experimental/shadow/analyze", json={"profile": {"name": "x"}})
    assert r.status_code == 503, r.text[:200]
    assert r.json()["error"]["code"] == "MODULE_UNAVAILABLE"
    assert r.json()["error"]["module"] == "shadow_protocol"
    assert r.json()["available"] is False


def test_missing_shadow_generate_module_is_503(monkeypatch):
    monkeypatch.setattr(api, "shadow_executor", None)
    with TestClient(app) as client:
        r = client.post("/api/experimental/shadow/generate", json={"task": {"objective": "x"}})
    assert r.status_code == 503, r.text[:200]
    assert r.json()["error"]["code"] == "MODULE_UNAVAILABLE"


def test_missing_dialogue_module_is_503(monkeypatch):
    monkeypatch.setattr(api, "dialogue_manager", None)
    with TestClient(app) as client:
        r = client.post(
            "/api/experimental/chat/respond",
            json={"task_id": "t1", "target_profile": {}, "user_profile": {}, "target_message": "selam"},
        )
    assert r.status_code == 503, r.text[:200]
    assert r.json()["error"]["code"] == "MODULE_UNAVAILABLE"
    assert r.json()["error"]["module"] == "dialogue_manager"


def test_failed_dialogue_generation_is_not_a_200_success(monkeypatch):
    """Üretim patlarsa çağrı "tamamlandı" GÖRÜNMEZ: 502 + DIALOGUE_FAILED.

    Eskiden `200 + {"error": {"code": "DIALOGUE_FAILED"}}` dönüyordu — yani
    başarısız bir çağrı HTTP seviyesinde başarıydı (Md.1).
    """

    class _Boom:
        sessions: dict = {}

        def start_session(self, *_a, **_k):
            raise RuntimeError("llm_down")

        async def generate_response(self, *_a, **_k):  # pragma: no cover - erişilmez
            raise RuntimeError("llm_down")

    monkeypatch.setattr(api, "dialogue_manager", _Boom())
    with TestClient(app) as client:
        r = client.post(
            "/api/experimental/chat/respond",
            json={"task_id": "t2", "target_profile": {}, "user_profile": {}, "target_message": "selam"},
        )
    assert r.status_code == 502, f"{r.status_code}: {r.text[:200]}"
    assert r.json()["error"]["code"] == "DIALOGUE_FAILED"
    assert r.json()["available"] is False


def test_missing_interpreter_agent_is_503_not_500(monkeypatch, _engine_open):
    """Interpreter ajanı odada yoksa: 500 değil, dürüst 503.

    Ayrıca eski kodda `executor.agents.get(...)` çıplak erişimdi: oda hiç
    kurulmamışsa AttributeError → 500 sızıyordu.
    """
    monkeypatch.setattr(api, "get_room", lambda _cid: {"executor": None})
    # NOT: `ENABLE_INTERPRETER=true` AÇILIŞta bağımlılık kapısını tetikler
    # (`REQUIRED_DEPENDENCY_MISSING: open-interpreter`) ve uygulama hiç
    # başlamaz — bu, kapının DOĞRU davranışıdır. Burada ölçülen şey kapı
    # SONRASI yoldur: bayrak açıkken ajan odada kayıtlı değilse ne dönüyor?
    with TestClient(app) as client:
        monkeypatch.setenv("ENABLE_INTERPRETER", "true")
        r = client.post(
            "/api/experimental/interpreter/execute",
            json={"client_id": "e5", "prompt": "print(1)", "auto_run": False},
        )
    assert r.status_code == 503, f"{r.status_code}: {r.text[:200]}"
    assert r.json()["error"]["code"] == "MODULE_UNAVAILABLE"
    assert r.json()["error"]["module"] == "interpreter_agent"


def test_module_gate_and_engine_gate_are_distinct_codes():
    """İki kapı iki farklı durumu anlatır: karıştırılırsa teşhis yanlış olur."""
    assert api._module_unavailable_response(None, "m").status_code == 503
    assert "MOTOR_UNAVAILABLE" in inspect.getsource(api._engine_unavailable_response)
    assert "MODULE_UNAVAILABLE" in inspect.getsource(api._module_unavailable_response)


def test_gate_helper_is_the_single_source():
    """Kapının tek sahibi `_engine_unavailable_response`; kural kopyalanmaz."""
    source = inspect.getsource(api)
    assert "def _engine_unavailable_response(" in source
    assert "ENGINE_UNAVAILABLE_REASONS" in source
    assert "MOTOR_UNAVAILABLE" in source


# ─────────────────────────────────────────────────────────────────────────────
# 4) SÖZLÜK DENETİMİ — sebep sözlüğü motor kodundan kopmasın
# ─────────────────────────────────────────────────────────────────────────────


def test_engine_level_reasons_are_the_declared_set():
    """400 üreten sebepler TAM olarak beyan edilmiş kümedir."""
    assert api.ENGINE_UNAVAILABLE_REASONS == frozenset(ENGINE_LEVEL_REASONS)


def test_runtime_reasons_are_never_hard_failures():
    """Çalışma-zamanı sebepleri 400'e ÇEVRİLMEZ (kilit değil, rapor)."""
    for reason in RUNTIME_REASONS:
        assert reason not in api.ENGINE_UNAVAILABLE_REASONS


def test_reason_vocabulary_matches_the_service_modules():
    """Beyan edilen motor sebepleri servislerin GERÇEK sözlüğünde var.

    Kopukluk denetimi: bir servis `library_missing` yerine yeni bir sebep
    uydurursa (ör. `lib_yok`) sessizce 200'e düşerdi; bu test sözlüğü
    servis kaynaklarına bağlar.
    """
    services = [
        Path("agent_core/services/maigret_scanner.py"),
        Path("agent_core/services/holehe_scanner.py"),
        Path("agent_core/services/crawl_enricher.py"),
        Path("agent_core/services/socid_enricher.py"),
    ]
    seen: set[str] = set()
    for path in services:
        text = path.read_text(encoding="utf-8")
        seen.update(re.findall(r'reason="([a-z_]+)"', text))
        seen.update(re.findall(r'reason=f"([a-z_]+)', text))
    engine_seen = seen & api.ENGINE_UNAVAILABLE_REASONS
    assert engine_seen, f"hiç motor-sebebi bulunamadı: {sorted(seen)}"
    # Beyan edilen her motor sebebi en az bir serviste geçmeli (uydurma sebep yok).
    assert api.ENGINE_UNAVAILABLE_REASONS <= seen | {"library_missing"}, (
        f"beyan edilen sebep servislerde yok: "
        f"{sorted(api.ENGINE_UNAVAILABLE_REASONS - seen)}"
    )
    # Çalışma-zamanı sebepleri de gerçekten var (sözlük canlı).
    assert set(RUNTIME_REASONS) & seen, f"runtime sebepleri bulunamadı: {sorted(seen)}"
