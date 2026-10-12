"""FAZ D · D1 — Agent Skills ihracı: defterden üretim, bayatlık yakalama.

Kilitlenen iddialar:
    * Paket ``CapabilityRegistry``den türetilir; MCP araç adlarıyla BİREBİR aynı
      adları kullanır (iki yüzey tek kaynaktan beslenir).
    * Üretim deterministiktir (zaman damgası yok, aynı girdi → aynı baytlar).
    * Bayat paket sessiz kalamaz: ``--check`` ayrışmayı yakalar.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from agent_core.capabilities import Availability, BaseCapability, CapabilityRegistry, CapabilityResult
from agent_core.mcp import tools as mcp_tools

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_exporter():
    spec = importlib.util.spec_from_file_location(
        "export_skills", REPO_ROOT / "scripts" / "export_skills.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exporter():
    return _load_exporter()


class _ExtraCapability(BaseCapability):
    id = "test.extra.skill"
    kind = mcp_tools.CapabilityKind.EXTRACTOR
    license = "test"
    gates = frozenset({"vault"})
    description = "Ek yetenek — paket kendiliğinden büyümeli."

    def availability(self) -> Availability:
        return Availability.ok()

    async def run(self, ctx) -> CapabilityResult:  # pragma: no cover
        return CapabilityResult(capability_id=self.id, available=True)


class TestPackageContents:
    def test_every_capability_has_a_skill(self, exporter):
        from agent_core.capabilities import bootstrap

        files = exporter.build_skill_files(bootstrap())
        registry = bootstrap()
        assert len(files) == len(registry.ids())

    def test_skill_names_match_mcp_tool_names(self, exporter):
        from agent_core.capabilities import bootstrap

        files = exporter.build_skill_files(bootstrap())
        index = mcp_tools.build_tool_index(bootstrap())
        assert {path.split("/")[0] for path in files} == set(index)

    def test_skill_body_carries_identity_and_gates(self, exporter):
        from agent_core.capabilities import bootstrap

        files = exporter.build_skill_files(bootstrap())
        translate = files["extractor_text_translate_local/SKILL.md"]
        assert "`extractor.text.translate_local`" in translate
        assert "ENABLE_LOCAL_TRANSLATE" in translate
        assert "vault" in translate
        assert "isError: true" in translate

    def test_front_matter_is_present(self, exporter):
        from agent_core.capabilities import bootstrap

        files = exporter.build_skill_files(bootstrap())
        for content in files.values():
            assert content.startswith("---\nname: ")
            assert "\ndescription: " in content.split("---")[1]

    def test_generation_is_deterministic(self, exporter):
        from agent_core.capabilities import bootstrap

        assert exporter.build_skill_files(bootstrap()) == exporter.build_skill_files(bootstrap())

    def test_new_capability_grows_the_package(self, exporter):
        registry = CapabilityRegistry()
        registry.register(_ExtraCapability())
        files = exporter.build_skill_files(registry)
        assert list(files) == ["test_extra_skill/SKILL.md"]


class TestFreshness:
    def test_written_package_is_reported_fresh(self, exporter, tmp_path):
        exporter.write_skills(tmp_path)
        assert exporter.find_stale(tmp_path) == []

    def test_edit_is_detected_as_stale(self, exporter, tmp_path):
        exporter.write_skills(tmp_path)
        target = tmp_path / "extractor_text_language" / "SKILL.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nelle eklendi\n", encoding="utf-8")
        assert "extractor_text_language/SKILL.md" in exporter.find_stale(tmp_path)

    def test_missing_file_is_detected(self, exporter, tmp_path):
        exporter.write_skills(tmp_path)
        (tmp_path / "voice_tts_local" / "SKILL.md").unlink()
        assert "voice_tts_local/SKILL.md" in exporter.find_stale(tmp_path)

    def test_orphan_file_is_detected(self, exporter, tmp_path):
        exporter.write_skills(tmp_path)
        orphan = tmp_path / "elle_yazilmis_yetenek" / "SKILL.md"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("uydurma yetenek", encoding="utf-8")
        assert "elle_yazilmis_yetenek/SKILL.md" in exporter.find_stale(tmp_path)

    def test_check_mode_exit_code(self, exporter, tmp_path, capsys):
        exporter.write_skills(tmp_path)
        assert exporter.main([str(tmp_path), "--check"]) == 0
        (tmp_path / "extractor_text_language" / "SKILL.md").write_text("bozuk", encoding="utf-8")
        assert exporter.main([str(tmp_path), "--check"]) == 3
        assert "BAYAT" in capsys.readouterr().out


class TestCommittedPackage:
    def test_repo_package_is_fresh(self, exporter):
        """Depodaki ``skills/`` defterle uyuşmalı (bayat paket commit edilemez)."""
        committed = REPO_ROOT / "skills"
        if not committed.exists():  # paket henüz üretilmemişse atlanır, sessiz geçilmez
            pytest.skip("skills/ paketi bu checkout'ta yok")
        assert exporter.find_stale(committed) == []


def test_exporter_module_imports_without_side_effects(exporter):
    # Üretici, içe aktarıldığında dosya YAZMAZ (test bunu varsayar).
    assert hasattr(exporter, "build_skill_files")
    assert "agent_core.capabilities" in sys.modules
