"""KASA MANDALI (Tüzük Md.4) — "kasa kilitli" bir İDDİA değil, çalışan bir kilittir.

Denetimin bulduğu delik (JULES_DENETIM_2026-10-06 · E-GÖZ2-3 / E-GÖZ2-5 /
E-GÖZ3-6): `/api/vault/status` ekrana "VAULT KİLİTLİ - dış dünya erişimi yok"
yazarken, tarayıcı uçları (`/api/browser/*`), deneysel OSINT uçları
(maigret/holehe/crawl4ai/socid), scraper yetkilendirmesi ve `SearchEngine`'in
"ücretsiz" DuckDuckGo/Tavily/SerpAPI/Exa yolu kasanın kilidine HİÇ
BAKMIYORDU. Yani kilit dekorasyondu; arkadan elini kolunu sallayarak dışarı
çıkılıyordu.

Bu dosya üç katmanı birden kilitler:

1. **YAPI DENETİMİ** — route tablosuna karşı makine kontrolü: dışarıya açılan
   her uç ya kapıyı çağırır ya da adı yazılı, gerekçeli muafiyet listesindedir.
   Yeni bir dış-çıkış ucu ekleyip kapıyı unutmak MÜMKÜN DEĞİL (kırmızı yanar).
2. **API KAPISI** — kasa kilitliyse her dış-çıkış ucu HTTP 423 Locked döner;
   motor/scraper/tarayıcı HİÇ çağrılmaz.
3. **SERVİS KATMANI** — kapı atlanmış olsa bile `SearchEngine` dışarı HTTP
   istemcisi OLUŞTURMAZ, `BrowserSession` `VaultLockedError` fırlatır.

Kilidin "açık" hâli de ölçülür: aynı uçlar kasa açıldığında 423 VERMEZ
(yoksa her şeyi reddeden bir kapı yazıp testleri yeşile boyamak işten bile
değildi).
"""

from __future__ import annotations

import inspect
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from agent_core.services import search_engine as search_mod
from agent_core.services.browser_session import BrowserSession, VaultLockedError
from agent_core.services.search_engine import SearchEngine
from backend import api
from backend.api import app

# ─────────────────────────────────────────────────────────────────────────────
# 1) YAPI DENETİMİ — route tablosu ↔ kapı ↔ muafiyet listesi tutarlılığı
# ─────────────────────────────────────────────────────────────────────────────

#: Dış dünyaya açılma POTANSİYELİ olan uç önekleri. Bu öneklerden birine uyan
#: her route ya kapıdan geçer ya da gerekçeli muafiyet listesinde adı geçer.
EGRESS_PREFIXES = (
    "/api/browser/",
    "/api/experimental/",
    "/api/scraper/",
    "/api/initiate",
)


def _egress_routes():
    rows = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        endpoint = getattr(route, "endpoint", None)
        if not path.startswith(EGRESS_PREFIXES) or endpoint is None:
            continue
        rows.append((path, endpoint))
    return sorted(rows, key=lambda r: r[0])


def test_route_inventory_is_not_empty():
    """Denetim boş bir tabloya karşı koşup "yeşil" olmasın."""
    assert len(_egress_routes()) >= 19, [p for p, _ in _egress_routes()]


def test_every_egress_route_is_guarded_or_explicitly_exempt():
    """DIŞARI AÇILAN HER UÇ: ya kapıyı çağırır ya adı yazılı muafiyettedir.

    Üçüncü bir ihtimal YOKTUR. "Kimse fark etmez" diye eklenen yeni bir
    tarayıcı/OSINT ucu bu testi kırmızıya boyar.
    """
    unguarded = []
    for path, endpoint in _egress_routes():
        declared = path in api.VAULT_EGRESS_ROUTES
        exempt = path in api.VAULT_EGRESS_EXEMPT_ROUTES
        assert not (declared and exempt), f"{path} hem kapıda hem muaf listede"
        source = inspect.getsource(endpoint)
        calls_gate = "_require_vault_open(" in source
        if declared:
            assert calls_gate, (
                f"{path} VAULT_EGRESS_ROUTES içinde ama uç gövdesi "
                "_require_vault_open() ÇAĞIRMIYOR — envanter yalan söylüyor"
            )
        elif exempt:
            assert not calls_gate, f"{path} muaf ilan edilmiş ama kapıyı da çağırıyor"
        else:
            unguarded.append(path)
    assert not unguarded, (
        "KASA MANDALI DELİĞİ: şu dış-çıkış uçları ne kapıdan geçiyor ne de "
        f"gerekçeli muafiyet listesinde: {unguarded}. Ya VAULT_EGRESS_ROUTES'a "
        "ekleyip uca `_require_vault_open(...)` koyun, ya da gerekçesiyle "
        "birlikte VAULT_EGRESS_EXEMPT_ROUTES'a yazın."
    )


def test_exempt_routes_are_declared_in_the_route_table():
    """Muafiyet listesi hayalet uç biriktirmesin (ölü envanter = sahte güvence)."""
    live = {path for path, _ in _egress_routes()}
    stale = sorted(set(api.VAULT_EGRESS_EXEMPT_ROUTES) - live)
    assert not stale, f"muafiyet listesinde artık var olmayan uçlar: {stale}"
    stale_guarded = sorted(set(api.VAULT_EGRESS_ROUTES) - live)
    assert not stale_guarded, f"kapı listesinde artık var olmayan uçlar: {stale_guarded}"


def test_gate_helper_is_single_source():
    """Kapının TEK sahibi `_check_vault_interlock`'tur; ikinci bir kasa
    okuması (env'den/dosyadan) uydurulamaz."""
    source = inspect.getsource(api._require_vault_open)
    assert "_check_vault_interlock(" in source
    assert "os.getenv" not in source
    assert "_load_vault" not in source


# ─────────────────────────────────────────────────────────────────────────────
# 2) API KAPISI — kasa kilitliyse 423 Locked, motor HİÇ çağrılmaz
# ─────────────────────────────────────────────────────────────────────────────


def _locked(monkeypatch, tmp_path):
    """Kasa KİLİTLİ ön koşulu: dosya kasası yok, env'de anahtar yok."""
    for env in ("OPENROUTER_API_KEY", "TAVILY_API_KEY", "SERPAPI_API_KEY",
                "SERPAPI_KEY", "EXA_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pineal_vault.json").write_text(
        json.dumps({"providers": {}}), encoding="utf-8"
    )


def _cid() -> str:
    return f"vaultlock_{uuid.uuid4().hex[:8]}"


LOCKED_CALLS = [
    ("post", "/api/browser/open", lambda c: {"client_id": c, "url": "https://www.instagram.com/"}),
    ("get", "/api/browser/shot", lambda c: {"client_id": c}),
    ("get", "/api/browser/state", lambda c: {"client_id": c}),
    ("post", "/api/browser/click", lambda c: {"client_id": c, "x": 1, "y": 1}),
    ("post", "/api/browser/type", lambda c: {"client_id": c, "text": "merhaba"}),
    ("post", "/api/browser/press", lambda c: {"client_id": c, "key": "Enter"}),
    ("post", "/api/browser/back", lambda c: {"client_id": c}),
    ("post", "/api/browser/save", lambda c: {"client_id": c}),
    ("post", "/api/experimental/maigret/scan", lambda c: {"username": "soxoj", "client_id": c}),
    ("post", "/api/experimental/holehe/scan", lambda c: {"email": "a@b.com", "client_id": c}),
    ("post", "/api/experimental/crawl/fetch", lambda c: {"url": "https://example.com/a", "client_id": c}),
    ("post", "/api/experimental/socid/extract", lambda c: {"url": "https://x.com/alper", "client_id": c}),
    ("post", "/api/scraper/authorize-alternative",
     lambda c: {"client_id": c, "alternative": "public_web_search", "approved": True}),
]


@pytest.mark.parametrize("method,path,body", LOCKED_CALLS, ids=[p for _, p, _ in LOCKED_CALLS])
def test_egress_endpoints_hard_reject_when_vault_locked(monkeypatch, tmp_path, method, path, body):
    """Kasa kilitli → 423 Locked + makine-okunur VAULT_LOCKED kodu."""
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        if method == "get":
            r = client.get(path, params=body(cid))
        else:
            r = client.post(path, json=body(cid))
    assert r.status_code == 423, f"{path} kasa kilitliken {r.status_code} döndü: {r.text[:200]}"
    payload = r.json()
    assert payload["error"]["code"] == "VAULT_LOCKED"
    assert payload["vault_locked"] is True


@pytest.mark.parametrize("method,path,body", LOCKED_CALLS, ids=[p for _, p, _ in LOCKED_CALLS])
def test_egress_endpoints_do_not_reach_the_engine_when_locked(monkeypatch, tmp_path, method, path, body):
    """423 sadece bir HTTP kodu değil: altındaki motor HİÇ ÇAĞRILMAMALI.

    Kapı "reddettim" derken arkada tarama başlatıyorsa bu yine tiyatrodur.
    """
    _locked(monkeypatch, tmp_path)

    def _boom(*a, **kw):
        raise AssertionError(f"{path}: kasa kilitliyken motor/tarayıcı çağrıldı")

    async def _aboom(*a, **kw):
        raise AssertionError(f"{path}: kasa kilitliyken motor/tarayıcı çağrıldı")

    # Dış dünyaya dokunan her çağrı noktası patlayıcıyla değiştirilir.
    monkeypatch.setattr(BrowserSession, "open", _aboom)
    monkeypatch.setattr(BrowserSession, "shot", _aboom)
    monkeypatch.setattr(BrowserSession, "state", _aboom)
    monkeypatch.setattr(BrowserSession, "click", _aboom)
    monkeypatch.setattr(BrowserSession, "type_text", _aboom)
    monkeypatch.setattr(BrowserSession, "press", _aboom)
    monkeypatch.setattr(BrowserSession, "back", _aboom)
    monkeypatch.setattr(BrowserSession, "session_cookie", _aboom)
    monkeypatch.setattr(search_mod.httpx, "AsyncClient", _boom)
    monkeypatch.setattr("agent_core.services.crawl_enricher.fetch_readable", _aboom)
    monkeypatch.setattr("agent_core.services.socid_enricher.extract_profile", _aboom)
    monkeypatch.setattr("agent_core.services.maigret_scanner.scan_username", _aboom)
    monkeypatch.setattr("agent_core.services.holehe_scanner.scan_email", _aboom)

    cid = _cid()
    with TestClient(app) as client:
        if method == "get":
            r = client.get(path, params=body(cid))
        else:
            r = client.post(path, json=body(cid))
    assert r.status_code == 423, f"{path}: {r.status_code} {r.text[:200]}"


def test_browser_close_is_exempt_so_no_zombie_chromium(monkeypatch, tmp_path):
    """`/api/browser/close` BİLEREK muaftır: kasa kilitliyken bile açık
    Chromium kanalı KAPATILABİLMELİ. Reddedilirse zombi süreç sızar — yani
    muafiyet kilidi zayıflatmaz, güçlendirir."""
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        r = client.post("/api/browser/close", json={"client_id": cid})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] in ("closed", "was_not_open")


def test_vault_status_endpoint_reports_locked(monkeypatch, tmp_path):
    """Ekran ile kapı AYNI şeyi söyler: status "kilitli" diyorsa kapı da kapalıdır."""
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        status = client.get("/api/vault/status", params={"client_id": cid}).json()
        assert status["locked"] is True
        assert status["can_scrape"] is False
        egress = client.post("/api/browser/open", json={"client_id": cid, "url": ""})
    assert egress.status_code == 423


def test_egress_opens_when_real_key_material_is_sealed(monkeypatch, tmp_path):
    """Kontrol deneyi: kasa GERÇEK anahtarla açılınca aynı uç 423 VERMEZ.

    (Her şeyi reddeden bir kapı yazmak kolaydı; bu test onu engeller.)
    Tarayıcı bu makinede kurulu olmayabilir → 423 DIŞINDA her cevap kabul.
    """
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    (tmp_path / ".pineal_vault.json").write_text(
        json.dumps({"api_key": "sk-or-v1-gercek-anahtar"}), encoding="utf-8"
    )
    with TestClient(app) as client:
        r = client.post("/api/browser/open", json={"client_id": cid, "url": ""})
    assert r.status_code != 423, r.text[:300]


def test_initiate_is_gated_by_the_shared_helper(monkeypatch, tmp_path):
    """/api/initiate eskiden elle yazılmış ikinci bir kasa `if` bloğu taşıyordu;
    artık TEK yardımcıyı kullanıyor (ikinci kaynak yok)."""
    source = inspect.getsource(api.api_initiate)
    assert "_require_vault_open(" in source
    assert "VAULT KİLİTLİ: Operatör anahtarı çevirmeden" not in source

    _locked(monkeypatch, tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        r = client.post(
            "/api/initiate",
            json={"client_id": cid, "url": "https://www.instagram.com/hedef/"},
        )
    assert r.status_code == 423
    assert r.json()["error"]["code"] == "VAULT_LOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# 3) SERVİS KATMANI — kapı atlanmış olsa bile dışarı çıkılamaz
# ─────────────────────────────────────────────────────────────────────────────


class _BoomClient:
    """Oluşturulduğu anda patlayan httpx istemcisi: dışarı çıkışın kanıtı."""

    def __init__(self, *a, **kw):
        raise AssertionError("kasa kilitliyken dış HTTP istemcisi oluşturuldu")


@pytest.mark.asyncio
async def test_search_engine_creates_no_http_client_when_locked(monkeypatch):
    """[DELİĞİN KENDİSİ] Eskiden kasa kilitli olsa bile Tavily/SerpAPI/Exa ve
    "ücretsiz" DuckDuckGo yolu doğrudan httpx ile dışarı çıkıyordu (kodda
    açıkça yazıyordu: "Ücretsiz DuckDuckGo yolu bugünkü davranışını korur").
    Artık istemci HİÇ OLUŞTURULMUYOR."""
    monkeypatch.setattr(search_mod.httpx, "AsyncClient", _BoomClient)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-gercek")
    engine = SearchEngine(tavily_key="tvly-gercek")
    engine.set_policy({"vault_locked": True})

    outcome = await engine.search("hedef kişi", num_results=3)
    assert outcome.results == []
    assert outcome.available is False
    assert outcome.status == "VAULT_LOCKED"
    assert outcome.error == "vault_locked"


@pytest.mark.asyncio
async def test_search_engine_defaults_to_locked_when_vault_state_unknown(monkeypatch):
    """Belirsizlik DAR tarafa yorumlanır: kasa durumu hiç bildirilmediyse
    motor dışarı ÇIKMAZ (`capabilities/state.py` doktrini)."""
    monkeypatch.setattr(search_mod.httpx, "AsyncClient", _BoomClient)
    engine = SearchEngine(tavily_key="tvly-gercek")
    assert engine.vault_locked() is True

    outcome = await engine.search("hedef", num_results=2)
    assert outcome.status == "VAULT_LOCKED"
    assert outcome.available is False


@pytest.mark.asyncio
async def test_search_engine_uses_live_vault_state_not_stale_snapshot(monkeypatch):
    """Canlı mandal, anlık görüntüden ÖNCE gelir: görev başladıktan sonra
    kasa kilitlenirse arama anında durur (bayat "açık" anlık görüntüsü kullanılmaz)."""
    monkeypatch.setattr(search_mod.httpx, "AsyncClient", _BoomClient)
    engine = SearchEngine(tavily_key="tvly-gercek")
    engine.set_policy({"vault_locked": False})  # bayat anlık görüntü: AÇIK

    unlocked = {"now": False}                  # canlı gerçek: KİLİTLİ
    engine.set_vault_state(lambda: unlocked["now"])

    assert engine.vault_locked() is True
    outcome = await engine.search("hedef", num_results=2)
    assert outcome.status == "VAULT_LOCKED"


@pytest.mark.asyncio
async def test_search_engine_vault_state_failure_falls_closed(monkeypatch):
    """Mandal okunamıyorsa arıza YUTULMAZ: dar taraf (kilitli) + ERROR logu."""
    monkeypatch.setattr(search_mod.httpx, "AsyncClient", _BoomClient)

    def _boom():
        raise RuntimeError("interlock çöktü")

    engine = SearchEngine(tavily_key="tvly-gercek")
    engine.set_vault_state(_boom)
    assert engine.vault_locked() is True
    outcome = await engine.search("hedef", num_results=2)
    assert outcome.status == "VAULT_LOCKED"


@pytest.mark.asyncio
async def test_browser_session_refuses_every_outward_action_without_guard():
    """Guard bağlanmamış bir tarayıcı oturumu DAR TARAFI seçer: hiçbir dış
    hareket yapamaz. Yalnız `close()` (kanalı kapatan eylem) serbesttir."""
    sess = BrowserSession()
    for action in ("open", "shot", "click", "type_text", "press", "back",
                   "state", "session_cookie"):
        with pytest.raises(VaultLockedError):
            kwargs = {"url": "https://www.instagram.com/"} if action == "open" else {}
            if action == "click":
                kwargs = {"x": 1, "y": 1}
            if action == "type_text":
                kwargs = {"text": "merhaba"}
            if action == "press":
                kwargs = {"key": "Enter"}
            await getattr(sess, action)(**kwargs)

    closed = await sess.close()
    assert closed["status"] == "was_not_open"


@pytest.mark.asyncio
async def test_browser_session_refuses_when_guard_reports_locked():
    sess = BrowserSession(vault_guard=lambda: False)
    with pytest.raises(VaultLockedError):
        await sess.open("https://www.instagram.com/")
    # Kilitliyken bile kapatma çalışır.
    assert (await sess.close())["status"] == "was_not_open"


@pytest.mark.asyncio
async def test_browser_session_guard_failure_falls_closed():
    """Guard patlarsa "açık" sayılmaz: fail-closed."""
    def _boom():
        raise RuntimeError("mandal çöktü")

    sess = BrowserSession(vault_guard=_boom)
    with pytest.raises(VaultLockedError):
        await sess.open("https://www.instagram.com/")


def test_room_browser_binds_a_live_vault_guard(monkeypatch, tmp_path):
    """Oda tarayıcısı mandalı CANLI okur: kasa sonradan kilitlenirse açık
    tarayıcı da dışarı çıkamaz (guard, oda kurulurken bağlanır)."""
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    room = api.get_room(cid)
    assert room.get("client_id") == cid

    sess = api._room_browser(room)
    assert sess._vault_guard is not None
    assert sess._vault_guard() is False

    # Kasa açılırsa AYNI guard True döner (anlık görüntü değil, canlı mandal).
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    assert sess._vault_guard() is True


def test_room_search_engine_binds_a_live_vault_guard(monkeypatch, tmp_path):
    """Odanın arama motoru da canlı mandala bağlıdır (get_room'da bağlanır)."""
    _locked(monkeypatch, tmp_path)
    cid = _cid()
    room = api.get_room(cid)
    engine = room["executor"].search_engine
    assert engine.vault_locked() is True

    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    assert engine.vault_locked() is False
