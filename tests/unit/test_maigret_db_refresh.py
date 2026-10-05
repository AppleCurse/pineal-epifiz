"""FAZ A · A8 — maigret DB tazeleme çekirdeği (WhatsMyName/sherlock birleştirme).

Kilitlenen üç kural (dürüstlük sözleşmesi):
    1. UYDURMA YOK — kaynakta olmayan alan üretilmez (ör. `known` boşsa
       `usernameClaimed` icat edilmez).
    2. KÜRASYON EZİLMEZ — maigret'in mevcut kaydı üzerine yazılmaz; yalnız
       eksik alanlar doldurulur.
    3. DESTEKLENMEYEN KİP ATLANIR ve SAYILIR (sherlock `response_url`,
       boş URL, kipsiz WMN kaydı).

Çekirdek saf ve deterministiktir: aynı girdi → aynı çıktı.
"""

from __future__ import annotations

import json

import pytest

from agent_core.services import maigret_db_refresh as r


# ---------------------------------------------------------------------------
# sherlock birleştirmesi
# ---------------------------------------------------------------------------


def _sherlock_entry(**overrides):
    base = {
        "url": "https://example.com/@{}",
        "urlMain": "https://example.com/",
        "errorType": "status_code",
        "username_claimed": "knownuser",
    }
    base.update(overrides)
    return base


class TestMergeSherlock:
    def test_new_site_added_with_mapped_fields(self):
        sites: dict = {}
        stats = r.merge_sherlock(sites, {"Example": _sherlock_entry()})
        assert stats.added == 1
        assert sites["Example"]["url"] == "https://example.com/@{username}"
        assert sites["Example"]["urlMain"] == "https://example.com/"
        assert sites["Example"]["checkType"] == "status_code"
        assert sites["Example"]["usernameClaimed"] == "knownuser"

    def test_no_fabricated_username_claimed(self):
        """Kural 1: kaynakta yoksa `usernameClaimed` İCAT EDİLMEZ."""
        sites: dict = {}
        entry = _sherlock_entry()
        entry.pop("username_claimed")
        r.merge_sherlock(sites, {"Ornek": entry})
        assert "usernameClaimed" not in sites["Ornek"]

    def test_response_url_mode_skipped_and_counted(self):
        """Kural 3: desteklenmeyen kip yanlış dönüştürülmez; atlanır + sayılır."""
        sites: dict = {}
        stats = r.merge_sherlock(
            sites, {"Redirector": _sherlock_entry(errorType="response_url")}
        )
        assert sites == {}
        assert stats.skipped == 1
        assert stats.skip_reasons["unsupported_mode"] == 1
        assert stats.added == 0

    def test_empty_url_skipped_and_counted(self):
        sites: dict = {}
        stats = r.merge_sherlock(sites, {"Bos": _sherlock_entry(url="")})
        assert sites == {}
        assert stats.skipped == 1
        assert stats.skip_reasons["empty_url"] == 1

    def test_message_mode_maps_error_msg_to_absence_strs(self):
        sites: dict = {}
        entry = _sherlock_entry(errorType="message", errorMsg=["Not Found", "404 page"])
        r.merge_sherlock(sites, {"Msg": entry})
        assert sites["Msg"]["checkType"] == "message"
        assert sites["Msg"]["absenceStrs"] == ["Not Found", "404 page"]

    def test_existing_site_only_missing_fields_filled(self):
        """Kural 2: elle kürate değerler ezilmez; yalnız eksik alan dolar."""
        sites = {
            "GitHub": {
                "url": "https://github.com/{username}",
                "usernameClaimed": "torvalds",  # kürate değer — EZİLMEZ
            }
        }
        entry = _sherlock_entry(urlMain="https://github.com/")
        stats = r.merge_sherlock(sites, {"GitHub": entry})
        assert stats.filled == 1
        assert stats.added == 0
        assert sites["GitHub"]["usernameClaimed"] == "torvalds"  # korunur
        assert sites["GitHub"]["urlMain"] == "https://github.com/"  # eksik doldu

    def test_existing_site_unchanged_when_complete(self):
        sites = {
            "GitHub": {
                "url": "https://github.com/{username}",
                "urlMain": "https://github.com/",
                "checkType": "status_code",
                "usernameClaimed": "torvalds",
            }
        }
        stats = r.merge_sherlock(sites, {"GitHub": _sherlock_entry(urlMain="https://github.com/")})
        assert stats.unchanged == 1
        assert stats.filled == 0
        assert stats.added == 0

    def test_schema_and_comment_keys_are_not_data(self):
        sites: dict = {}
        stats = r.merge_sherlock(
            sites,
            {
                "$schema": "data.schema.json",
                "__comment__": "not a site",
                "Real": _sherlock_entry(),
            },
        )
        assert stats.candidates == 1
        assert stats.added == 1
        assert "$schema" not in sites

    def test_url_probe_and_regex_carry_over(self):
        sites: dict = {}
        entry = _sherlock_entry(
            urlProbe="https://probe.example.com/{}", regexCheck="^[a-z]{3,20}$"
        )
        r.merge_sherlock(sites, {"Probe": entry})
        assert sites["Probe"]["urlProbe"] == "https://probe.example.com/{username}"
        assert sites["Probe"]["regexCheck"] == "^[a-z]{3,20}$"


# ---------------------------------------------------------------------------
# WhatsMyName birleştirmesi
# ---------------------------------------------------------------------------


def _wmn_entry(**overrides):
    base = {
        "name": "WmnExample",
        "uri_check": "https://wmn.example.com/@{account}",
        "uri_pretty": "https://wmn.example.com/@{account}",
        "m_code": 200,
        "e_code": 404,
        "known_accounts": [{"username": "claimed_user", "note": "site sahibi"}],
        "cat": "social",
    }
    base.update(overrides)
    return base


class TestMergeWmn:
    def test_wmn_payload_shape_sites_list(self):
        sites: dict = {}
        stats = r.merge_wmn(sites, {"license": ["CC"], "sites": [_wmn_entry()]})
        assert stats.candidates == 1
        assert stats.added == 1
        entry = sites["WmnExample"]
        assert entry["url"] == "https://wmn.example.com/@{username}"
        assert entry["checkType"] == "status_code"
        assert entry["usernameClaimed"] == "claimed_user"
        assert entry["tags"] == ["social"]

    def test_string_codes_become_message_check(self):
        sites: dict = {}
        entry = _wmn_entry(e_string="sayfa bulunamadi", m_string="profil burada")
        entry.pop("m_code", None)
        entry.pop("e_code", None)
        r.merge_wmn(sites, {"sites": [entry]})
        assert sites["WmnExample"]["checkType"] == "message"
        assert sites["WmnExample"]["absenceStrs"] == ["sayfa bulunamadi"]
        assert sites["WmnExample"]["presenseStrs"] == ["profil burada"]

    def test_empty_known_accounts_never_fabricates_claimed(self):
        """Kural 1: `known_accounts` boşsa `usernameClaimed` ÜRETİLMEZ."""
        sites: dict = {}
        stats = r.merge_wmn(sites, {"sites": [_wmn_entry(known_accounts=[])]})
        assert stats.added == 1
        assert "usernameClaimed" not in sites["WmnExample"]

    def test_entry_without_any_check_mode_skipped(self):
        """Kural 3: ne kod ne mesaj varsa kontrol kipi İCAT EDİLMEZ → atla+say."""
        sites: dict = {}
        entry = _wmn_entry()
        for key in ("m_code", "e_code"):
            entry.pop(key)
        stats = r.merge_wmn(sites, {"sites": [entry]})
        assert sites == {}
        assert stats.skipped == 1
        assert stats.skip_reasons["unsupported_mode"] == 1

    def test_empty_uri_skipped(self):
        sites: dict = {}
        stats = r.merge_wmn(sites, {"sites": [_wmn_entry(uri_check="")]})
        assert sites == {}
        assert stats.skip_reasons["empty_url"] == 1

    def test_missing_name_skipped(self):
        sites: dict = {}
        entry = _wmn_entry()
        entry.pop("name")
        stats = r.merge_wmn(sites, {"sites": [entry]})
        assert sites == {}
        assert stats.skip_reasons["no_site_name"] == 1

    def test_wmn_fills_only_missing_fields_on_existing(self):
        sites = {"WmnExample": {"url": "https://kurated.example.com/{username}"}}
        stats = r.merge_wmn(sites, {"sites": [_wmn_entry()]})
        assert stats.filled == 1
        assert sites["WmnExample"]["url"] == "https://kurated.example.com/{username}"
        assert sites["WmnExample"]["checkType"] == "status_code"


# ---------------------------------------------------------------------------
# Taban DB biçimleri + uçtan uca tazeleme + CLI
# ---------------------------------------------------------------------------


class TestBaseShapes:
    def test_flat_and_nested_shapes_both_load(self, tmp_path):
        flat = {"SiteA": {"url": "https://a.example.com/{username}"}}
        nested = {"sites": {"SiteB": {"url": "https://b.example.com/{username}"}}, "engines": {}}
        flat_path = tmp_path / "flat.json"
        nested_path = tmp_path / "nested.json"
        flat_path.write_text(json.dumps(flat), encoding="utf-8")
        nested_path.write_text(json.dumps(nested), encoding="utf-8")

        sites_f, shape_f, _ = r.load_base_sites(str(flat_path))
        sites_n, shape_n, _ = r.load_base_sites(str(nested_path))
        assert shape_f == "flat" and set(sites_f) == {"SiteA"}
        assert shape_n == "nested" and set(sites_n) == {"SiteB"}

    def test_empty_db_raises_no_silent_fallback(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"sites": {}}), encoding="utf-8")
        with pytest.raises(ValueError):
            r.load_base_sites(str(bad))

    def test_write_refreshed_db_preserves_nested_sections(self):
        sites = {"Yeni": {"url": "https://y.example.com/{username}"}}
        payload = r.write_refreshed_db(
            sites, "nested", {"sites": {}, "engines": {"json": {}}, "tags": []}
        )
        assert payload["sites"] == sites
        assert payload["engines"] == {"json": {}}
        assert payload["tags"] == []


class TestRefreshEndToEnd:
    def test_refresh_reports_honest_counts(self, tmp_path):
        base = tmp_path / "base.json"
        base.write_text(
            json.dumps(
                {
                    "GitHub": {
                        "url": "https://github.com/{username}",
                        "usernameClaimed": "torvalds",
                    },
                    "Meccut": {"url": "https://mevcut.example.com/{username}"},
                }
            ),
            encoding="utf-8",
        )
        sherlock = tmp_path / "sherlock.json"
        sherlock.write_text(
            json.dumps(
                {
                    "GitHub": _sherlock_entry(urlMain="https://github.com/"),
                    "YeniSherlock": _sherlock_entry(url="https://ys.example.com/{}"),
                    "AtlananKip": _sherlock_entry(
                        url="https://ak.example.com/{}", errorType="response_url"
                    ),
                }
            ),
            encoding="utf-8",
        )
        wmn = tmp_path / "wmn.json"
        wmn.write_text(
            json.dumps(
                {
                    "sites": [
                        _wmn_entry(name="YeniWmn", uri_check="https://yw.example.com/{account}"),
                        _wmn_entry(name="Meccut"),  # aynı site: yalnız doldurur
                    ]
                }
            ),
            encoding="utf-8",
        )

        sites, report = r.refresh(str(base), str(wmn), str(sherlock))
        assert report.base_sites == 2
        assert report.final_sites == 4  # GitHub, Meccut, YeniSherlock, YeniWmn
        assert report.sherlock is not None
        assert report.sherlock.added == 1
        assert report.sherlock.filled == 1  # GitHub urlMain doldu
        assert report.sherlock.skipped == 1
        assert report.wmn is not None
        assert report.wmn.added == 1
        assert report.wmn.filled == 1  # Meccut alanları doldu
        assert "GitHub" in sites and "YeniSherlock" in sites and "YeniWmn" in sites

    def test_missing_source_is_reported_not_hidden(self, tmp_path):
        base = tmp_path / "base.json"
        base.write_text(json.dumps({"A": {"url": "https://a.example.com/{username}"}}), encoding="utf-8")
        _sites, report = r.refresh(str(base), None, None)
        assert sorted(report.missing_sources) == ["sherlock", "wmn"]
        assert report.sherlock is None
        assert report.wmn is None

    def test_cli_writes_file_and_prints_report(self, tmp_path, capsys):
        base = tmp_path / "base.json"
        base.write_text(json.dumps({"A": {"url": "https://a.example.com/{username}"}}), encoding="utf-8")
        sherlock = tmp_path / "sherlock.json"
        sherlock.write_text(json.dumps({"Yeni": _sherlock_entry(url="https://y.example.com/{}")}), encoding="utf-8")
        out = tmp_path / "refreshed.json"

        rc = r.main(["--base", str(base), "--sherlock", str(sherlock), "--out", str(out)])
        assert rc == 0
        written = json.loads(out.read_text(encoding="utf-8"))
        assert "Yeni" in written and "A" in written
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["final_sites"] == 2

    def test_cli_without_source_refuses(self, tmp_path):
        base = tmp_path / "base.json"
        base.write_text(json.dumps({"A": {"url": "https://a.example.com/{username}"}}), encoding="utf-8")
        assert r.main(["--base", str(base)]) == 2

    def test_determinism_same_input_same_output(self, tmp_path):
        base = tmp_path / "base.json"
        base.write_text(json.dumps({"A": {"url": "https://a.example.com/{username}"}}), encoding="utf-8")
        sherlock = tmp_path / "sherlock.json"
        sherlock.write_text(
            json.dumps({"Yeni": _sherlock_entry(url="https://y.example.com/{}")}), encoding="utf-8"
        )
        first_sites, first_report = r.refresh(str(base), None, str(sherlock))
        second_sites, second_report = r.refresh(str(base), None, str(sherlock))
        assert first_sites == second_sites
        assert first_report.model_dump() == second_report.model_dump()
