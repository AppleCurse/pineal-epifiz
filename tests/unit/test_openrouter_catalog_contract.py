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
def _payload(price_in: float, price_out: float) -> bytes:
    return json.dumps({"data": [
        {"id": "google/gemini-3.7-flash",
         "pricing": {"prompt": str(price_in), "completion": str(price_out)}},
        {"id": "openai/gpt-5.6-sol-pro",
         "pricing": {"prompt": str(2.0 / 1_000_000), "completion": str(10.0 / 1_000_000)}},
    ]}).encode()


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
        lambda *a, **k: _Response(_payload(0.75 / 1_000_000, 3.75 / 1_000_000)),
    )
    failures, unverified = oc.verify_live_openrouter("key")
    assert failures == [] and unverified is None


def test_live_price_drift_is_a_failure_not_an_unverified_start(monkeypatch):
    monkeypatch.setattr(
        oc.urllib.request, "urlopen",
        lambda *a, **k: _Response(_payload(0.99 / 1_000_000, 3.75 / 1_000_000)),
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
        lambda *a, **k: _Response(_payload(0.99 / 1_000_000, 3.75 / 1_000_000)),
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
        return _Response(_payload(0.75 / 1_000_000, 3.75 / 1_000_000))

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
