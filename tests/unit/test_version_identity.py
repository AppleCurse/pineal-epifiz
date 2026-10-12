"""Sürüm kimliği sözleşmesi: ``VERSION`` dosyası TEK otoritedir.

[AUDIT 2026-10-07 · Madde 2] Denetimde sürüm kimliğinin depoya dağıldığı
tespit edildi — aynı ürün için beş farklı (ve çelişen) cevap vardı:

    VERSION                        -> 3.0.0-rc.2
    backend/api.py  (FastAPI adı)  -> "PINEAL-HERETIC v3.0.0-rc.1 API"  (BAYAT)
    package.json                   -> 3.0.0
    frontend/package.json          -> 0.0.0
    rust_core/Cargo.toml           -> 5.0.0
    rust_core/src-tauri/Cargo.toml -> 0.1.0
    rust_core/src-tauri/tauri.conf.json -> 5.0.0

Kök neden: sürüm, ihtiyaç duyulan her yere elle KOPYALANMIŞTI. Kopya
bayatlar — bunu engelleyecek hiçbir mekanizma yoktu.

Çözüm iki katmanlı:
  1. Çalışma zamanında sürüm gösteren yüzeyler (FastAPI adı, MCP
     ``server_version``) değeri artık ``agent_core.version`` üzerinden
     OKUR; kopyalamaz.
  2. Okuyamayan yerler (npm / Cargo / Tauri manifestoları, frontend sabiti)
     bu dosyadaki testlerle ``VERSION``'a EŞİT OLMAYA ZORLANIR.

Ek olarak iki "araç kırılması" da korunur:
  * npm lockfile'ları package.json ile senkron olmalı (yoksa ``npm ci`` kırılır)
  * Cargo.lock, Cargo.toml ile senkron olmalı   (yoksa ``cargo test --locked`` kırılır)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = REPO_ROOT / "VERSION"

#: SemVer 2.0.0 (opsiyonel ön-sürüm ve derleme meta verisi ile).
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

CANONICAL_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()


# ─────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────


def _cargo_package_version(cargo_toml: Path) -> str:
    """``[package]`` bölümündeki ``version`` alanını oku.

    Bilinçli olarak TOML ayrıştırıcı yerine düzenli ifade: bu testin
    çalışması için ek bağımlılık (tomli) veya Python >= 3.11 (tomllib)
    şartı getirmek istemedik. Yalnızca İLK ``version =`` satırı okunur;
    Cargo.toml'da ``[package]`` her zaman baştadır.
    """
    for line in cargo_toml.read_text(encoding="utf-8").splitlines():
        match = re.match(r'^version\s*=\s*"([^"]+)"\s*$', line.strip())
        if match:
            return match.group(1)
    raise AssertionError(f"{cargo_toml}: [package] version bulunamadı")


# ─────────────────────────────────────────────────────────────────────────
# 1) Kaynak: VERSION dosyası
# ─────────────────────────────────────────────────────────────────────────


def test_version_file_exists_and_is_non_empty():
    assert VERSION_FILE.is_file(), "kök VERSION dosyası yok: sürüm otoritesi kayıp"
    assert CANONICAL_VERSION, "VERSION dosyası boş"


def test_version_file_is_valid_semver():
    """Sürüm, hem npm hem Cargo hem PEP 440 tarafından anlaşılır biçimde olmalı."""
    assert SEMVER_RE.match(CANONICAL_VERSION), (
        f"VERSION dosyası geçerli bir SemVer değil: {CANONICAL_VERSION!r}"
    )


def test_version_module_reads_the_same_file():
    """``agent_core.version`` gerçekten kök VERSION dosyasını okuyor mu?"""
    from agent_core.version import VERSION as module_version
    from agent_core.version import read_version, version_file_path

    assert version_file_path == VERSION_FILE
    assert module_version == CANONICAL_VERSION
    assert read_version() == CANONICAL_VERSION


def test_mcp_server_version_derives_from_single_source():
    """MCP sunucusu ile FastAPI aynı kaynağı paylaşmak ZORUNDA."""
    from agent_core.mcp.server import server_version

    assert server_version() == CANONICAL_VERSION, (
        "MCP server_version kök VERSION dosyasından sapmış — sürüm kimliği "
        "yeniden çatallanıyor"
    )


# ─────────────────────────────────────────────────────────────────────────
# 2) Çalışma zamanı yüzeyleri
# ─────────────────────────────────────────────────────────────────────────


def test_fastapi_title_uses_canonical_version():
    """[AUDIT] FastAPI adında bayat ``v3.0.0-rc.1`` yazılıydı (elle kopya)."""
    from backend.api import app

    expected = f"PINEAL-HERETIC v{CANONICAL_VERSION} API"
    assert app.title == expected, (
        f"FastAPI adı VERSION dosyasıyla uyuşmuyor: {app.title!r} != {expected!r}. "
        "Sürümü elle yazmayın; agent_core.version.VERSION kullanın."
    )
    assert "rc.1" not in app.title, "bayat rc.1 sürüm etiketi geri geldi"


def test_openapi_document_reports_canonical_version():
    """Müşterilerin gördüğü OpenAPI şeması da aynı sürümü söylemeli."""
    from backend.api import app

    assert app.openapi()["info"]["title"] == f"PINEAL-HERETIC v{CANONICAL_VERSION} API"


# ─────────────────────────────────────────────────────────────────────────
# 3) npm manifestoları (+ lockfile senkronizasyonu = `npm ci` koruması)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "manifest",
    ["package.json", "frontend/package.json"],
)
def test_npm_manifest_tracks_canonical_version(manifest: str):
    data = json.loads((REPO_ROOT / manifest).read_text(encoding="utf-8"))
    assert data["version"] == CANONICAL_VERSION, (
        f"{manifest} sürümü kök VERSION'dan sapmış: {data['version']!r} != {CANONICAL_VERSION!r}"
    )


@pytest.mark.parametrize(
    "package_dir",
    [".", "frontend"],
)
def test_npm_lockfile_is_in_sync_with_manifest(package_dir: str):
    """Lockfile senkron değilse ``npm ci`` kırılır — sessiz bir CI tuzağı.

    Sürümü tek başına güncelleyip lockfile'ı unutmak tam olarak bu hatayı
    üretir; bu yüzden ikisi birlikte kilitlenir.
    """
    base = REPO_ROOT / package_dir
    manifest = json.loads((base / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((base / "package-lock.json").read_text(encoding="utf-8"))

    assert lock["name"] == manifest["name"], f"{package_dir}: lockfile adı uyuşmuyor"
    assert lock["version"] == manifest["version"], (
        f"{package_dir}/package-lock.json üst sürümü bayat: {lock['version']!r} != {manifest['version']!r}"
    )
    assert lock["packages"][""]["version"] == manifest["version"], (
        f"{package_dir}/package-lock.json kök paket girdisi bayat: "
        f"{lock['packages']['']['version']!r} != {manifest['version']!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 4) Rust / Tauri manifestoları (+ Cargo.lock = `cargo test --locked` koruması)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "manifest",
    [
        "rust_core/Cargo.toml",
        "rust_core/src-tauri/Cargo.toml",
    ],
)
def test_cargo_manifest_tracks_canonical_version(manifest: str):
    version = _cargo_package_version(REPO_ROOT / manifest)
    assert version == CANONICAL_VERSION, (
        f"{manifest} sürümü kök VERSION'dan sapmış: {version!r} != {CANONICAL_VERSION!r}"
    )


def test_tauri_conf_tracks_canonical_version():
    conf = json.loads((REPO_ROOT / "rust_core/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    assert conf["version"] == CANONICAL_VERSION, (
        f"tauri.conf.json sürümü sapmış: {conf['version']!r} != {CANONICAL_VERSION!r}"
    )


def test_cargo_lock_is_in_sync_with_manifest():
    """CI ``cargo test --locked`` koşar: Cargo.toml değişip lock değişmezse kırılır."""
    manifest_version = _cargo_package_version(REPO_ROOT / "rust_core/Cargo.toml")
    lock_text = (REPO_ROOT / "rust_core/Cargo.lock").read_text(encoding="utf-8")
    match = re.search(
        r'^name = "pineal_heretic_core"\nversion = "([^"]+)"$',
        lock_text,
        flags=re.M,
    )
    assert match, "Cargo.lock içinde pineal_heretic_core girdisi bulunamadı"
    assert match.group(1) == manifest_version, (
        f"Cargo.lock bayat: {match.group(1)!r} != Cargo.toml {manifest_version!r} "
        "(cargo test --locked kırılır)"
    )


# ─────────────────────────────────────────────────────────────────────────
# 5) Frontend sabiti
# ─────────────────────────────────────────────────────────────────────────


def test_frontend_version_constant_tracks_canonical_version():
    """``main.ts`` içinde eskiden 'v5.0' yazılıydı — derlemeye gömülü bayat kimlik."""
    source = (REPO_ROOT / "frontend/src/lib/version.ts").read_text(encoding="utf-8")
    match = re.search(r"export const APP_VERSION = '([^']+)'", source)
    assert match, "frontend/src/lib/version.ts: APP_VERSION bulunamadı"
    assert match.group(1) == CANONICAL_VERSION, (
        f"frontend APP_VERSION sapmış: {match.group(1)!r} != {CANONICAL_VERSION!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 6) Sürüm notu / yayın manifestosu
# ─────────────────────────────────────────────────────────────────────────


def test_release_manifest_exists_and_matches_version():
    manifest_path = REPO_ROOT / "release" / f"{CANONICAL_VERSION}.json"
    assert manifest_path.is_file(), (
        f"yayın manifestosu yok: release/{CANONICAL_VERSION}.json"
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["version"] == CANONICAL_VERSION


# ─────────────────────────────────────────────────────────────────────────
# 7) Bayat, elle yazılmış sürüm dizgeleri geri sızmasın
# ─────────────────────────────────────────────────────────────────────────

_GUARDED_FILES = [
    "backend/api.py",
    "frontend/src/main.ts",
    "frontend/src/lib/version.ts",
    "frontend/src/lib/tauriBridge.ts",
    "rust_core/src-tauri/tauri.conf.json",
    "rust_core/src-tauri/Cargo.toml",
    "rust_core/Cargo.toml",
    "package.json",
    "frontend/package.json",
]

#: "v5.0"/"5.0.0" ve "rc.1" — denetimde bulunan bayat kimlikler.
_STALE_LITERAL_RE = re.compile(r"\b5\.0\.0\b|\bv5\.0\b|\brc\.1\b")
_VERSIONISH_LINE_RE = re.compile(r"(?i)version|signature|PINEAL-HERETIC v")


@pytest.mark.parametrize("relative_path", _GUARDED_FILES)
def test_no_stale_hardcoded_version_literals(relative_path: str):
    """Sürümle ilgili satırlarda bayat (5.0.0 / v5.0 / rc.1) dizge kalmasın."""
    path = REPO_ROOT / relative_path
    offenders = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _VERSIONISH_LINE_RE.search(line) and _STALE_LITERAL_RE.search(line):
            offenders.append(f"{relative_path}:{lineno}: {line.strip()[:120]}")
    assert not offenders, "bayat sürüm dizgeleri geri sızmış:\n" + "\n".join(offenders)
