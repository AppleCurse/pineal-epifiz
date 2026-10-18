"""E-GÖZ1-3 — tek sırt (egress) omurgası: davranış + statik ölçümler.

Kurallar:

* ``agent_core`` içinde ``httpx.AsyncClient`` inşası **yalnızca**
  ``agent_core/capabilities/egress.py`` dosyasındadır.
* Satır başı ``import httpx`` yalnızca egress'tedir; diğer dosyalar
  ``httpx`` adını egress üzerinden yeniden ihracat alır.
* ``open_client`` her denemeyi ``ContextVar`` üzerinden kaydeder
  (başarısız deneme de zincirde görünür kalır).
* Kasa kapısı: üretimde zorunlu amaçlar (osint/search/sensor/scraper)
  kilitliyse ``VaultLockedError`` — ama açık deneme KAYDI BIRAKMAZ.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agent_core.capabilities import egress
from agent_core.scraper.vault_gate import (
    VaultLockedError,
    get_vault_status,
    mark_vault_egress_authorized,
)

ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────────────
# Statik: tek sırt
# ─────────────────────────────────────────────────────────────────────────────


def _clear_boundary() -> None:
    """Sınır yetkisini sıfırla (işaret None = atanmadı)."""
    from agent_core.scraper import vault_gate as vg

    vg._auth_ctx.set(None)


def _agent_core_py_files() -> list[Path]:
    return sorted((ROOT / "agent_core").rglob("*.py"))


def test_no_construction_outside_egress() -> None:
    offenders: list[str] = []
    for path in _agent_core_py_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "agent_core/capabilities/egress.py":
            continue
        body = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(^|[^.\w])httpx\.AsyncClient\(", body, re.M):
            ln = body[: m.start()].count("\n") + 1
            offenders.append(f"{rel}:{ln}")
    assert offenders == [], f"omurga dışı httpx.AsyncClient inşası: {offenders}"


def test_no_line_start_httpx_import_outside_egress() -> None:
    offenders: list[str] = []
    for path in _agent_core_py_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "agent_core/capabilities/egress.py":
            continue
        body = path.read_text(encoding="utf-8")
        if re.search(r"^\s*import httpx\s*(#.*)?$", body, re.M):
            offenders.append(rel)
    assert offenders == [], f"omurga dışı satır başı import httpx: {offenders}"


def test_egress_is_the_only_constructor_and_reexports() -> None:
    src = (ROOT / "agent_core/capabilities/egress.py").read_text(encoding="utf-8")
    assert "def open_client(" in src
    assert re.search(r"^import httpx\s", src, re.M)
    # Kullanıcı dosyaları egress üzerinden httpx adını alabilmeli.
    security = (ROOT / "agent_core/utils/security.py").read_text(encoding="utf-8")
    assert "from agent_core.capabilities.egress import httpx" in security


# ─────────────────────────────────────────────────────────────────────────────
# Davranış: deneme kaydı + kasa kapısı
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_context(monkeypatch):
    """Her test öncesi/sonrası sınır yetkisi ve deneme kayıtları sıfırlanır."""
    from agent_core.scraper import vault_gate as vg

    prior = vg._auth_ctx.get()
    egress._reset_for_tests()
    yield
    vg._auth_ctx.set(prior)
    egress._reset_for_tests()


async def test_open_client_records_attempt_and_drain_clears() -> None:
    async with egress.open_client(purpose="llm", target="https://llm.local/v1") as c:
        assert c is not None
    attempts = egress.egress_attempts()
    assert attempts, "açık deneme kaydı bırakmalı"
    assert attempts[-1].purpose == "llm"
    assert attempts[-1].target == "https://llm.local/…"
    drained = egress.drain_egress_attempts()
    assert len(drained) == len(attempts)
    assert drained[-1]["purpose"] == "llm"
    assert egress.egress_attempts() == ()


async def test_egress_target_records_destination_without_url_secrets() -> None:
    secret_url = "https://user:password@llm.local/v1/chat?api_key=top-secret#fragment"
    async with egress.open_client(purpose="llm", target=secret_url) as c:
        assert c is not None
    target = egress.egress_attempts()[-1].target
    assert target == "https://llm.local/…"
    assert all(secret not in target for secret in ("user", "password", "top-secret", "fragment"))


async def test_production_locked_vault_refuses_osint_without_record(
    monkeypatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault.json"
    vault.write_text(json.dumps({"pineal": {"vault": {"api_key": "changeme-123"}}}))
    monkeypatch.setenv("PINEAL_VAULT_FILE", str(vault))
    monkeypatch.setenv("PINEAL_ENV", "production")
    _clear_boundary()
    egress._reset_for_tests()

    with pytest.raises(VaultLockedError):
        async with egress.open_client(purpose="search", target="https://x") as c:
            _ = c
    assert egress.egress_attempts() == (), "reddedilen istek kayıt bırakmamalı"


async def test_production_open_vault_allows_and_records(
    monkeypatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault.json"
    vault.write_text(
        json.dumps({"pineal": {"vault": {"api_key": "sk-real-key-123456"}}})
    )
    monkeypatch.setenv("PINEAL_VAULT_FILE", str(vault))
    monkeypatch.setenv("PINEAL_ENV", "production")
    _clear_boundary()
    egress._reset_for_tests()

    status = get_vault_status()
    assert status["open"] is True and status["source"] == "file_vault"

    async with egress.open_client(purpose="osint") as c:
        assert c is not None
    assert egress.egress_attempts()[-1].purpose == "osint"


async def test_production_non_enforced_purpose_passes_without_vault(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    monkeypatch.setenv("PINEAL_ENV", "production")
    _clear_boundary()
    egress._reset_for_tests()

    async with egress.open_client(purpose="llm", target="http://127.0.0.1:11434") as c:
        assert c is not None
    assert egress.egress_attempts()[-1].purpose == "llm"


async def test_boundary_authorization_propagates(monkeypatch) -> None:
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    monkeypatch.setenv("PINEAL_ENV", "production")
    egress._reset_for_tests()
    mark_vault_egress_authorized()  # API sınırı kapıyı açtı
    async with egress.open_client(purpose="scraper") as c:
        assert c is not None
    assert egress.egress_attempts()[-1].purpose == "scraper"


def test_strict_mode_cli_semantics(monkeypatch) -> None:
    """CLI (strict): dosya kasası yoksa geliştirme bile olsa kilit."""
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    monkeypatch.delenv("PINEAL_ENV", raising=False)
    _clear_boundary()
    status = get_vault_status(strict=True)
    assert status["locked"] is True
    assert status["source"] == "strict_no_authorization"
