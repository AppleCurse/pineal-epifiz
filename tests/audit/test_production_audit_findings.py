"""Üretim denetimi (2026-09-04) — kapatılan kusurların REGRESYON KORUMASI.

Bu dosya yeni bir davranış sözleşmesi icat etmez; denetimde ölçülen somut
kusurların geri gelmesini engeller.

Durum (2026-09-04 onarım turu; 2026-09-06 round-2 turunda TAMAMLANDI):
  KAPATILDI  P0-1 redact O(N x M)          -> iplik önbellekli tek geçiş regex
             P0-2 cache prune yok          -> get() siler + periyodik prune
             P0-3 dict olmayan vault 500   -> _load_vault() her zaman dict
             P0-4 rooms eviction yok       -> TTL eviction + tavan + id doğrulama
             P0-5 _rate_buckets sızıntısı  -> boş kova iadesi + LRU tavan
             P1-8 time.sleep event loop    -> async _random_delay
             P2-10 auth fail-open          -> PINEAL_ENV belirsizse üretim
             P1-6 extract_username profili-dışı URL  (2026-09-06: strict
                  profile-URL kuralı + scrape guard; xfail kaldı)
             P1-7 evaluate_confidence üretimde kapısı   (2026-09-06:
                  check_scrape_confidence scrape yolunda; xfail kaldı)
             P2-9 bozuk learnings.json 500              (2026-09-06:
                  quarantine + atomik yazım; xfail kaldı)

Bu dosyada AÇIK madde ve xfail işareti YOKTUR (9 işaret 2026-09-06 round-2
turunda kaldırıldı). Tüm maddeler normal testtir — davranış geri gelirse
suite KIZARIR.

Çalıştırma:
    pytest tests/audit/test_production_audit_findings.py -v
"""

from __future__ import annotations

import os
import sqlite3
import time

import pytest

from agent_core.services.response_cache import ResponseCache
from agent_core.utils.security import redact_structure


# --------------------------------------------------------------------------
# P0-1  redact_text her string için tüm environment'ı yeniden tarıyor
# --------------------------------------------------------------------------
def test_redact_structure_recomputes_env_secrets_per_string(monkeypatch):
    """Her metin alanı için `_environment_secret_values()` yeniden kuruluyor.

    Ölçülen maliyet: 900 string'lik tek bir telemetri gövdesi için 900 kez
    env taraması. Telemetri yolu (broadcast_log / broadcast_event) bunu
    event loop üzerinde senkron çağırır.
    """
    import agent_core.utils.security as sec

    for i in range(40):
        monkeypatch.setenv(f"AUDIT_SECRET_{i}", "z" * 24 + str(i))

    calls = {"n": 0}
    original = sec._environment_secret_values

    def spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(sec, "_environment_secret_values", spy)
    payload = {"rows": [{"a": f"x{i}", "b": "y", "c": "z"} for i in range(300)]}

    redact_structure(payload)

    # 900 metin alanı -> 900 env taraması. Beklenen: 1 (önbellekli).
    assert calls["n"] == 1, (
        f"_environment_secret_values {calls['n']} kez çağrıldı; "
        "sır listesi önbelleğe alınmadığı için maliyet metin alanı x env sayısı"
    )


# --------------------------------------------------------------------------
# P0-2  ResponseCache süresi dolan satırları asla silmiyor (disk sızıntısı)
# --------------------------------------------------------------------------
def test_response_cache_prunes_expired_rows(tmp_path):
    """Süresi dolan satırlar silinmeli ve ayrılan alan yeniden kullanılmalı.

    Ham dosya boyutu bilinçli olarak ÖLÇÜLMÜYOR: SQLite boş sayfaları ancak
    tam bir VACUUM ile işletim sistemine iade eder. Sızıntının gerçek ölçütü
    (a) kalan satır sayısı ve (b) aynı hacim tekrar yazıldığında veritabanının
    BÜYÜMEMESİdir — yani alan geri kazanılıp yeniden kullanılıyor mu.
    """
    db = tmp_path / "responses.db"
    cache = ResponseCache(db_path=str(db), ttl_seconds=1)

    for i in range(500):
        cache.put(f"k{i}", "gövde " * 50)
    pages_before = _page_count(db)

    time.sleep(1.1)
    assert all(cache.get(f"k{i}") is None for i in range(500))

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
    assert rows == 0, f"{rows} süresi dolmuş satır hâlâ duruyor (disk sızıntısı)"
    assert free > 0, "silinen satırların alanı serbest bırakılmadı"
    assert cache.pruned >= 500, f"pruned sayacı {cache.pruned}; silmeler izlenmiyor"

    # Alan gerçekten yeniden kullanılıyor mu: aynı hacmi tekrar yaz.
    for i in range(500):
        cache.put(f"yeni{i}", "gövde " * 50)
    assert _page_count(db) <= pages_before + 4, (
        f"veritabanı {_page_count(db)} sayfaya büyüdü (önce {pages_before}); "
        "serbest alan yeniden kullanılmıyor"
    )


def test_low_traffic_expired_rows_are_pruned_by_time_not_write_count(tmp_path):
    """[AUDIT P0-2 v2] Düşük trafikte budama ZAMANA bağlı olmalı.

    İlk onarım budamayı yalnızca yazım SAYISINA bağlamıştı (her 256 yazım).
    Ölçülen boşluk: az sayıda ama benzersiz anahtar üreten bir sistemde 256
    eşiğine HİÇ ulaşılmıyor, süresi dolmuş satırlar sonsuza dek diskte
    kalıyordu (10 yazım + TTL doldu + okuma yok -> 10 satır diskte, pruned=0).
    Bu test o senaryoyu birebir kurar.
    """
    cache = ResponseCache(
        db_path=str(tmp_path / "low.db"), ttl_seconds=1, prune_interval_seconds=1.0
    )
    for i in range(10):                       # 256 eşiğinin ÇOK altında
        cache.put(f"tekil-{i}", "gövde " * 50)

    time.sleep(1.3)                           # hepsinin TTL'i ve budama aralığı doldu
    cache.put("yeni-anahtar", "x")            # tek bir masum yazma tetiklemeli

    with sqlite3.connect(tmp_path / "low.db") as conn:
        rows = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
    assert rows == 1, (
        f"{rows} satır kaldı; süresi dolmuş 10 satır budanmadı "
        "(düşük trafikte yazım-sayısı tetikleyicisi hiç çalışmaz)"
    )
    assert cache.pruned >= 10, f"pruned={cache.pruned}; zaman temelli budama çalışmadı"


def test_startup_prune_clears_rows_left_by_previous_process(tmp_path):
    """Yeniden başlatma, önceki süreçten kalan süresi dolmuş satırları hemen temizlemeli.

    Zaman temelli tetikleyici ilk işleme kadar bekler (varsayılan 15 dk).
    Açılış budaması olmazsa bir çökme/yeniden başlatma döngüsünde birikmiş
    satırlar o süre boyunca diskte kalır. Bu test tam olarak o boşluğu kapatır:
    önceki "süreç" satır bırakır, yeni örnek açılır açılmaz temizlemelidir —
    hiçbir get/put çağrısı yapılmadan.
    """
    db = tmp_path / "restart.db"

    # [AUDIT P0-2 v2] Bu test eskiden "yeni süreçte TTL=0 yap, 25 satır
    # silinsin" diye kurulmuştu. O mekanizma tam olarak düzeltilen kusurdu:
    # satırların ömrü GÜNCEL config'ten yeniden hesaplanıyordu. Artık süre
    # satırda sabit; bu yüzden önceki sürecin satırları GERÇEKTEN süresi
    # dolmuş yazılır ve test asıl iddiasını (açılış budaması) korur.
    previous = ResponseCache(db_path=str(db), ttl_seconds=1)
    for i in range(25):
        previous.put(f"eski-{i}", "gövde " * 40)
    previous.close()

    time.sleep(1.2)
    # Yeni süreç: aynı TTL, satırlar gerçekten süresi dolmuş.
    restarted = ResponseCache(db_path=str(db), ttl_seconds=1)

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
    assert rows == 0, (
        f"açılışta {rows} süresi dolmuş satır bırakıldı; "
        "yeniden başlatma birikimi temizlemiyor"
    )
    assert restarted.pruned >= 25
    restarted.close()


def test_prune_deadline_is_rearmed_even_when_prune_fails(tmp_path, monkeypatch):
    """Budama patlarsa son tarih yine de yenilenmeli.

    Aksi halde her get/put budamayı yeniden dener: kilit çekişmesi + her
    işlemde tekrarlanan hata logu (sessiz performans çöküşü).
    """
    cache = ResponseCache(db_path=str(tmp_path / "fail.db"), ttl_seconds=60)
    cache._prune_deadline = 0.0               # "süresi geçmiş" durumuna zorla
    monkeypatch.setattr(cache, "_conn", None)
    monkeypatch.setattr(cache, "_connect", lambda: (_ for _ in ()).throw(OSError("disk yok")))

    before = cache._prune_deadline
    cache.get("herhangi")
    assert cache._prune_deadline > before, "hatalı budama son tarihi yenilemedi"
    assert cache.errors >= 1


def test_cache_pragmas_are_applied(tmp_path):
    """WAL/auto_vacuum ayarları GERÇEKTEN etkin olmalı.

    Sıra tuzağı: `PRAGMA journal_mode=WAL` veritabanı dosyasını başlatır ve
    sonrasında `auto_vacuum` değiştirilemez (sessizce 0 kalır). Bu test o
    regresyonu yakalar; ayrıca :memory: için dosya-özel pragmaların
    atlanmadığını doğrular.
    """
    cache = ResponseCache(db_path=str(tmp_path / "pragma.db"), ttl_seconds=60)
    conn = cache._conn
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2, (
        "auto_vacuum=INCREMENTAL uygulanmadı — PRAGMA sırası bozulmuş "
        "(journal_mode=WAL önce çalışırsa auto_vacum sessizce 0 kalır)"
    )
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL

    memory_cache = ResponseCache(db_path=":memory:", ttl_seconds=60)
    assert memory_cache._conn.execute("PRAGMA journal_mode").fetchone()[0] == "memory"
    # :memory: üzerinde de yazma/okuma çalışmalı (paylaşılan bağlantı sayesinde)
    memory_cache.put("k", "v")
    assert memory_cache.get("k") == "v"


def _page_count(db) -> int:
    with sqlite3.connect(db) as conn:
        return conn.execute("PRAGMA page_count").fetchone()[0]


# --------------------------------------------------------------------------
# P0-3  get_room(): dict olmayan .pineal_vault.json 500 üretir
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ['["a","b"]', "null", '"düz metin"', "42"])
def test_get_room_survives_non_dict_vault(tmp_path, monkeypatch, raw):
    """`.pineal_vault.json` elle düzenlenip bozulursa API tamamen ölür.

    `json.load` try/except içinde ama sonraki `vault.pop/get` çağrıları değil.
    """
    from backend import api

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pineal_vault.json").write_text(raw, encoding="utf-8")
    api.app.state.rooms.clear()

    room = api.get_room("audit-client")  # TypeError/AttributeError atmamalı
    assert isinstance(room["vault"], dict)
    api.app.state.rooms.clear()


# --------------------------------------------------------------------------
# P0-4  app.state.rooms için hiçbir eviction/TTL yok
# --------------------------------------------------------------------------
def test_idle_rooms_are_reclaimed(monkeypatch):
    """Boşta kalan odalar geri kazanılmalı; aktif görevi olanlar korunmalı."""
    from backend import api

    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()
    monkeypatch.setattr(api, "_ROOM_TTL_SECONDS", 0.0)
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)

    api.get_room("idle-room")
    assert len(api.app.state.rooms) == 1

    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)
    api.get_room("trigger-sweep")          # herhangi bir oda erişimi süpürmeyi tetikler

    assert "idle-room" not in api.app.state.rooms, "boşta kalan oda geri kazanılmadı"
    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()


def test_room_ttl_uses_real_production_window(monkeypatch):
    """Üretim sabitiyle (1800 sn) TTL karşılaştırması doğru mu?

    Sahte kısa bir TTL ile test etmek karşılaştırma mantığını kanıtlamaz.
    Burada saat `time.monotonic` üzerinden kontrol edilir ve modülün GERÇEK
    varsayılanı olan 1800 saniye kullanılır: 1799. sn'de oda yaşamalı,
    1801. sn'de geri kazanılmalı.
    """
    from backend import api

    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()
    assert api._ROOM_TTL_SECONDS == 1800.0, (
        f"üretim TTL sabiti değişmiş: {api._ROOM_TTL_SECONDS}"
    )

    clock = {"now": 1_000.0}
    monkeypatch.setattr(api.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)

    api.get_room("ttl-room")
    assert "ttl-room" in api.app.state.rooms

    # 1799 saniye sonra: hâlâ taze, dokunulmamalı
    clock["now"] += 1_799.0
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)
    api.get_room("probe-1")
    assert "ttl-room" in api.app.state.rooms, "oda TTL dolmadan erken geri kazanıldı"

    # 1801 saniyeye ulaş: süresi dolmuş olmalı
    clock["now"] += 2.0
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)
    api.get_room("probe-2")
    assert "ttl-room" not in api.app.state.rooms, (
        "oda 1800 sn sonra geri kazanılmadı — TTL karşılaştırması bozuk"
    )
    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()


def test_active_rooms_survive_eviction(monkeypatch):
    """Aktif görevi olan bir oda TTL geçmiş olsa bile ASLA geri kazanılmamalı.

    Aksi halde çalışan bir görev ortasında executor'ı altından çekilir ve
    görev sessizce kaybolur.
    """
    import asyncio

    from backend import api

    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()
    clock = {"now": 5_000.0}
    monkeypatch.setattr(api.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)

    room = api.get_room("busy-room")
    never_finishing = asyncio.get_event_loop_policy().new_event_loop().create_future()
    room["mission_tasks"]["op_test"] = never_finishing

    clock["now"] += 99_999.0                  # TTL'i fersah fersah aş
    monkeypatch.setattr(api._evict_rooms, "_last_sweep", 0.0, raising=False)
    api.get_room("probe")

    assert "busy-room" in api.app.state.rooms, "aktif görevi olan oda geri kazanıldı"
    never_finishing.cancel()
    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()


def test_room_capacity_is_bounded(monkeypatch):
    """Oda tavanı aşılınca yeni oda YARATILMAMALI, 503 üretilmeli."""
    from backend import api

    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()
    monkeypatch.setattr(api, "_MAX_ROOMS", 4)
    monkeypatch.setattr(api, "_ROOM_TTL_SECONDS", 10_000.0)

    for i in range(4):
        api.get_room(f"cap-{i}")
    assert len(api.app.state.rooms) == 4

    with pytest.raises(api.RoomCapacityExceeded):
        api.get_room("cap-overflow")
    assert len(api.app.state.rooms) == 4, "tavan aşıldığı halde oda yaratıldı"
    api.app.state.rooms.clear()
    api._rooms_last_seen.clear()


def test_get_room_rejects_malformed_client_id():
    """client_id bir güvenlik sınırıdır: biçim doğrulaması olmadan sınırsız
    uzunlukta/şekilde anahtarlarla kayıt defteri şişirilebilir."""
    from fastapi import HTTPException

    from backend import api

    api.app.state.rooms.clear()
    for bad in ["../etc/passwd", "a" * 5_000, "boşluk var", ""]:
        with pytest.raises(HTTPException):
            api.get_room(bad)
    assert len(api.app.state.rooms) == 0
    api.app.state.rooms.clear()


# --------------------------------------------------------------------------
# P0-5  _rate_buckets anahtarları asla silinmiyor
# --------------------------------------------------------------------------
def test_expired_rate_bucket_is_released(monkeypatch):
    """Kendi penceresi dolmuş kova süpürmede bırakılmalı, taze kova korunmalı.

    Pencere KOVADA saklanır; süpürme artık "en geniş pencere"yi kullanmaz.
    Bu, 1 sn'lik bir kovadaki anahtarın 60 sn beklemesini engeller.
    """
    from backend import api

    now = time.monotonic()
    api._rate_buckets.clear()
    api._rate_buckets["stale"] = api._RateBucket(60)
    api._rate_buckets["stale"].events.append(now - 61)
    api._rate_buckets["empty"] = api._RateBucket(60)
    api._rate_buckets["short-stale"] = api._RateBucket(1)
    api._rate_buckets["short-stale"].events.append(now - 2)
    api._rate_buckets["fresh"] = api._RateBucket(60)
    api._rate_buckets["fresh"].events.append(now)
    monkeypatch.setattr(api, "_MAX_RATE_BUCKETS", 100)

    api._sweep_rate_buckets(now)

    assert "stale" not in api._rate_buckets, "penceresi dolmuş kova geri verilmedi"
    assert "empty" not in api._rate_buckets, "boş kova geri verilmedi"
    assert "short-stale" not in api._rate_buckets, (
        "kısa pencereli kova, başka kovaların 60 sn'lik penceresi yüzünden "
        "bellekte tutuluyor — pencere kova başına uygulanmıyor"
    )
    assert "fresh" in api._rate_buckets, "taze kova yanlışlıkla silindi"
    api._rate_buckets.clear()


def test_rate_buckets_reclaimed_without_waiting_for_cap(monkeypatch):
    """[AUDIT P0-5 v3 — çapraz denetim bulgusu] Geri kazanım ZAMANA bağlı olmalı.

    Salim'in sorusu: P0-2'deki "eşiğe hiç ulaşılmama" hatasının ikizi burada
    da var mı? Vardı — süpürme yalnızca tavan (100.000) aşıldığında
    çalışıyordu. Ölçülen: 30.000 tekil anahtar, pencereleri dolmuş, süpürme
    çağıran hiçbir şey yok -> 30.000 kova / 26.4 MB süresiz bellekte.
    Onarım sonrası aynı senaryo 1 kovaya / 0.9 MB'a iniyor.
    """
    from backend import api

    api.RATE_LIMITS["openai"] = (60, 1)          # pencere 1 sn
    api._rate_buckets.clear()
    monkeypatch.setattr(api, "_RATE_SWEEP_INTERVAL_SECONDS", 1.0)
    monkeypatch.setattr(api, "_rate_sweep_deadline", time.monotonic() + 1.0)

    for i in range(2_000):                       # tavanın ÇOK altında
        api.rate_limit(f"tekil-{i}", "openai")
    assert len(api._rate_buckets) == 2_000

    time.sleep(1.2)                              # pencere + süpürme aralığı doldu
    api.rate_limit("tetikleyici", "openai")      # TEK istek geri kazanmalı

    assert len(api._rate_buckets) <= 2, (
        f"{len(api._rate_buckets)} kova kaldı; düşük trafikte tavana hiç "
        "ulaşılmadığı için süresi dolmuş kovalar geri kazanılmıyor"
    )
    api._rate_buckets.clear()
    api.RATE_LIMITS["openai"] = (60, 60)


def test_sweep_does_not_run_on_every_request_at_cap(monkeypatch):
    """Tavan aşıldığında süpürme HER istekte çalışmamalı (histerezis).

    Ölçülen eski davranış: tavan doluyken 12/12 istek süpürme ödüyordu;
    üretim tavanında (100.000) bu istek başına ~48-57 ms demekti — kendi
    kendine DoS. Histerezis tavanın ~%80'ine indiği için süpürme seyrelir.
    """
    from backend import api

    api._rate_buckets.clear()
    monkeypatch.setattr(api, "_MAX_RATE_BUCKETS", 200)
    monkeypatch.setattr(api, "_RATE_SWEEP_INTERVAL_SECONDS", 1e9)   # yalnız tavan yolu

    sweeps = {"n": 0}
    real = api._sweep_rate_buckets

    def counting(now):
        sweeps["n"] += 1
        real(now)

    monkeypatch.setattr(api, "_sweep_rate_buckets", counting)

    for i in range(200):
        api.rate_limit(f"dolu-{i}", "openai")
    sweeps["n"] = 0
    for i in range(40):
        api.rate_limit(f"yeni-{i}", "openai")

    assert sweeps["n"] < 40, (
        f"40 istekte {sweeps['n']} süpürme çalıştı; histerezis yok, "
        "her istek tüm sözlüğü sıralıyor"
    )
    assert len(api._rate_buckets) <= 200
    api._rate_buckets.clear()


def test_rate_bucket_count_is_bounded(monkeypatch):
    """Farklı kimlikler sınırsız sayıda kalıcı sözlük girdisi bırakmamalı."""
    from backend import api

    api._rate_buckets.clear()
    monkeypatch.setattr(api, "_MAX_RATE_BUCKETS", 50)
    monkeypatch.setattr(api, "_RATE_SWEEP_INTERVAL_SECONDS", 1e9)  # yalnız tavan yolu
    # Pencere UZUN tutulur: kovaların hepsi taze. Böylece sayıyı yalnızca LRU
    # aşaması düşürebilir — aşama 1 (süresi dolmuş) hiçbir şey silmez.
    monkeypatch.setitem(api.RATE_LIMITS, "openai", (60, 1_000_000))

    for i in range(2_000):
        api.rate_limit(f"identity-{i}", "openai")

    assert len(api._rate_buckets) <= 50, (
        f"{len(api._rate_buckets)} kalıcı kova birikti; LRU tavan kırpma çalışmıyor"
    )
    api._rate_buckets.clear()
    monkeypatch.setitem(api.RATE_LIMITS, "openai", (60, 60))


# --------------------------------------------------------------------------
# P1-6  extract_username URL path'ini doğrulamıyor -> yanlış hedef kazıma
# --------------------------------------------------------------------------
# [AUDIT 2026-09-06] P1-6 KAPANDI: extract_username yalnız tek-segmentli,
# rezerv olmayan, geçerli karakter/uzunluktaki instagram.com/<kullanici>
# URL'lerinden kullanıcı adı üretir; profil dışı URL "" üretir ve
# scrape_instagram kazımayı başlatmaz. Xfail işareti kaldırıldı.
@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/p/CxYz123Ab/",
        "https://www.instagram.com/reel/DaBc9/",
        "https://www.instagram.com/explore/tags/kedi/",
        "https://www.instagram.com/stories/someone/123/",
        "https://www.instagram.com/accounts/login/",
        "https://www.instagram.com/",
    ],
)
def test_extract_username_rejects_non_profile_urls(url):
    """Modül dokümanı 'yanlış hedef kazınmaz' diyor; kod path'i doğrulamıyor."""
    from agent_core.services.platform_registry import (
        effective_scraper_type,
        extract_username,
    )

    assert effective_scraper_type(url) == "instagram"
    username = extract_username(url)
    # Şu an: 'CxYz123Ab', 'kedi', '123', 'login', 'www.instagram.com' ...
    assert username not in {
        "CxYz123Ab", "DaBc9", "kedi", "123", "login", "www.instagram.com",
    }, f"{url!r} profil URL'si değil ama {username!r} hedef kullanıcı adı kabul edildi"


# --------------------------------------------------------------------------
# P1-7  Scraper anti-halüsinasyon güven kapısı üretimde hiç çağrılmıyor
# --------------------------------------------------------------------------
# [AUDIT 2026-09-06] P1-7 KAPANDI: platform_registry.scrape_instagram
# kazıma sonrası evaluate_confidence'ı çağırır; PINEAL_MIN_SCRAPER_CONFIDENCE
# (0.6) altında InsufficientEvidenceError yükseltir. Xfail işareti kaldırıldı.
def test_evaluate_confidence_is_wired_into_production():
    """Testler evaluate_confidence'ı doğruluyor, üretim kodu hiç çağırmıyor."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2]
    callers = []
    for path in (root / "agent_core").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\.evaluate_confidence\(", text):
            callers.append(f"{path.relative_to(root)}:{text[:match.start()].count(chr(10)) + 1}")
    assert callers, (
        "evaluate_confidence yalnızca tanımıyla var; hiçbir üretim yolundan "
        "çağrılmıyor — 'skor < 0.6 ise halt' sözleşmesi uygulanmıyor"
    )


# --------------------------------------------------------------------------
# P1-8  Scraper event loop'u 2-5 saniye bloke ediyor
# --------------------------------------------------------------------------
def test_scraper_delay_does_not_block_event_loop():
    """_random_delay event loop'u bloke etmemeli.

    Kaynak metninde "time.sleep" aramak yeterli değil (docstring de eşleşir);
    asıl sözleşme: fonksiyon bir coroutine olmalı VE çağrı noktası await etmeli.
    """
    import inspect

    from agent_core.scraper.instagram_ghost import InstagramGhostScraper

    assert inspect.iscoroutinefunction(InstagramGhostScraper._random_delay), (
        "_random_delay senkron; async scrape_async içinden çağrıldığında tüm "
        "event loop 2-5 saniye donar"
    )
    source = inspect.getsource(InstagramGhostScraper.scrape_async)
    assert "await self._random_delay()" in source, (
        "çağrı noktası await etmiyor — coroutine hiç çalışmaz ya da uyarı üretir"
    )


@pytest.mark.asyncio
async def test_scraper_delay_yields_to_event_loop(monkeypatch):
    """Davranışsal kanıt: bekleme sırasında event loop başka iş çalıştırabilmeli."""
    import asyncio

    from agent_core.scraper.instagram_ghost import InstagramGhostScraper

    original_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: original_sleep(0))
    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0)
            ticks += 1

    task = asyncio.create_task(ticker())
    await InstagramGhostScraper()._random_delay()
    await task
    assert ticks > 0, "bekleme sırasında event loop hiç işlemedi (senkron blokaj)"


# --------------------------------------------------------------------------
# P2-9  /api/override bozuk learnings.json ile kalıcı 500
# --------------------------------------------------------------------------
# [AUDIT 2026-09-06] P2-9 KAPANDI: /api/override artık (a) bozuk/şemasız
# learnings.json'u yedekleyip sıfırdan devam eder, (b) atomik (tmp+replace)
# yazar -> endpoint bir daha kalıcı 500 üretemez. Xfail işareti kaldırıldı.
@pytest.mark.parametrize("raw", ['{ bozuk', '{"fact": "x"}'])
def test_api_override_survives_corrupt_learnings(tmp_path, monkeypatch, raw):
    from fastapi.testclient import TestClient

    from backend import api

    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(tmp_path))
    api.app.state.rooms.clear()
    room = api.get_room("audit-override")
    storage = room["executor"].memory.storage_path
    os.makedirs(storage, exist_ok=True)
    with open(os.path.join(storage, "learnings.json"), "w", encoding="utf-8") as fh:
        fh.write(raw)

    with TestClient(api.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/override",
            json={"client_id": "audit-override", "fact": "deneme", "tag": "t"},
        )
    api.app.state.rooms.clear()

    assert response.status_code != 500, (
        f"learnings.json={raw!r} iken /api/override 500 döndü; "
        "dosya bir kez bozulursa endpoint kalıcı olarak kullanılamaz"
    )
    # [P2-9] Bozuk dosya silinmemeli, learnings.json.corrupt.* olarak yedeklenmeli
    # (main 56fec0e uzerindeki ekleme; merge ile birlestirildi). Audit uretimi
    # şema hatasını .schema.* ile ayırdığı için her iki aile de kabul edilir.
    corrupt_backups = [
        f for f in os.listdir(storage)
        if "learnings.json.corrupt" in f or "learnings.json.schema" in f
    ]
    assert len(corrupt_backups) >= 1, "Bozuk dosya yedeklenmeden kayboldu veya silindi"


# --------------------------------------------------------------------------
# P2-10  Üretimde PINEAL_ENV set edilmezse kimlik doğrulama tamamen kapalı
# --------------------------------------------------------------------------
def test_auth_fails_closed_by_default(monkeypatch):
    """PINEAL_ENV unutulduğunda (en olası dağıtım hatası) uygulama kimlik
    doğrulamasız AÇILMAMALI; token yoksa startup reddedilmeli."""
    from agent_core.utils.security import SecurityConfigurationError, security_posture

    monkeypatch.delenv("PINEAL_ENV", raising=False)
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.delenv("PINEAL_REQUIRE_AUTH", raising=False)

    with pytest.raises(SecurityConfigurationError) as raised:
        security_posture()
    assert raised.value.error_code == "PRODUCTION_AUTH_REQUIRED", (
        "PINEAL_ENV belirsizken geliştirme varsayılıyor — fail-open"
    )


def test_explicit_development_still_opens_auth(monkeypatch):
    """Geriye uyumluluk: açık geliştirme seçimi çalışmaya devam etmeli."""
    from agent_core.utils.security import security_posture

    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.delenv("PINEAL_REQUIRE_AUTH", raising=False)
    assert security_posture()["auth_required"] is False


@pytest.mark.parametrize("value", ["production", "prod", "staging", "PRODUCTION", " production "])
def test_non_development_environments_require_token(monkeypatch, value):
    from agent_core.utils.security import SecurityConfigurationError, security_posture

    monkeypatch.setenv("PINEAL_ENV", value)
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    with pytest.raises(SecurityConfigurationError):
        security_posture()


# --------------------------------------------------------------------------
# P2-13  Sınırsız büyüyen iki sözlük: canonical_memory._locks ve
#        dialogue_manager.sessions  (desen üçüncü kez çıktı)
# --------------------------------------------------------------------------
def test_canonical_memory_locks_are_reclaimed(tmp_path):
    """[AUDIT P2-13] `_locks` toplam task sayısıyla değil eşzamanlılıkla sınırlı olmalı.

    Ölçülen eski davranış: 5.000 sıralı merge_evidence -> 5.000 kalıcı
    asyncio.Lock (izole 0.80 MB, 167 bayt/girdi), hiçbir zaman silinmiyordu.
    """
    import asyncio

    from agent_core.services.canonical_memory import CanonicalMemory

    mem = CanonicalMemory(storage_path=str(tmp_path))

    async def run():
        for i in range(500):
            await mem.merge_evidence(f"task-{i}", [{"source": "x", "claim": f"c{i}"}])

    asyncio.run(run())

    assert len(mem._locks) == 0, (
        f"{len(mem._locks)} kilit girdisi kaldı; defaultdict her task_id için "
        "kalıcı girdi üretiyor ve hiçbir geri kazanım yok"
    )


def test_canonical_memory_lock_still_serializes_concurrent_merges(tmp_path):
    """Sızıntı kapatılırken kilit BOZULMAMALI: aynı task'ta çakışma olmamalı.

    Kilit no-op yapılırsa 8 eşzamanlı merge aynı `.tmp` yolunda çakışır
    (ölçülen: 6/8 FileNotFoundError). Kilit yerindeyken 0/8 hata.
    """
    import asyncio

    from agent_core.services import canonical_memory as cm

    mem = cm.CanonicalMemory(storage_path=str(tmp_path))
    state = {"n": 0, "max": 0, "errors": 0}
    orig = cm.CanonicalMemory._atomic_write

    def spy(path, payload):
        state["n"] += 1
        state["max"] = max(state["max"], state["n"])
        time.sleep(0.005)                       # çakışma penceresini aç
        try:
            return orig(path, payload)
        finally:
            state["n"] -= 1

    async def run():
        results = await asyncio.gather(
            *[mem.merge_evidence("ayni-task", [{"source": "x", "claim": f"c{i}"}]) for i in range(8)],
            return_exceptions=True,
        )
        state["errors"] = sum(1 for r in results if isinstance(r, Exception))

    cm.CanonicalMemory._atomic_write = staticmethod(spy)
    try:
        asyncio.run(run())
    finally:
        cm.CanonicalMemory._atomic_write = staticmethod(orig)

    assert state["max"] == 1, f"aynı anda {state['max']} merge içerdeydi; kilit dışlama sağlamıyor"
    assert state["errors"] == 0, f"{state['errors']}/8 merge hata verdi; kilit korumuyor"


def test_dialogue_sessions_are_bounded_by_cap(monkeypatch):
    """[AUDIT P2-13] `sessions` tavanla sınırlı olmalı.

    Ölçülen eski davranış: 50.000 start_session -> 50.000 kalıcı
    DialogueContext / 58.0 MB, girdi başına 1.217 bayt, hiçbiri silinmiyordu.
    """
    from agent_core.chat.dialogue_manager import DialogueManager

    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_SESSIONS", "100")
    monkeypatch.setenv("PINEAL_DIALOGUE_SESSION_TTL_SECONDS", "3600")
    dm = DialogueManager(llm_gateway=object())

    for i in range(5_000):
        dm.start_session(f"task-{i}", {"b": 1}, {"k": 2})

    assert len(dm.sessions) <= 100, (
        f"{len(dm.sessions)} oturum birikti; tavan uygulanmıyor"
    )


def test_dialogue_sessions_expire_by_time(monkeypatch):
    """Oturumlar ZAMANLA düşmeli — 'süresi doldu' hatası bunu ima ediyordu
    ama uygulayan tek satır kod yoktu."""
    from agent_core.chat.dialogue_manager import DialogueManager

    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_SESSIONS", "10000")
    monkeypatch.setenv("PINEAL_DIALOGUE_SESSION_TTL_SECONDS", "1")
    dm = DialogueManager(llm_gateway=object())

    for i in range(200):
        dm.start_session(f"task-{i}", {}, {})
    assert len(dm.sessions) == 200

    time.sleep(1.2)
    dm.start_session("yeni", {}, {})

    assert len(dm.sessions) == 1, (
        f"{len(dm.sessions)} oturum kaldı; TTL dolmuş oturumlar geri kazanılmıyor"
    )


# --------------------------------------------------------------------------
# P0-2 v2  Süre satırda saklanmalı, config'ten yeniden hesaplanmamalı
# --------------------------------------------------------------------------
def test_cache_ttl_is_stored_per_row_not_recomputed_from_config(tmp_path):
    """[AUDIT P0-2 v2] TTL değişikliği mevcut satırların ömrünü değiştirmemeli.

    Ölçülen eski davranış: 7 günlük TTL ile yazılan kayıt, aynı dosya
    TTL=1 sn ile açılınca 1.2 sn içinde yok oluyordu (erken silme).
    """
    from agent_core.services.response_cache import ResponseCache

    db = str(tmp_path / "a.db")
    a = ResponseCache(db_path=db, ttl_seconds=7 * 24 * 3600)
    a.put("k1", "v1")
    a.close()

    b = ResponseCache(db_path=db, ttl_seconds=1)
    time.sleep(1.2)
    try:
        assert b.get("k1") == "v1", (
            "7 günlük kayıt, TTL=1 sn ile açılınca silindi; süre satırda "
            "değil config'ten türetiliyor"
        )
        assert b.prune() == 0, "erken silme: prune süresi dolmamış satırı sildi"
    finally:
        b.close()


def test_cache_expired_row_still_expires_after_ttl_raised_to_infinite(tmp_path):
    """Tersi yön: kısa TTL ile yazılan kayıt, TTL süresiz yapılınca
    sonsuza dek yaşamamalı (ölçülen eski davranış: yaşıyordu, prune 0 sildi)."""
    from agent_core.services.response_cache import ResponseCache

    db = str(tmp_path / "b.db")
    c = ResponseCache(db_path=db, ttl_seconds=1)
    c.put("k1", "v1")
    c.close()

    time.sleep(1.2)
    d = ResponseCache(db_path=db, ttl_seconds=None)
    try:
        # Açılış budaması satırı zaten sildiği için get() tek başına ayırt
        # edici değil (mutasyon testi bunu ortaya çıkardı): süreyi SATIRDAN
        # okuma kararını doğrudan doğrula.
        assert d._is_expired(time.time() - 10) is True, (
            "süresi dolmuş satır, güncel config ttl_seconds=None diye canlı "
            "sayılıyor; süre satırdan değil config'ten türetiliyor"
        )
        assert d._is_expired(None) is False, "expires_at NULL olan satır süresiz sayılmalı"
        assert d.get("k1") is None, (
            "süresi dolmuş kayıt TTL=None ile açılınca canlandı; "
            "satırın kendi expires_at değeri kullanılmıyor"
        )
    finally:
        d.close()


def test_cache_schema_migrates_legacy_db_without_expires_at(tmp_path):
    """expires_at kolonu olmayan eski veritabanı açılabilmeli ve doldurulmalı."""
    import sqlite3

    from agent_core.services.response_cache import ResponseCache

    db = str(tmp_path / "legacy.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE response_cache "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at REAL NOT NULL)"
    )
    con.execute(
        "INSERT INTO response_cache VALUES ('eski', 'deger', ?)", (time.time() - 10,)
    )
    con.commit()
    con.close()

    cache = ResponseCache(db_path=db, ttl_seconds=3600)
    try:
        assert cache.get("eski") == "deger", "göç sonrası eski satır okunamadı"
        cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(response_cache)")}
        assert "expires_at" in cols, "göç expires_at kolonunu eklemedi"
        filled = sqlite3.connect(db).execute(
            "SELECT expires_at FROM response_cache WHERE key='eski'"
        ).fetchone()[0]
        assert filled is not None, "göç mevcut satırların expires_at değerini doldurmadı"
    finally:
        cache.close()


# --------------------------------------------------------------------------
# P1-18a/b/c  Hız sınırı kimliği istemci kontrollüydü + bare except
# --------------------------------------------------------------------------
def _dev_client():
    from fastapi.testclient import TestClient

    from backend import api

    api._rate_buckets.clear()
    return api, TestClient(api.app)


def test_rate_limit_identity_is_server_derived_not_client_supplied(monkeypatch):
    """[AUDIT P1-18a] Hız sınırı istemcinin gönderdiği client_id'ye bağlanamaz.

    Ölçülen eski davranış: /api/initiate (limit 5/60sn) her istekte farklı
    client_id ile 200 istek -> 0/200 429. Sınır hiç devreye girmiyordu.
    Düzeltme sonrası: 12 farklı client_id -> 7/12 429.
    """
    import uuid

    api, client = _dev_client()

    # run_mission gerçek kazıma işi yapıyor ve TestClient portal kapanışını
    # thread.join()'de kilitliyordu (tam pakette ölçülen donma). Hız sınırı
    # davranışını ölçmek için görev gövdesi etkisizleştirilir; endpoint'in
    # kendi rate_limit yolu aynen çalışır.
    async def _no_mission(*_args, **_kwargs):
        return None

    monkeypatch.setattr(api, "run_mission", _no_mission)
    codes = [
        client.post("/api/initiate", json={
            "client_id": f"cli{uuid.uuid4().hex[:9]}",
            "subject_consent": True,
            "url": "https://www.instagram.com/ornek/",
            "rituals": "x", "playlist": "y", "envies": "z",
        }).status_code
        for _ in range(8)
    ]
    try:
        assert codes.count(429) > 0, (
            f"{codes} — farklı client_id ile hız sınırı atlatılıyor; "
            "anahtar istemci kontrollü"
        )
    finally:
        api._rate_buckets.clear()


def test_rate_identity_falls_back_to_shared_bucket_not_unlimited():
    """Kimlik yoksa fail-safe: paylaşımlı ve sınırlı kova, sınırsız değil."""
    from backend import api

    class Bare:
        pass

    first = api._rate_identity(Bare())
    second = api._rate_identity(Bare())
    assert first == second, (
        "kimliksiz çağıranlar farklı kova alıyor -> her biri sınırsız olur"
    )
    assert first == api._UNIDENTIFIED_RATE_IDENTITY

    class WithIdentity:
        state = type("S", (), {"rate_identity": "sunucu-kimligi"})()

    assert api._rate_identity(WithIdentity()) == "sunucu-kimligi"


def test_general_api_bucket_limits_previously_unlimited_endpoints(monkeypatch):
    """[AUDIT P1-18b] Mutasyon uçları (/api/override, /api/executor/intervene,
    /api/tasks/*/cancel, DELETE /api/tasks/*) önceden tamamen sınırsızdı.

    Genel kova paylaşımlı süreç-durumudur; bu test onu tüketip bırakırsa
    sonraki testler erken 429 alır (ölçülen gerçek bir tam-paket arızası).
    Bu yüzden limit küçültülür ve kova sonda temizlenir.
    """
    api, client = _dev_client()
    monkeypatch.setitem(api.RATE_LIMITS, "api", (3, 60))
    try:
        codes = [
            client.post("/api/tasks/olmayan-gorev/cancel").status_code
            for _ in range(6)
        ]
        assert codes.count(429) > 0, (
            f"{codes} — mutasyon uçlarında genel /api/ kovası çalışmıyor"
        )
        assert codes[0] != 429, "ilk istek sınırlanmamalıydı"

        # GET'ler genel kovayı tüketmemeli: ucuz okuma, mutasyon bütçesini yemesin.
        api._rate_buckets.clear()
        gets = [client.get("/api/telemetry?client_id=ci").status_code for _ in range(10)]
        assert gets.count(429) == 0, (
            f"GET istekleri genel kovadan sınırlanıyor: {gets}"
        )
    finally:
        api._rate_buckets.clear()


def test_websocket_cancellation_propagates_and_still_cleans_up():
    """[AUDIT P1-18c] bare `except:` CancelledError'ı yutuyordu.

    Ölçülen eski davranış: task.cancelled() == False, görev normal döndü.
    Ayrıca kontrol ölçümü `except Exception:`'ın TEK BAŞINA yetmediğini
    gösterdi: iptal durumunda temizlik kayboluyordu. Bu yüzden finally.
    """
    import asyncio

    from backend import api

    class FakeWS:
        def __init__(self):
            self.parked = asyncio.Event()

        async def accept(self):
            pass

        async def receive_json(self):
            return {}

        async def send_json(self, _payload):
            pass

        async def close(self, code=1000):
            pass

        async def receive_text(self):
            await self.parked.wait()
            return ""

    async def scenario():
        ws = FakeWS()
        cid = "cancel-probe-test"
        task = asyncio.create_task(api.websocket_endpoint(ws, cid))
        await asyncio.sleep(0.05)
        task.cancel()
        propagated = False
        try:
            await task
        except asyncio.CancelledError:
            propagated = True
        room = api.app.state.rooms.get(cid, {})
        cleaned = len(room.get("websockets", ())) == 0
        return propagated, cleaned

    propagated, cleaned = asyncio.run(scenario())
    assert propagated, "CancelledError yutuldu; görev iptal edilmiş sayılmıyor"
    assert cleaned, "iptal durumunda websocket odadan düşürülmedi (finally eksik)"
