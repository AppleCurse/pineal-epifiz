"""ÇOCUK KIRMIZI ÇİZGİSİ — API SINIRI (Faz E / E2).

Ürün kuralı: 18 yaş altı = çocuktur; normalde HİÇ ARAŞTIRILAMAZ. Tek istisna
kayıp/yaralanma vakası ve dört şartın TAMAMI (aile bilgisi + net sebep +
doğrulama + konsorsiyum onayı ≥2).

FAZ 0'da kilit yalnız capability koşucusunda yaşıyordu (`runner.py`) ve oraya
da ancak `PolicyState.minor_case` DOLDURULURSA ulaşıyordu. API sınırı onu hiç
doldurmuyordu: operatör bir hedefi çocuk olarak beyan etse bile istek kapıda
DURDURULMUYORDU. Ölçüm (2026-10-07): `grep -c 'MinorGate\\|minor_gate'
backend/api.py` → 0.

Bu dosya, kilidin API sınırında GERÇEKTEN çalıştığını ölçer ve üç kaçış
yolunu kapatır:

1. **Beyan ≠ izin.** Yukarıdan/dışarıdan gelen beyan "geç" demek değildir;
   dört şart eksikse istek gövdesi HİÇ ÇALIŞMAZ (451).
2. **Beyan sessizce düşemez.** Oda tahliyesi (30 dk boşta), yeniden başlatma
   veya bozuk bir nesne kilidi GEVŞETEMEZ. Beyan oda yaşam döngüsünden
   bağımsızdır ve okunamayan beyan "yetişkin" sayılmaz.
3. **Kilit dekorasyon değildir.** Altındaki motor/tarayıcı çağrılmaz; ve
   gerçekten meşru vakada (dört şart tamam) kapı AÇILIR — yoksa her şeyi
   reddeden bir kapı yazıp testleri yeşile boyamak işten bile değildi.
"""

from __future__ import annotations

import inspect
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from agent_core.safety import MinorCaseContext, MinorGate, coerce_minor_case
from backend import api
from backend.api import app

# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

#: Dış dünyaya açılma POTANSİYELİ olan uçlar. Kasa testindeki envanterle aynı
#: önekler; her uç ya çocuk kapısından geçer ya da gerekçeli muafiyette olur.
EGRESS_PREFIXES = (
    "/api/browser/",
    "/api/experimental/",
    "/api/scraper/",
    "/api/initiate",
)

#: Çocuk kilidinden MUAF tutulan dış-çıkış uçları — gerekçesiyle birlikte.
#: `/api/browser/close` muafiyeti KASA kilidinden miras: kilidin kendisi bir
#: zombi Chromium üretmemelidir (temizleme, dışa veri AKTARMAZ).
MINOR_EXEMPT_ROUTES = {
    "/api/browser/close": (
        "Kapatma temizleme işlemidir, dışa veri aktarmaz; engellemek zombi "
        "tarayıcı üretir (kasa muafiyetiyle aynı gerekçe)."
    ),
    "/api/experimental/stealth": (
        "Salt-okunur envanter raporu: hedef materyali işlemez, kişi aramaz "
        "(kendi docstring'i tarayıcı başlatmadığını beyan eder)."
    ),
}


def _cid() -> str:
    return f"minorgate_{uuid.uuid4().hex[:8]}"


def _cleanup(client_id: str) -> None:
    """Test odası VE beyanı bırakmaz (durum testler arası sızmaz)."""
    api.app.state.minor_cases.pop(client_id, None)
    api.app.state.rooms.pop(client_id, None)
    api._rooms_last_seen.pop(client_id, None)


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    """Her test: ayrı oda kimliği + defter test dizininde + kasa kilitli DEĞİL.

    Kasa kapısı burada konu değil: anahtar malzemesi olmadan 423 dönerdi ve
    çocuk kapısının sırasını ölçmek zorlaşırdı. Kasa env'i verilir, böylece
    ölçülen şey YALNIZ çocuk kilididir.
    """
    monkeypatch.setenv("PINEAL_MINOR_LEDGER_PATH", str(tmp_path / "minor-cases.jsonl"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-key-for-minor-gate")
    monkeypatch.chdir(tmp_path)
    yield


#: Kapıdan geçmesi beklenen dış-çıkış çağrıları (beyanlı oda → 451).
EGRESS_CALLS = [
    ("post", "/api/initiate", lambda c: {"client_id": c, "url": "https://example.com"}),
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


def _call(client: TestClient, method: str, path: str, body: dict):
    if method == "get":
        return client.get(path, params=body)
    return client.post(path, json=body)


def _declare_incomplete(client_id: str) -> None:
    """Çocuk beyanı VERİLMİŞ ama dört şart EKSİK (vaka tipi bile yok)."""
    api.app.state.minor_cases[client_id] = MinorCaseContext(subject_is_minor=True)


def _declare_approved(client_id: str) -> MinorCaseContext:
    """Meşru istisna: dört şartın tamamı sağlanmış kayıp vakası."""
    case = MinorCaseContext(
        subject_is_minor=True,
        case_type="missing_or_harm",
        family_notified=True,
        reason="Çocuk 3 gündür kayıp; aile karakola başvurdu, dosya no 2026/4471.",
        verified=True,
        council_approvals=("operator:alper", "council:legal"),
        case_id="case-2026-4471",
    )
    api.app.state.minor_cases[client_id] = case
    return case


# ─────────────────────────────────────────────────────────────────────────────
# 1) YAPI DENETİMİ — yeni bir dış-çıkış ucu kapıyı unutamaz
# ─────────────────────────────────────────────────────────────────────────────


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


def test_every_egress_route_calls_the_minor_gate_or_is_exempt():
    """Her dış-çıkış ucu ya çocuk kapısını çağırır ya gerekçeli muafiyettedir."""
    missing = []
    for path, endpoint in _egress_routes():
        if path in MINOR_EXEMPT_ROUTES:
            continue
        try:
            source = inspect.getsource(endpoint)
        except OSError:  # pragma: no cover - kaynak yoksa denetim yanar
            missing.append(path)
            continue
        if "_require_minor_clearance(" not in source:
            missing.append(path)
    assert not missing, (
        "Çocuk kapısı olmayan dış-çıkış uçları: "
        f"{missing} — ya `_require_minor_clearance(...)` ekleyin ya da "
        "MINOR_EXEMPT_ROUTES'a gerekçe yazın."
    )


def test_minor_gate_runs_before_the_vault_gate_everywhere():
    """Sıra yapısal olarak da kilitli: çocuk kapısı kasa kapısından ÖNCE.

    Tersi olsaydı denetim izi "VAULT_LOCKED" derdi; çocuk ihlali maskelenirdi.
    """
    wrong = []
    for path, endpoint in _egress_routes():
        if path in MINOR_EXEMPT_ROUTES:
            continue
        source = inspect.getsource(endpoint)
        minor_at = source.find("_require_minor_clearance(")
        vault_at = source.find("_require_vault_open(")
        if minor_at < 0:
            continue  # envanter testi bunu ayrıca yakalar
        if vault_at >= 0 and minor_at > vault_at:
            wrong.append(path)
    assert not wrong, f"çocuk kapısı kasa kapısının ARKASINDA: {wrong}"


def test_exempt_routes_are_declared_in_the_route_table():
    """Muafiyet listesi gerçek route'lara karşılık gelir (hayalet muafiyet yok)."""
    paths = {p for p, _ in _egress_routes()}
    for path, reason in MINOR_EXEMPT_ROUTES.items():
        assert path in paths, f"{path} route tablosunda yok"
        assert len(reason) > 30, f"{path} için gerekçe cılız"


def test_gate_helper_is_single_source():
    """Kapının TEK sahibi `_require_minor_clearance`'tır; kapı noktaları onu
    çağırır (ikinci, elle yazılmış bir çocuk kontrolü olamaz)."""
    source = inspect.getsource(api)
    assert "_require_minor_clearance(" in source
    assert "MINOR_BLOCKED" in source
    # Kilidin ikinci bir kopyası: capability koşucusundaki kilit zaten var,
    # burada YENİDEN yazılmamalı.
    assert "MinorGate().evaluate" in source


def test_minor_state_endpoint_is_registered():
    """Operatör durumu görebilmelidir (kayıt/temizleme/durum üçlüsü)."""
    paths = {getattr(r, "path", "") for r in app.routes}
    assert {"/api/minor/case", "/api/minor/clear", "/api/minor/state"} <= paths


# ─────────────────────────────────────────────────────────────────────────────
# 2) BEYAN ≠ İZİN — dört şart eksikse istek gövdesi HİÇ ÇALIŞMAZ
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method,path,body", EGRESS_CALLS, ids=[p for _, p, _ in EGRESS_CALLS])
def test_egress_endpoints_reject_declared_minor_without_full_case(method, path, body):
    """Çocuk beyanı var, dört şart eksik → 451 + makine-okunur MINOR_BLOCKED."""
    cid = _cid()
    _declare_incomplete(cid)
    try:
        with TestClient(app) as client:
            r = _call(client, method, path, body(cid))
    finally:
        _cleanup(cid)
    assert r.status_code == 451, f"{path} beyanlı odada {r.status_code} döndü: {r.text[:200]}"
    payload = r.json()
    assert payload["error"]["code"] == "MINOR_BLOCKED"
    assert payload["minor_case"]["subject_is_minor"] is True
    assert payload["error"]["reason_code"]


@pytest.mark.parametrize("method,path,body", EGRESS_CALLS, ids=[p for _, p, _ in EGRESS_CALLS])
def test_egress_endpoints_do_not_reach_the_engine_when_minor(monkeypatch, method, path, body):
    """451 sadece bir kod değil: altındaki motor/tarayıcı HİÇ ÇAĞRILMAMALI."""
    cid = _cid()
    _declare_incomplete(cid)

    def _boom(*_a, **_k):
        raise AssertionError(f"çocuk kilidi delindi: {path} alt motora ulaştı")

    async def _aboom(*_a, **_k):
        raise AssertionError(f"çocuk kilidi delindi: {path} alt motora ulaştı")

    import agent_core.services.crawl_enricher as crawl_mod
    import agent_core.services.holehe_scanner as holehe_mod
    import agent_core.services.maigret_scanner as maigret_mod
    import agent_core.services.socid_enricher as socid_mod
    from agent_core.services.browser_session import BrowserSession

    for name in ("open", "shot", "state", "click", "type_text", "press", "back", "session_cookie"):
        monkeypatch.setattr(BrowserSession, name, _aboom, raising=False)
    monkeypatch.setattr(crawl_mod, "fetch_readable", _aboom, raising=False)
    monkeypatch.setattr(socid_mod, "extract_profile", _aboom, raising=False)
    monkeypatch.setattr(maigret_mod, "scan_username", _aboom, raising=False)
    monkeypatch.setattr(holehe_mod, "scan_email", _aboom, raising=False)
    monkeypatch.setattr(api, "start_mission", _boom, raising=False)

    try:
        with TestClient(app) as client:
            r = _call(client, method, path, body(cid))
    finally:
        _cleanup(cid)
    assert r.status_code == 451, f"{path} → {r.status_code}: {r.text[:200]}"


# ─────────────────────────────────────────────────────────────────────────────
# 3) BEYAN SESSİZCE DÜŞEMEZ — tahliye, bozuk nesne, metinle kandırma
# ─────────────────────────────────────────────────────────────────────────────


def test_declaration_survives_room_eviction():
    """Boşta kalan oda tahliye edilse bile kilit AÇILMAZ (regresyon kilidi).

    Delik: beyan oda sözlüğünde tutulsaydı `_evict_rooms` 30 dk sonra odayı
    kapatır, beyan düşer ve kilit KENDİLİĞİNDEN açılırdı.
    """
    import time

    cid = _cid()
    api.get_room(cid)  # oda kurulur
    _declare_incomplete(cid)
    api._rooms_last_seen[cid] = time.monotonic() - api._ROOM_TTL_SECONDS - 60
    api._evict_rooms._last_sweep = 0.0  # 5 sn'lik tarama gazını sıfırla

    api._evict_rooms(time.monotonic())
    assert cid not in api.app.state.rooms, "oda tahliye edilmeliydi (ön koşul)"

    try:
        blocked = api._require_minor_clearance(cid)
        assert blocked is not None, "odasız kalan beyan kilidi AÇTI — delik açık"
        assert blocked.status_code == 451
    finally:
        _cleanup(cid)


def test_helper_does_not_create_rooms():
    """Salt okuma yolu yan etkisiz olmalı: durum sorgusu oda açmaz."""
    cid = _cid()
    try:
        assert api._minor_case_for(cid) is None
        assert api._require_minor_clearance(cid) is None
        assert cid not in api.app.state.rooms
    finally:
        _cleanup(cid)


def test_unreadable_declaration_still_locks():
    """Beyan nesnesi bozuksa 'yetişkin' sayılmaz — fail-closed."""
    cid = _cid()
    api.app.state.minor_cases[cid] = ["bozuk", "beyan"]
    try:
        blocked = api._require_minor_clearance(cid)
        assert blocked is not None and blocked.status_code == 451
        with TestClient(app) as client:
            r = client.post("/api/experimental/maigret/scan", json={"username": "x", "client_id": cid})
        assert r.status_code == 451
    finally:
        _cleanup(cid)


def test_textual_minor_flag_is_not_treated_as_adult():
    """`subject_is_minor: "true"` gönderen istemci 'çocuk değil' hükmü ALMAZ.

    Naive bool tuzağının aynası: burada gevşek okuma fail-OPEN olurdu (beyanı
    yorumlayamamak onu yok saymak hâline gelirdi).
    """
    case = coerce_minor_case({"subject_is_minor": "true"})
    assert case is not None and case.subject_is_minor is True
    assert MinorGate().evaluate(case).allowed is False

    for declared in ("true", "evet", "1", "TRUE", "", 1, ["x"], {"nested": 1}):
        case = coerce_minor_case({"subject_is_minor": declared})
        assert case.subject_is_minor is True, f"{declared!r} beyanı yutuldu"
        assert MinorGate().evaluate(case).allowed is False


def test_conditions_stay_strict_even_with_textual_values():
    """Dört şart metinle 'doğru gibi görünerek' GEÇEMEZ (strict bool)."""
    case = coerce_minor_case(
        {
            "subject_is_minor": True,
            "case_type": "missing_or_harm",
            "family_notified": "true",   # metin: sayılmaz
            "reason": "Çocuk kayıp, aile başvurdu, dosya no 2026/4471.",
            "verified": "evet",          # metin: sayılmaz
            "council_approvals": ["a", "b"],
        }
    )
    decision = MinorGate().evaluate(case)
    assert decision.allowed is False
    assert decision.reason_code in {"family_not_notified", "not_verified"}


def test_explicit_false_declares_adult_without_blocking():
    """Açıkça 'yetişkin' beyanı engellenmez — karar mercii operatördür."""
    assert coerce_minor_case({"subject_is_minor": False}) is not None
    assert coerce_minor_case({"subject_is_minor": False}).subject_is_minor is False
    assert coerce_minor_case(None) is None
    # Yetişkin beyanında kapı 451 VERMEZ.
    cid = _cid()
    api.app.state.minor_cases[cid] = coerce_minor_case({"subject_is_minor": False})
    try:
        assert api._require_minor_clearance(cid) is None
    finally:
        _cleanup(cid)


# ─────────────────────────────────────────────────────────────────────────────
# 4) KİLİT AÇIK HÂLDE DE ÖLÇÜLÜR — meşru vaka akışı durdurmaz
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method,path,body", EGRESS_CALLS, ids=[p for _, p, _ in EGRESS_CALLS])
def test_approved_missing_case_does_not_block(monkeypatch, method, path, body):
    """Dört şart tamamsa çocuk kapısı 451 DÖNMEZ (kapı, her şeyi reddetmiyor).

    Alt motora inilmesi beklenmez (kasa/env kapıları ardından gelir); ölçülen
    şey çocuk kapısının onaylı vakayı GEÇİRMESİDİR.
    """
    cid = _cid()
    _declare_approved(cid)
    try:
        with TestClient(app) as client:
            r = _call(client, method, path, body(cid))
        assert r.status_code != 451, f"{path} onaylı vakada 451 döndü: {r.text[:200]}"
        if r.status_code == 200:
            payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            assert payload.get("error", {}).get("code") != "MINOR_BLOCKED"
    finally:
        _cleanup(cid)


def test_gate_order_minor_precedes_vault():
    """Çocuk kilidi kasa kilidinden ÖNCE: ikisi de kilitliyken karar 451'dir.

    Tersi olsaydı denetim izinde "VAULT_LOCKED" görünür ve çocuk ihlali
    maskelenirdi (koşucudaki sıra da çocuk → politika).
    """
    cid = _cid()
    _declare_incomplete(cid)
    # Kasa da kilitli: anahtar malzemesi yok.
    import os

    for env in ("OPENROUTER_API_KEY", "TAVILY_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(env, None)
    try:
        with TestClient(app) as client:
            r = client.get("/api/browser/state", params={"client_id": cid})
        assert r.status_code == 451, f"çocuk kapısı kasa kapısının arkasında kaldı: {r.status_code}"
        assert r.json()["error"]["code"] == "MINOR_BLOCKED"
    finally:
        _cleanup(cid)


def test_browser_close_stays_exempt_so_no_zombie_chromium():
    """Kapatma yolu çocuk kilidinden muaf: temizleme engellenirse zombi kalır."""
    cid = _cid()
    _declare_incomplete(cid)
    try:
        with TestClient(app) as client:
            r = client.post("/api/browser/close", json={"client_id": cid})
        assert r.status_code != 451, "kapatma engellendi: zombi tarayıcı riski"
    finally:
        _cleanup(cid)


# ─────────────────────────────────────────────────────────────────────────────
# 5) BEYAN, KAYIT VE DENETİM — operatör yolu
# ─────────────────────────────────────────────────────────────────────────────


def test_register_endpoint_refuses_to_claim_approval_when_case_incomplete():
    """/api/minor/case beyanı kaydeder ama 'izin' VERMEZ: eksikse allowed:false."""
    cid = _cid()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/minor/case",
                json={"client_id": cid, "subject_is_minor": True, "case_type": ""},
            )
        assert r.status_code == 200, r.text[:200]
        payload = r.json()
        assert payload["declared"] is True
        assert payload["allowed"] is False
        assert payload["reason_code"]

        with TestClient(app) as client:
            r2 = client.post("/api/experimental/maigret/scan", json={"username": "x", "client_id": cid})
        assert r2.status_code == 451
    finally:
        _cleanup(cid)


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/experimental/shadow/analyze", lambda c: {"profile": {"name": "hedef"}}),
        ("/api/experimental/shadow/generate", lambda c: {"task": {"objective": "x"}}),
        ("/api/experimental/chat/respond",
         lambda c: {"task_id": "t1", "target_profile": {}, "user_profile": {}, "target_message": "selam"}),
    ],
    ids=["shadow/analyze", "shadow/generate", "chat/respond"],
)
def test_room_less_subject_routes_block_when_any_declaration_exists(path, body):
    """Oda adı taşımayan hedef-uçları "odayı söyleyemedim" kaçışı olamaz."""
    cid = _cid()
    _declare_incomplete(cid)
    try:
        with TestClient(app) as client:
            r = client.post(path, json=body(cid))
        assert r.status_code == 451, f"{path} beyan varken {r.status_code} döndü"
        assert r.json()["error"]["code"] == "MINOR_BLOCKED"
    finally:
        _cleanup(cid)


def test_room_less_routes_are_not_blocked_without_any_declaration():
    """Beyan yokken bu uçlar çocuk kapısına TAKILMAZ (kapı yalnız beyanla kilitler)."""
    for path, body in [
        ("/api/experimental/shadow/analyze", {"profile": {"name": "hedef"}}),
        ("/api/experimental/chat/respond",
         {"task_id": "t1", "target_profile": {}, "user_profile": {}, "target_message": "selam"}),
    ]:
        with TestClient(app) as client:
            r = client.post(path, json=body)
        assert r.status_code != 451, f"{path} beyansız 451 döndü: {r.text[:200]}"


def test_register_then_clear_restores_flow():
    """Beyan yalnız operatör tarafından kaldırılır ve kaldırma gerçekten açar."""
    cid = _cid()
    try:
        with TestClient(app) as client:
            assert client.post("/api/minor/case", json={"client_id": cid}).json()["allowed"] is False
            assert client.get("/api/minor/state", params={"client_id": cid}).json()["cleared"] is False
            cleared = client.post("/api/minor/clear", json={"client_id": cid}).json()
            state = client.get("/api/minor/state", params={"client_id": cid}).json()
        assert cleared["cleared"] is True
        assert state["declared"] is False and state["cleared"] is True
    finally:
        _cleanup(cid)


def test_state_endpoint_is_honest_when_nothing_declared():
    """Beyan yokken 'temiz' denir AMA yaş hakkında iddia kurulmaz."""
    cid = _cid()
    try:
        with TestClient(app) as client:
            payload = client.get("/api/minor/state", params={"client_id": cid}).json()
        assert payload["declared"] is False
        assert payload["reason_code"] == "not_declared"
        # Dürüstlük: bu katman yaş UYDURMAZ, karar mercii operatördür.
        assert "UYDURMAZ" in payload["detail"]
    finally:
        _cleanup(cid)


def test_ledger_records_both_rejections_and_approvals(tmp_path):
    """Denetim izi sessiz değil: ret VE onay deftere yazılır (hedef hash'li)."""
    cid = _cid()
    ledger = tmp_path / "minor-cases.jsonl"
    api.app.state.minor_cases[cid] = MinorCaseContext(subject_is_minor=True)
    try:
        with TestClient(app) as client:
            client.post(
                "/api/minor/case",
                json={
                    "client_id": cid,
                    "subject_is_minor": True,
                    "case_type": "missing_or_harm",
                    "family_notified": True,
                    "reason": "Çocuk kayıp; aile karakola başvurdu, dosya 2026/4471.",
                    "verified": True,
                    "council_approvals": ["operator:alper", "council:legal"],
                    "case_id": "case-2026-4471",
                },
            )
        lines = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert lines, "defter boş: karar sessizce yutulmuş"
        assert any(l["reason_code"] == "approved" for l in lines), lines
        assert all("case_id" in l for l in lines)
        # Hedefin ham kimliği (telefon/e-posta) dosyaya GİRMEZ; yalnız özet.
        api._require_minor_clearance(cid, subject="+90 555 000 00 00")
        raw = ledger.read_text(encoding="utf-8")
        assert "555 000 00 00" not in raw and "5550000000" not in raw
        assert "sha256:" in raw
    finally:
        _cleanup(cid)


def test_declaration_capacity_is_bounded_and_honest(monkeypatch):
    """Depo sınırsız büyümez: sınır aşılırsa dürüst 503 (sessiz kabul yok)."""
    monkeypatch.setattr(api, "_MINOR_CASE_MAX_ENTRIES", 1)
    filler, cid = _cid(), _cid()
    api.app.state.minor_cases[filler] = MinorCaseContext(subject_is_minor=True)
    try:
        with TestClient(app) as client:
            r = client.post("/api/minor/case", json={"client_id": cid})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "MINOR_CASE_CAPACITY"
        assert cid not in api.app.state.minor_cases
    finally:
        _cleanup(filler)
        _cleanup(cid)


def test_declaration_rejects_malformed_client_id():
    """Beyan yolu da client_id sınırını doğrular (oda anahtarı güvenlik sınırı)."""
    with TestClient(app) as client:
        r = client.post("/api/minor/case", json={"client_id": "kötü id!", "subject_is_minor": True})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_CLIENT_ID"


def test_spine_receives_the_declaration_from_raw_json(monkeypatch):
    """Omurga (ikinci savunma hattı) beyanı HAM JSON'dan da görür.

    `runner.py` kilidi politika kapılarından önce uygular; ama PolicyState'e
    beyan girmezse kilidin ikinci katmanı KÖR kalır. Bu test, API'den gelen
    ham sözlüğün `coerce_minor_case` ile omurgaya taşındığını ölçer.
    """
    from agent_core.agents.osint_investigator import OsintInvestigatorAgent

    state = OsintInvestigatorAgent._policy_state(
        {"policy": {"vault_locked": False, "minor_case": {"subject_is_minor": True}}}
    )
    case = state.minor_case
    assert case is not None, "beyan omurgaya taşınmadı: ikinci katman kör"
    assert case.subject_is_minor is True
    assert MinorGate().evaluate(case).allowed is False

    # Yetişkin beyanı / beyansızlık omurgayı kilitlemez.
    assert OsintInvestigatorAgent._policy_state({"policy": {}}).minor_case is None
    adult = OsintInvestigatorAgent._policy_state(
        {"policy": {"minor_case": {"subject_is_minor": False}}}
    ).minor_case
    assert adult is not None and adult.subject_is_minor is False


def test_no_declaration_leaks_between_tests():
    """Her test kendi beyanını temizler: sızan beyan başka testleri kilitleyemez."""
    assert api.app.state.minor_cases == {}, api.app.state.minor_cases


def test_mission_payload_carries_the_declaration():
    """Beyan görev payload'ına da taşınır (kuşak kuşak savunma).

    Kapı zaten zorunlu tutar; bu satır, beyanı koşucunun da görmesini sağlar —
    omurga kilidi ikinci kez uygular.
    """
    source = inspect.getsource(api)
    assert '"minor_case": _minor_case_for(client_id)' in source, (
        "görev payload'ına minor_case konmuyor: omurga ikinci savunma hattı kör"
    )
