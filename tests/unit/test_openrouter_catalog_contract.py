"""`scripts/verify_openrouter_catalog.py` kontratının kilidi.

NEDEN BU DOSYA VAR: CI'daki 11. adım 2026-10-14'te main'de düştü ve düşüşün
SEBEBİ hiçbir yerde okunamadı — betik hata satırlarını stderr'e yazıyordu, adım
yalnız stdout'u yakalıyordu; Actions logları da api.github.com'dan okunamıyor.
Üstelik bu betiğin HİÇ testi yoktu: yalnız CI'da koşuyordu, yani kırıldığında
yerelde kimse görmedi (bu deponun kendi kuralı: kilitlenmemiş bekçi yanlış
yeşil üretebilir, o zaman yokluğundan daha tehlikelidir).

Kilitlenen hükümler:

1. YEREL KONTRAT GERÇEKTEN ISIRIYOR — pinli fiyat kayarsa / model düşerse /
   ``:free`` rotası $0'dan farklıysa kırmızı.
2. ÜÇ HÜKÜM AYRI — ``FAIL`` (kayma), ``UNVERIFIED`` (ulaşılamadı: doğrulama
   YAPILMADI), ``SKIP`` (anahtar yok). Kesinti asla "geçti" diye sunulmaz;
   "canlı doğrulandı" yalnız gerçekten doğrulandıysa yazılır.
3. GEÇİCİ ARIZA YENİDEN DENENİR — ilk deneme düşerse ikinci denemede başarı
   yeterlidir; tek DNS sarsıntısı main'i kırmaz.
4. CI ADIMI SEBEBİ YAYINLAR — stderr yakalanır, kırılırsa ``::error``
   annotation'ı çıkar (bir daha kör kalmayalım).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_openrouter_catalog.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# `scripts/` paket değil; bekçi dosyadan yüklenir (test_audit_regression ile aynı desen).
_spec = importlib.util.spec_from_file_location("verify_openrouter_catalog", SCRIPT)
assert _spec and _spec.loader
oc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = oc  # dataclass/annotation çözümü için gerekli
_spec.loader.exec_module(oc)

FREE_KEY = "OPENROUTER_API_KEY"


def _catalog(**overrides: object) -> dict:
    """Gerçek katalogu taban alıp istenen alanı bozar (uydurma katalog yazmayız)."""
    catalog = json.loads(oc.CATALOG_PATH.read_text(encoding="utf-8"))
    for dotted, value in overrides.items():
        provider_id, _, model_id = dotted.partition("::")
        for provider in catalog["providers"]:
            if provider["id"] != provider_id:
                continue
            if model_id:
                for model in provider["models"]:
                    if model["id"] == model_id:
                        model.update(value)  # type: ignore[arg-type]
            else:
                provider.update(value)  # type: ignore[arg-type]
    return catalog


@pytest.fixture()
def isolated_catalog(tmp_path, monkeypatch):
    def _install(catalog: dict) -> None:
        path = tmp_path / "provider_catalog.json"
        path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(oc, "CATALOG_PATH", path)

    return _install


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Testler asla gerçekten beklemez; yeniden deneme uykusu sahtelenir."""
    monkeypatch.setattr(oc, "_live_sleep", lambda _seconds: None)


# ─────────────────────────────────────────────────────────────────────────────
# 1) YEREL KONTRAT GERÇEKTEN ISIRIYOR MU
# ─────────────────────────────────────────────────────────────────────────────
def test_committed_catalog_passes_the_local_contract():
    """Bugünün gerçeği: commit'li katalog pinlerle birebir."""
    assert oc.verify_local_catalog() == []


def test_local_contract_bites_on_price_drift(isolated_catalog):
    """Fiyat kayması sessizce geçemez — pinin anlamı budur."""
    pinned = oc.REQUIRED_OPENROUTTER["google/gemini-3.7-flash"]
    broken = _catalog(**{
        "openrouter::google/gemini-3.7-flash": {
            "pricing": {"input_per_million_usd": pinned[0] + 0.01,
                        "output_per_million_usd": pinned[1]}
        }
    })
    isolated_catalog(broken)
    failures = oc.verify_local_catalog()
    assert any("price drift" in f for f in failures), failures


def test_local_contract_bites_on_missing_model(isolated_catalog):
    catalog = _catalog()
    for provider in catalog["providers"]:
        if provider["id"] == "openrouter":
            provider["models"] = [
                m for m in provider["models"] if m["id"] != "google/gemini-3.7-flash"
            ]
    isolated_catalog(catalog)
    failures = oc.verify_local_catalog()
    assert any("missing from local catalog" in f for f in failures), failures


def test_free_route_can_never_be_priced_above_zero(isolated_catalog):
    """`:free` etiketi fiyata değil, kontrata dayanır: $0 değilse kırmızı."""
    free_id = sorted(oc.REQUIRED_NOUS_FREE)[0]
    free_model_id = free_id.split("/")[-1]
    catalog = _catalog()
    for provider in catalog["providers"]:
        if provider["id"] == "nous-research":
            for model in provider["models"]:
                if model["id"] == free_model_id or model["id"].endswith(free_model_id):
                    model["pricing"] = {"input_per_million_usd": 0.5,
                                        "output_per_million_usd": 0.5}
    isolated_catalog(catalog)
    failures = oc.verify_local_catalog()
    assert any("free" in f for f in failures), failures


def test_forbidden_free_route_stays_out_of_the_catalog(isolated_catalog):
    """Denetimle düşürülen ölü kayıt geri sızamaz."""
    catalog = _catalog()
    for provider in catalog["providers"]:
        if provider["id"] == "nous-research":
            provider["models"].append({
                "id": "google/gemma-3-27b-it:free",
                "pricing": {"input_per_million_usd": 0.0, "output_per_million_usd": 0.0},
            })
    isolated_catalog(catalog)
    failures = oc.verify_local_catalog()
    assert any("gemma-3-27b-it:free" in f for f in failures), failures


# ─────────────────────────────────────────────────────────────────────────────
# 2) ÜÇ HÜKÜM AYRI MI (fail / unverified / skip)
# ─────────────────────────────────────────────────────────────────────────────
def _payload(overrides: dict[str, tuple[float, float]] | None = None) -> bytes:
    """Canlı katalog yanıtını PİNLERDEN türetir.

    Sabit iki model yazmak yerine pin kümesi gezilir: kapsam büyüdüğünde
    (2026-10-14'te 2 -> 5 oldu) test kendiliğinden uyumlu kalır; aksi hâlde
    "missing from live catalog" yüzünden yanlış kırmızı üretirdi.
    """
    overrides = overrides or {}
    data = []
    for model_id, (pin_in, pin_out) in oc.REQUIRED_OPENROUTTER.items():
        live_in, live_out = overrides.get(model_id, (pin_in, pin_out))
        data.append({
            "id": model_id,
            "pricing": {"prompt": str(live_in / 1_000_000), "completion": str(live_out / 1_000_000)},
        })
    return json.dumps({"data": data}).encode()


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def test_live_match_yields_no_failures_and_no_unverified(monkeypatch):
    monkeypatch.setattr(
        oc.urllib.request, "urlopen",
        lambda *a, **k: _Response(_payload()),
    )
    failures, unverified = oc.verify_live_openrouter("key")
    assert failures == [] and unverified is None


def test_live_price_drift_is_a_failure_not_an_unverified_start(monkeypatch):
    monkeypatch.setattr(
        oc.urllib.request, "urlopen",
        lambda *a, **k: _Response(_payload({"google/gemini-3.7-flash": (0.99, 3.75)})),
    )
    failures, unverified = oc.verify_live_openrouter("key")
    assert unverified is None, "katalog okunduysa 'doğrulanamadı' DENEMEZ"
    assert any("live input price" in f for f in failures), failures


def test_unreachable_service_is_unverified_and_never_verified(monkeypatch, capsys):
    def _boom(*_a, **_k):
        raise urllib.error.URLError("TLS/SSL connection has been closed")

    monkeypatch.setattr(oc.urllib.request, "urlopen", _boom)
    monkeypatch.setenv(FREE_KEY, "key")
    rc = oc.main()
    out, err = capsys.readouterr()
    assert rc == 0, "ağ kesintisi main'i kırmaz — ama doğrulandı da DEMEZ"
    assert "UNVERIFIED: live OpenRouter unreachable" in out, out
    assert "live OpenRouter models verified" not in out, (
        "doğrulanamayan bir koşu 'doğrulandı' diye sunulamaz"
    )
    assert "FAIL:" not in err, "kesinti, kayma hükmü değildir"


def test_missing_key_says_skip_without_pretending(monkeypatch, capsys):
    monkeypatch.delenv(FREE_KEY, raising=False)
    rc = oc.main()
    out, _ = capsys.readouterr()
    assert rc == 0
    assert "SKIP: live OpenRouter check" in out
    assert "live OpenRouter models verified" not in out


def test_failures_are_printed_where_ci_can_read_them(monkeypatch, capsys):
    """Hata satırı stdout'ta DE olmalı: CI çıktıyı oradan toplar.

    (2026-10-14 körlüğü: satırlar yalnız stderr'deydi, adım stdout'u okuyordu.)
    """
    monkeypatch.setenv(FREE_KEY, "key")
    monkeypatch.setattr(
        oc.urllib.request, "urlopen",
        lambda *a, **k: _Response(_payload({"google/gemini-3.7-flash": (0.99, 3.75)})),
    )
    rc = oc.main()
    out, err = capsys.readouterr()
    assert rc == 1
    assert "FAIL:" in err and "live input price" in err


# ─────────────────────────────────────────────────────────────────────────────
# 3) GEÇİCİ ARIZA YENİDEN DENENİR
# ─────────────────────────────────────────────────────────────────────────────
def test_transient_failure_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def _flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("geçici DNS sarsıntısı")
        return _Response(_payload())

    monkeypatch.setattr(oc.urllib.request, "urlopen", _flaky)
    failures, unverified = oc.verify_live_openrouter("key")
    assert (failures, unverified) == ([], None)
    assert calls["n"] == 2, "tek sarsıntıda pes edilmez"


def test_retries_are_bounded_and_report_the_last_error(monkeypatch):
    calls = {"n": 0}

    def _always_down(*_a, **_k):
        calls["n"] += 1
        raise urllib.error.URLError("kapalı")

    monkeypatch.setattr(oc.urllib.request, "urlopen", _always_down)
    failures, unverified = oc.verify_live_openrouter("key")
    assert failures == []
    assert unverified is not None and "unreachable" in unverified
    assert calls["n"] == oc._LIVE_MAX_ATTEMPTS, "deneme sayısı sabit ve sınırlı"


# ─────────────────────────────────────────────────────────────────────────────
# 5) KOPYALAR ARASI TUTARLILIK (kök onarım)
# ─────────────────────────────────────────────────────────────────────────────
def test_pinned_prices_agree_in_every_copy():
    """Aynı fiyat DÖRT yerde yaşıyor; dördü de aynı olmak ZORUNDA.

    Neden bu test var: 2026-10-14'te canlı kontrol, sol-pro'nun fiyatının
    $2/$10'dan $4/$20'ye çıktığını gösterdi. Fiyat şu dört kopyada duruyordu ve
    aralarındaki tutarlılığı denetleyen HİÇBİR şey yoktu:

      1. ``scripts/verify_openrouter_catalog.py`` → ``REQUIRED_OPENROUTTER`` (pin)
      2. ``config/provider_catalog.json`` → ``openrouter/<id>``
      3. ``agent_core/services/llm_gateway.py`` → ``LLMGateway.MODEL_PRICING``
         (harcama sayacı/spend cap BUNA bakar)
      4. ``agent_core/services/final_routing_policy.py`` → ``ROUTES[<id>@openrouter]``

    Kopyalardan biri güncellenip diğeri unutulursa harcama sayacı sessizce
    yanlış sayar (ölçülen: sol-pro'da tam 2×). Bu kilit o sınıfı kapatır.

    Kapsam dürüstçe: yalnız CANLI KONTROL EDİLEN pinli küme için eşitlik
    aranır (nous-research gibi kanal-indirimli fiyatlar bilinçli olarak farklı
    kanalları gösterir ve bu testin dışındadır).
    """
    from agent_core.services.final_routing_policy import ROUTES
    from agent_core.services.llm_gateway import LLMGateway

    catalog = json.loads(oc.CATALOG_PATH.read_text(encoding="utf-8"))
    katalog = {}
    for provider in catalog["providers"]:
        if provider["id"] != "openrouter":
            continue
        for model in provider.get("models", []):
            pricing = model.get("pricing") or {}
            katalog[model["id"]] = (
                pricing.get("input_per_million_usd"),
                pricing.get("output_per_million_usd"),
            )

    sorunlar: list[str] = []
    for model_id, pin in oc.REQUIRED_OPENROUTTER.items():
        if katalog.get(model_id) != pin:
            sorunlar.append(f"katalog[openrouter/{model_id}]={katalog.get(model_id)} != pin{tuple(pin)}")
        gateway = LLMGateway.MODEL_PRICING.get(model_id)
        if gateway is None or (gateway["in"], gateway["out"]) != tuple(pin):
            sorunlar.append(f"MODEL_PRICING[{model_id}]={gateway} != pin{tuple(pin)}")
        route = ROUTES.get(f"{model_id}@openrouter")
        if route is not None and (route.input_per_million_usd, route.output_per_million_usd) != tuple(pin):
            sorunlar.append(
                f"ROUTES[{model_id}@openrouter]="
                f"({route.input_per_million_usd}, {route.output_per_million_usd}) != pin{tuple(pin)}"
            )
    assert not sorunlar, "fiyat kopyaları ayrışmış:\n  " + "\n  ".join(sorunlar)


def test_pinned_live_coverage_includes_the_spend_cap_models():
    """Doğrulama kapsamı boşaltılamaz: harcama sayacının taşıdığı modeller pinli.

    ``anthropic/claude-sonnet-5`` · ``deepseek/deepseek-v4-flash`` ·
    ``deepseek/deepseek-v4-pro`` harcama tablosunda fiyatlıydı ama hiçbir canlı
    kontrol yoktu — yani "inanç" olarak duruyorlardı. Bu test, kapsamın sessizce
    daraltılmasını engeller (ölçülen inanç ≠ doğrulama).
    """
    from agent_core.services.llm_gateway import LLMGateway

    beklenen = {
        "anthropic/claude-sonnet-5",
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-pro",
        "upstage/solar-pro4",
        "inclusionai/ling-3.0-flash",
        "z-ai/glm-5.2",
        "x-ai/grok-4.6",
    }
    assert beklenen <= set(oc.REQUIRED_OPENROUTTER), (
        "bu modeller harcama sayacında fiyatlı ama canlı kontrolden çıkarılmış"
    )
    for model_id in beklenen:
        assert model_id in LLMGateway.MODEL_PRICING, model_id


def test_catalog_openrouter_pricing_is_fully_pinned():
    """Katalogun `openrouter` bölümündeki HER fiyatlı kayıt pinli olmalı.

    Katalog "bu modeli OR bize şu fiyattan verir" diye İDDİA eder; iddia ya
    doğrulanır ya kaldırılır. Ara durum (beyan var, kontrol yok) yasak —
    2026-10-14'te kapsam dışı kalan dört kayıt tam bu ara durumdaydı.
    """
    catalog = json.loads(oc.CATALOG_PATH.read_text(encoding="utf-8"))
    for provider in catalog["providers"]:
        if provider["id"] != "openrouter":
            continue
        for model in provider.get("models", []):
            pricing = model.get("pricing") or {}
            if not pricing:
                continue  # fiyat beyanı yoksa doğrulanacak iddia da yok
            assert model["id"] in oc.REQUIRED_OPENROUTTER, (
                f"katalogda fiyatlı ama canlı kontrolde yok: {model['id']}"
            )


def test_uncovered_priced_models_are_named_not_silent():
    """Ücretlendirilen ama doğrulanamayan modeller ADIYLA kayıtlı olmalı.

    Bunlar harcama sayacında fiyatlı (`MODEL_PRICING`) ama katalogda beyan
    edilmedikleri için canlı kontrole alınamıyorlar. Sessiz kalmak yerine
    isimleri sabitlenir: yeni bir "fiyatlı ama doğrulanamaz" model eklenirse
    bu test kırmızı olur ve karar (katalogda yetkilendir → pinle, ya da kaydı
    düşür) zorunlu hâle gelir.
    """
    from agent_core.services.llm_gateway import LLMGateway

    catalog = json.loads(oc.CATALOG_PATH.read_text(encoding="utf-8"))
    katalogdaki_or = set()
    for provider in catalog["providers"]:
        if provider["id"] == "openrouter":
            katalogdaki_or |= {m["id"] for m in provider.get("models", [])}

    ucretli = {
        model_id
        for model_id, rates in LLMGateway.MODEL_PRICING.items()
        if (rates["in"] or rates["out"])  # $0 hatları (pineal-*, :free) kapsam dışı
    }
    pinli = set(oc.REQUIRED_OPENROUTTER)
    kapsam_disi = ucretli - pinli
    assert kapsam_disi == set(oc.UNCOVERED_PRICED_MODELS), (
        f"kapsam dışı ücretli model kümesi değişti: {sorted(kapsam_disi)} — "
        "her yeni üye ya katalogda yetkilendirilip pinlenmeli ya da buradaki "
        "adlandırılmış boşluk listesine gerekçesiyle eklenmeli"
    )
    for model_id in oc.UNCOVERED_PRICED_MODELS:
        assert model_id not in katalogdaki_or, (
            f"{model_id} artık katalogda — pini eklenip kapsam genişletilmeli"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4) CI ADIMI SEBEBİ YAYINLIYOR MU (bir daha kör kalmayalım)
# ─────────────────────────────────────────────────────────────────────────────
def test_ci_step_captures_stderr_and_publishes_the_reason():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    step = workflow.split("Verify provider catalog contract", 1)[1].split("- name:", 1)[0]
    assert "verify_openrouter_catalog.py 2>&1" in step, (
        "stderr yakalanmazsa düşüşün sebebi yine görünmez"
    )
    assert "::error title=catalog-contract" in step, (
        "kırılma sebebi annotation olarak yayınlanmalı (api.github.com'dan okunur)"
    )
    assert "::warning title=catalog-unverified" in step, (
        "doğrulanamayan koşu yüksek sesle işaretlenmeli"
    )
