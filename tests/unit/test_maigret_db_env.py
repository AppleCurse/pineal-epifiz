"""FAZ A · A8 — tarayıcı tazelenmiş DB'yi GERÇEKTEN kullanır ve raporlar.

Kilitlenen iddialar:
    * ``PINEAL_MAIGRET_DB`` doluysa tarama o dosyadan koşar; sonuç
      ``db_source`` (dosya yolu) + ``db_sites`` (site sayısı) taşır.
    * Boşsa paketlenmiş DB kullanılır; ``db_source`` ``bundled:`` öneki taşır.
    * Bozuk/boş tazelenmiş dosya SESSİZCE paketlenmiş listeye düşmez:
      ``db_unavailable`` (fail-closed dürüstlük).
    * Kaynak anahtarlı önbellek: env değişince bayat DB ile taranmaz.
"""

from __future__ import annotations

import json

import pytest

from agent_core.services import maigret_scanner


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("ENABLE_MAIGRET", "true")
    monkeypatch.delenv("PINEAL_MAIGRET_DB", raising=False)
    maigret_scanner._reset_site_dict_cache()  # her test tazeye bakar
    yield
    maigret_scanner._reset_site_dict_cache()


def _write_db(path, sites, nested=False):
    payload = {"sites": sites, "engines": {}} if nested else sites
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fake_scan_factory():
    """Kütüphane taramasını taklit eder: tüm siteler AVAILABLE döner."""
    from maigret.result import MaigretCheckStatus

    class _R:
        status = MaigretCheckStatus.AVAILABLE
        url_user = ""

    async def _fake_library(username, site_dict, timeout):
        return {name: _R() for name in site_dict}

    return _fake_library


class TestRefreshedDbEnv:
    @pytest.mark.asyncio
    async def test_refreshed_db_used_and_reported(self, monkeypatch, tmp_path):
        db = _write_db(
            tmp_path / "refreshed.json",
            {
                "A": {"url": "https://a.example.com/{username}"},
                "B": {"url": "https://b.example.com/{username}"},
                "C": {"url": "https://c.example.com/{username}"},
            },
        )
        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(db))
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan_factory())

        res = await maigret_scanner.scan_username("soxoj", limit=3)
        assert res.available is True
        assert res.db_source == f"file:{db}"
        assert res.db_sites == 3
        assert res.scanned_count == 3

    @pytest.mark.asyncio
    async def test_nested_shape_supported(self, monkeypatch, tmp_path):
        db = _write_db(
            tmp_path / "nested.json",
            {"X": {"url": "https://x.example.com/{username}"}},
            nested=True,
        )
        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(db))
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan_factory())

        res = await maigret_scanner.scan_username("soxoj", limit=1)
        assert res.db_source == f"file:{db}"
        assert res.db_sites == 1

    @pytest.mark.asyncio
    async def test_broken_refreshed_db_never_falls_back_silently(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"sites": {}}), encoding="utf-8")
        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(bad))

        res = await maigret_scanner.scan_username("soxoj")
        assert res.available is False
        assert res.reason == "db_unavailable"
        assert res.db_source == ""  # çözülmemiş DB raporlanmaz (uydurma yok)

    @pytest.mark.asyncio
    async def test_missing_refreshed_db_is_db_unavailable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(tmp_path / "yok.json"))
        res = await maigret_scanner.scan_username("soxoj")
        assert res.available is False
        assert res.reason == "db_unavailable"

    @pytest.mark.asyncio
    async def test_bundled_source_label_when_env_empty(self, monkeypatch):
        monkeypatch.delenv("PINEAL_MAIGRET_DB", raising=False)
        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": 1})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan_factory())

        res = await maigret_scanner.scan_username("soxoj", limit=1)
        # test mock'u gerçek DB değildir; kaynak etiketi UYDURULMAZ (boş kalır)
        assert res.available is True
        assert res.db_source == ""
        assert res.db_sites == 0

    @pytest.mark.asyncio
    async def test_cache_keyed_by_source_env_change_reloads(self, monkeypatch, tmp_path):
        db1 = _write_db(tmp_path / "bir.json", {"A": {"url": "https://a.example.com/{username}"}})
        db2 = _write_db(
            tmp_path / "iki.json",
            {
                "A": {"url": "https://a.example.com/{username}"},
                "B": {"url": "https://b.example.com/{username}"},
            },
        )
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan_factory())

        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(db1))
        res1 = await maigret_scanner.scan_username("soxoj", limit=5)
        assert res1.db_sites == 1

        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(db2))
        res2 = await maigret_scanner.scan_username("soxoj", limit=5)
        assert res2.db_sites == 2  # bayat önbellekle 1 dönmedi

    @pytest.mark.asyncio
    async def test_ranked_top_n_is_deterministic(self, tmp_path):
        db = _write_db(
            tmp_path / "rank.json",
            {
                "Popular": {"url": "https://p.example.com/{username}", "alexaRank": 10},
                "Obscure": {"url": "https://o.example.com/{username}"},
                "Middle": {"url": "https://m.example.com/{username}", "alexaRank": 500},
            },
        )
        raw = maigret_scanner._raw_db_from_file(str(db))
        top2 = raw.ranked_sites_dict(2)
        assert list(top2) == ["Popular", "Middle"]  # rank'ı olanlar önde, ada göre


class TestAdapterReportsDbSource:
    @pytest.mark.asyncio
    async def test_capability_notes_carry_db_source(self, monkeypatch, tmp_path):
        from agent_core.capabilities.adapters_osint import MaigretCapability
        from agent_core.capabilities.base import CapabilityContext

        db = _write_db(
            tmp_path / "refreshed.json",
            {"A": {"url": "https://a.example.com/{username}"}},
        )
        monkeypatch.setenv("PINEAL_MAIGRET_DB", str(db))
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan_factory())

        result = await MaigretCapability().run(CapabilityContext(subject="soxoj"))
        assert result.notes["db_source"] == f"file:{db}"
        assert result.notes["db_sites"] == 1
