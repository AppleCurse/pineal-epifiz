"""Herkese açık (token'sız) vitrin ve `consent` kapısı sözleşmeleri.

Neden bu test var (doğrulama 2026-11-23)
----------------------------------------
Dış inceleme + bağımsız doğrulama aynı bulguyu verdi: site açılır açılmaz
kırmızı ``HTTP 401`` + ``KASA DURUMU BİLİNMİYOR`` görünüyordu. Kök neden
``auth_middleware``'in **tüm** ``/api/*`` yollarına uygulanması ve hiçbir
herkese açık istisna olmamasıydı.

Bu dosya üç şeyi kilitler:

1. Public uçlar token İSTEMEZ (200), ama yalnızca GET/HEAD.
2. Public olmayan uçlar token'sız hâlâ 401 verir — yani allowlist bir
   **delik** değil, **dar bir istisna**.
3. Allowlist prefix eşleşmesiyle yazılmadı: path traversal denemeleri auth'suz
   geçemez.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.api import _is_public_get, app

_TOKEN = "public-showcase-test-token-32-characters"


def _cid() -> str:
    return f"pub_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def token_mode(monkeypatch):
    """Üretim benzeri: auth ZORUNLU. Public uçlar yine de açılmalı."""
    monkeypatch.setenv("PINEAL_TOKEN", _TOKEN)
    monkeypatch.setenv("PINEAL_ENV", "development")


def test_public_endpoints_do_not_require_token(token_mode):
    with TestClient(app) as client:
        listing = client.get("/api/public/demo-reports")
        assert listing.status_code == 200, listing.text
        body = listing.json()
        assert body["synthetic"] is True
        assert body["count"] >= 2, "en az 2 örnek rapor sözü verilmişti"

        notice = client.get("/api/public/notice")
        assert notice.status_code == 200
        assert notice.json()["jurisdiction"] == "TR"


def test_each_demo_report_loads_fully(token_mode):
    with TestClient(app) as client:
        listing = client.get("/api/public/demo-reports").json()
        for summary in listing["reports"]:
            detail = client.get(f"/api/public/demo-reports/{summary['id']}")
            assert detail.status_code == 200, summary["id"]
            report = detail.json()
            assert report["synthetic"] is True
            assert report["findings"], "örnek rapor bulgu taşımıyor"
            assert report["evidence_chain"], "örnek rapor kanıt zinciri taşımıyor"
            # Kanıt satırları gerçek şemayla aynı alan adlarını taşımalı.
            for ev in report["evidence_chain"]:
                assert {"agent", "evidence_type", "result", "epistemic_type"} <= set(ev)


def test_demo_reports_are_labelled_synthetic_everywhere(token_mode):
    with TestClient(app) as client:
        listing = client.get("/api/public/demo-reports").json()
        assert listing["synthetic"] is True
        assert listing["notice"]
        for summary in listing["reports"]:
            assert summary["synthetic"] is True
            assert summary["subject_label"].endswith("(SENTEİTK)")


def test_unknown_demo_report_is_404_not_a_leak(token_mode):
    with TestClient(app) as client:
        resp = client.get("/api/public/demo-reports/bu-rapor-yok")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DEMO_REPORT_NOT_FOUND"


def test_non_public_api_still_requires_token(token_mode):
    """Allowlist bir delik değil: korunan uçlar 401 vermeye devam eder."""
    with TestClient(app) as client:
        assert client.get("/api/telemetry", params={"client_id": _cid()}).status_code == 401
        assert client.get("/api/tasks").status_code == 401
        assert client.get("/api/vault/status").status_code == 401
        assert client.get("/api/report/status").status_code == 401


def test_public_allowlist_is_get_only(token_mode):
    """Aynı yola POST → 401. Yani allowlist 'yol' değil 'yol+yöntem' bazlı."""
    with TestClient(app) as client:
        assert client.post("/api/public/demo-reports").status_code == 401
        assert client.put("/api/public/notice").status_code == 401
        assert client.delete("/api/public/demo-reports/demo-01-acik-kaynak-tutarlilik").status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/public/demo-reports/../api/vault/status",
        "/api/public/demo-reports/..%2fapi%2fvault%2fstatus",
        "/api/public/demo-reports/%2e%2e/api/vault/status",
        "/api/public/demo-reports/./api/vault/status",
        "/api/public/demo-reports//api/vault/status",
        "/api/public/demo-reports/API/VAULT/STATUS",
    ],
)
def test_path_traversal_is_not_allowed_by_prefix(path, token_mode):
    """Prefix eşleşmesi auth bypass'a dönüşmesin — helper düzeyinde ölçülür."""
    assert _is_public_get(path, "GET") is False, path


def test_public_helper_rejects_non_get_methods():
    for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD"):
        # HEAD istisna: salt-okunur olduğu için izinli (gövde boş döner).
        expected = method == "HEAD"
        assert _is_public_get("/api/public/demo-reports", method) is expected, method


def test_public_helper_accepts_only_safe_slugs():
    assert _is_public_get("/api/public/demo-reports", "GET") is True
    assert _is_public_get("/api/public/notice", "GET") is True
    assert _is_public_get("/api/public/demo-reports/demo-01-acik-kaynak-tutarlilik", "GET") is True
    # Büyük harf / alt çizgi / boşluk / uzun girişler reddedilir.
    for bad in ("Demo-01", "demo_01", "demo 01", "a" * 200, "-basinda-tire"):
        assert _is_public_get(f"/api/public/demo-reports/{bad}", "GET") is False, bad
