"""
Test ortamı için ortak ayarlar.

Önemli: LLM yanıt önbelleği (ResponseCache) varsayılan olarak ./cache/responses.db
konumunu kullanır. Testler aynı kısa prompt'ları (ör. "ping") tekrar kullandığından,
bir testin başarılı yanıtı başka bir testin hata senaryosuna sızabilir (ör. 429
sonrası başarı cache'lenir, 401 testi hatayı görmez).

Bu otomatik fixture, her test için cache'i geçici, izole bir veritabanına yönlendirir.
Cache davranışını özel olarak test edenler (tests/unit/test_response_cache.py)
PINEAL_RESPONSE_CACHE / PINEAL_CACHE_PATH değişkenlerini kendileri ayarlayabilir.
"""
import os
import tempfile

import dotenv
import pytest

# Hermetik test garantisi: backend.api veya diğer modüller yüklendiğinde üretim .env
# dosyasındaki anahtarların/endpoint'lerin test ortamına sızmasını engeller.
dotenv.load_dotenv = lambda *args, **kwargs: False


# --- İTHALAT-ANI (import-time) DİSK YAN ETKİSİ -------------------------------
#
# `backend.api` içe aktarılırken ResponseCache varsayılan yolu
# (`cache/responses.db`, WAL modu) diske yazılır (os.makedirs +
# sqlite3.connect). Bu yan etki autouse fixture'lar KOŞMADAN ÖNCE
# gerçekleştiği için yalnız fixture içinde ortam değişkeni ayarlamak yetmez.
#
# Bu yüzden izolasyon CONFTEST MODÜL SEVİYESİNDE kurulur: conftest.py test
# modüllerinden ÖNCE içe aktarılır, dolayısıyla aşağıdaki değerler ithalat-anı
# yan etkisini de kapsar. Oturum boyunca tek geçici kök kullanılır; tekil
# testler kendi `tmp_path` değerleriyle bunu fixture içinde EZEBİLİR.
_SESSION_ROOT = tempfile.mkdtemp(prefix="pineal-test-isolation-")
os.environ.setdefault("PINEAL_CACHE_PATH", os.path.join(_SESSION_ROOT, "cache", "responses.db"))
os.environ.setdefault("PINEAL_MEMORY_PATH", os.path.join(_SESSION_ROOT, "memory"))
os.environ.setdefault(
    "PINEAL_MINOR_LEDGER_PATH",
    os.path.join(_SESSION_ROOT, "memory", "ledger", "minor-cases.jsonl"),
)
# GÖREV SAHİPLİĞİ KAYDI da izole edilir: `backend/security/task_ownership.py`
# varsayılanını PINEAL_MEMORY_PATH'ten TÜRETİR (memory/task_owners.db), ama
# modül ilk kullanımda DİSKTE dosya açar. Fixture yetişemeyecek import-time
# yan etkisi olmasa da, depo köküne kalıcı bir .db düşmesin diye hem oturum
# kökünde hem fixture içinde tmp_path'e bağlanır.
os.environ.setdefault(
    "PINEAL_TASK_OWNERS_DB",
    os.path.join(_SESSION_ROOT, "memory", "task_owners.db"),
)


@pytest.fixture(autouse=True)
def _isolate_response_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_CACHE_PATH", str(tmp_path / "test_responses.db"))
    # KALICI KANIT DEPOSU DA İZOLE EDİLİR: tek başına PINEAL_CACHE_PATH yetmez,
    # PINEAL_MEMORY_PATH (varsayılan "./memory/") de tmp_path'e taşınır — aksi
    # halde test koşusu depo kökündeki memory/ dizinine görev kayıtları yazar
    # ve bunlar backend tarafından canlı kayıt gibi servis edilebilir.
    #
    # PINEAL_MEMORY_DB ayrıca sabitlenir: hindsight_memory.py onu
    # PINEAL_MEMORY_PATH'ten TÜRETİR; çağıran açıkça override etmişse eski
    # değer kalmasın diye ikisi birlikte tmp_path'e bağlanır.
    # Dizin adı bilerek "memory" DEĞİL: tests/unit/test_security_hardening.py
    # kendi `tmp_path / "memory"` dizinini `mkdir()` (exist_ok=False) ile
    # kuruyor; aynı ad FileExistsError ile çakışır. "pineal_memory" ayırır.
    _memory_root = tmp_path / "pineal_memory"
    _memory_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(_memory_root))
    monkeypatch.setenv("PINEAL_MEMORY_DB", str(_memory_root / "hindsight.db"))

    # PINEAL_MEMORY_PATH YETERLİ DEĞİL: bazı kalıcı yazıcılar varsayılan
    # yollarını ondan TÜRETMEZ, doğrudan CWD'ye göre BAĞIL kurar (ör.
    # memory/ledger/minor-cases.jsonl — çocuk kilidi denetim defteri). Bu
    # yüzden bağıl varsayılanı olan HER kalıcı yol tek tek tmp_path'e bağlanır.
    # Testler kendi değerlerini monkeypatch ile sonradan kurarsa ÖNCELİK
    # ONLARINDIR (autouse fixture önce koşar) — hiçbir testin niyeti bozulmaz.
    monkeypatch.setenv(
        "PINEAL_MINOR_LEDGER_PATH", str(_memory_root / "ledger" / "minor-cases.jsonl")
    )
    # Görev sahipliği kaydı testler arasında SIZMASIN: Alice'in görevini
    # sahiplenen kayıt Bob'un testine kalırsa sahiplik kararı yanlış ölçülür.
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(_memory_root / "task_owners.db"))
    monkeypatch.setenv("PINEAL_MEDIA_DIR", str(_memory_root / "media"))
    monkeypatch.setenv("PINEAL_REPORT_DIR", str(_memory_root / "reports"))
    monkeypatch.setenv("PINEAL_CALIB_DIR", str(_memory_root / "calibration"))
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(_memory_root / "telemetry"))
    monkeypatch.setenv("PINEAL_CRYSTAL_DIR", str(_memory_root / "crystals"))
    monkeypatch.setenv("PINEAL_SPEECH_DIR", str(_memory_root / "speech"))
    monkeypatch.setenv("PINEAL_MAIGRET_DB", str(_memory_root / "maigret_db_refreshed.json"))
    # Tests are hermetic even when invoked from a production-configured shell;
    # individual auth tests explicitly opt back into production/token modes.
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.setenv("PINEAL_REQUIRE_AUTH", "false")
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.delenv("LIVE_LLM_E2E", raising=False)
    monkeypatch.delenv("PINEAL_ROUTER_LIVE", raising=False)
    monkeypatch.delenv("OPENROUTER_MAX_SPEND_USD", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_TIER_1_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_TIER_2_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_BACKUP_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_VERTEX_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("NOUS_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("SAMBANOVA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("NINEROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("NINEROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PINEAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PINEAL_LLM_API_KEY", raising=False)
    yield


@pytest.fixture
def vault_open(monkeypatch):
    """KASA MANDALINI AÇAR — test ÖN KOŞULU, otomatik DEĞİL.

    [KASA MANDALI] `backend/api.py::_check_vault_interlock` dış dünyaya açılan
    her ucun (tarayıcı, OSINT taramaları, web kazıma, public-web araması)
    kapısındaki TEK kilittir. Bu fixture BİLİNÇLİ olarak `autouse` değildir:
    kilidin KAPALI hâlini ölçen testler (tests/unit/test_vault_egress_lock.py)
    vardır ve otomatik açma onları anlamsızlaştırırdı — yani kasa kilidi hiç
    test edilmemiş olurdu. Kullanan her test "kasayı ölçmüyorum, kasa açıkken
    kendi konumu ölçüyorum" demiş olur.
    """
    from backend import api

    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    return True


@pytest.fixture(autouse=True)
def _isolate_threshold_calibration(tmp_path, monkeypatch):
    """[FAZ B · B5] Eşik kalibrasyon ledger'ı testler arasında SIZMASIN.

    Kalibrasyon verisi MAKİNEDE kalır ve eşiği değiştirir: bir testin yazdığı
    ölçüm bir sonraki testin eşiğini (ve dolayısıyla alıntı kapısının kararını)
    sessizce değiştirirdi. Ledger geçici dizine taşınır; gözlem varsayılan
    KAPALIdır, kalibrasyonu test eden dosyalar kendileri açar.
    """
    monkeypatch.setenv("PINEAL_CALIB_DIR", str(tmp_path / "calibration"))
    # [FAZ B · B2/B3] Hafıza kristali de makineye yazılır: testler arasında sızmasın.
    monkeypatch.setenv("PINEAL_CRYSTAL_DIR", str(tmp_path / "crystals"))
    # [FAZ C · C1] Jenerik yanıt telemetrisi de makineye yazılır.
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "false")
    monkeypatch.delenv("PINEAL_THRESHOLD", raising=False)
    monkeypatch.delenv("PINEAL_THRESHOLD_QUOTE", raising=False)
    monkeypatch.delenv("PINEAL_CALIB_MIN_SAMPLES", raising=False)
    yield


@pytest.fixture(autouse=True)
def _isolate_rate_limit_state():
    """[AUDIT P1-18a] `backend.api._rate_buckets` süreç genelinde paylaşılan
    mutable durumdur.

    Hız sınırı anahtarı artık SUNUCU kimliğine bağlı (eskiden istemcinin
    gönderdiği `client_id` idi). Eski davranış testler arasında kazara
    izolasyon sağlıyordu: her test benzersiz bir client_id kullandığı için
    kovalar çakışmıyordu. Anahtar sunucu kimliğine geçince tüm TestClient
    istekleri aynı kovayı paylaşmaya başladı ve bir testin tükettiği bütçe
    sonraki testte erken 429'a yol açtı (ölçülen: test_initiate_rate_limit_429
    ve test_ws_ordering tam pakette kırmızı, tek başına yeşil).
    """
    try:
        from backend import api
    except Exception:  # api yüklenemiyorsa test zaten kendi hatasını verir
        yield
        return
    api._rate_buckets.clear()
    yield
    api._rate_buckets.clear()


@pytest.fixture(autouse=True)
def _isolate_gateway_contextvars():
    """Gateway contextvar'larını testler arasında temizle.

    (b'') kural 1 gereği `get_agent_chain` `_active_agent_tier`'ı BİLİNÇLİ
    reset etmez (overwrite disiplini; değer resolve->query arasında yaşamalı).
    Üretimde her istek kendi context'inde olduğu için sorun yok; ama pytest
    aynı OS-thread context'ini paylaşır — bir testin `get_agent_chain` çağrısı
    tier'ı arkada bırakır ve sonraki testler (ör. eski "tier yok == eski
    davranış" senaryoları) sessizce yanlış semantiğe düşer. Bu fixture,
    süreç-geneli mutable durum izolasyonu deseninin (rate bucket/cache) aynısını
    contextvar'lara uygular.
    """
    try:
        from agent_core.services import llm_gateway as gwmod
    except Exception:  # gateway yüklenemiyorsa test zaten kendi hatasını verir
        yield
        return
    vars_ = (
        gwmod._active_agent_tier,
        gwmod._active_chain_source,
        gwmod._active_task_hint,
        gwmod._active_agent_hint,
        gwmod._active_call_scope,
    )
    for var in vars_:
        var.set(None)
    yield
    for var in vars_:
        var.set(None)


@pytest.fixture(autouse=True)
def _clear_security_env_cache():
    """Clear lru_cache on _environment_secret_values between tests to prevent test pollution."""
    from agent_core.utils.security import _environment_secret_values
    yield
    _environment_secret_values.cache_clear()

@pytest.fixture(autouse=True)
def _clear_provider_catalog_cache():
    from agent_core.services.provider_manager import load_builtin_catalog
    yield
    load_builtin_catalog.cache_clear()


@pytest.fixture(autouse=True)
def _clear_agent_tiers_cache():
    """Clear lru_cache on _load_agent_tiers between tests to prevent test pollution."""
    try:
        from agent_core.services.llm_gateway import LLMGateway
        LLMGateway._load_agent_tiers.cache_clear()
    except Exception:
        pass
    yield
    try:
        from agent_core.services.llm_gateway import LLMGateway
        LLMGateway._load_agent_tiers.cache_clear()
    except Exception:
        pass
