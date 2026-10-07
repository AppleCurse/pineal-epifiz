"""FAZ D · D5 — rapor fabrikası servisi: kanıt bağlantısı, mühür, dürüst eksik.

Kilitlenen iddialar:
    * Rapor yalnız kanonik kanıt çizelgesinden üretilir; strateji satırları
      çizelgeye girmez, bozuk satırlar REDDEDİLİR ve sayılır.
    * Markdown + manifest her koşulda yazılır; PDF/diyagram üretilir.
    * Video ffmpeg yoksa ``dependency_missing:ffmpeg`` der — uydurma dosya yok.
    * Manifest mührü doğrulanabilir: gövde hash'i ``manifest_sha256``e eşit.
    * Bilinmeyen format / boş başlık dürüst ret; dosya yazılmaz.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from agent_core.services import report_factory as rf

EVIDENCE = [
    {
        "evidence_id": "ev_" + "a" * 20,
        "epistemic_type": "observation",
        "source_engine": "twscrape",
        "content": "Gönderi: 'Merhaba dünya'",
        "provenance_refs": ["https://x.com/u/1"],
        "observed_at": "2026-01-02T03:04:05Z",
    },
    {
        "evidence_id": "ev_" + "b" * 20,
        "epistemic_type": "absence",
        "source_engine": "company_seo",
        "content": "robots.txt yayınlanmamış",
        "provenance_refs": ["https://ornek.com/robots.txt"],
    },
    {
        "evidence_id": "ev_" + "c" * 20,
        "epistemic_type": "strategy",
        "source_engine": "plan",
        "content": "çizelgeye GİRMEZ",
    },
    {"bozuk": "kanıt değil"},
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PINEAL_REPORT_DIR", raising=False)
    monkeypatch.delenv("ENABLE_REPORT_FACTORY", raising=False)
    yield


@pytest.fixture()
def out_dir(tmp_path):
    return tmp_path / "raporlar"


def _manifest_of(package) -> dict:
    return json.loads(Path(package.manifest_path).read_text(encoding="utf-8"))


class TestEvidenceFidelity:
    def test_only_canonical_evidence_enters_report(self, out_dir):
        package = rf.build_report(
            EVIDENCE, title="Örnek Rapor", subject="ornek.com", formats=("markdown",), out_dir=out_dir
        )
        assert package.available is True
        assert len(package.evidence_ids) == 2
        assert package.notes["rejected_item_count"] == 1
        assert package.notes["excluded_strategy_count"] == 1
        text = Path(package.artifact("markdown").path).read_text(encoding="utf-8")
        assert "çizelgeye GİRMEZ" not in text
        assert "not independently verified" in text  # epistemik not aynen taşınır
        assert "https://x.com/u/1" in text

    def test_empty_title_is_honest(self, out_dir):
        package = rf.build_report(EVIDENCE, title="   ", formats=("markdown",), out_dir=out_dir)
        assert package.available is False
        assert package.reason == "empty_title"
        assert not out_dir.exists()  # boş başlıkta dizin bile açılmaz

    def test_unknown_format_is_honest(self, out_dir):
        package = rf.build_report(EVIDENCE, title="Rapor", formats=("exe",), out_dir=out_dir)
        assert package.available is False
        assert package.reason == "unknown_format:exe"

    def test_report_dir_env_is_honored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PINEAL_REPORT_DIR", str(tmp_path / "ozel"))
        assert rf.report_dir() == tmp_path / "ozel"


class TestArtifacts:
    def test_pdf_and_diagram_and_manifest(self, out_dir):
        package = rf.build_report(
            EVIDENCE, title="Örnek Rapor", subject="ornek.com", formats=("pdf", "diagram"), out_dir=out_dir
        )
        pdf = package.artifact("pdf")
        diagram = package.artifact("diagram")
        assert pdf.available is True and Path(pdf.path).read_bytes().startswith(b"%PDF")
        assert diagram.available is True and Path(diagram.path).read_bytes().startswith(b"\x89PNG")
        assert pdf.sha256 == hashlib.sha256(Path(pdf.path).read_bytes()).hexdigest()

    def test_video_is_honest_without_ffmpeg(self, out_dir, monkeypatch):
        monkeypatch.setattr(rf.shutil, "which", lambda name: None)
        package = rf.build_report(
            EVIDENCE, title="Örnek", formats=("video",), out_dir=out_dir
        )
        video = package.artifact("video")
        assert video.available is False
        assert video.reason == "dependency_missing:ffmpeg"
        assert package.available is True  # markdown + manifest yine teslim

    @pytest.mark.skipif(os.name != "posix", reason="sahte ffmpeg POSIX betiği (WinError 193)")
    def test_video_with_fake_ffmpeg(self, out_dir, tmp_path, monkeypatch):
        fake = tmp_path / "ffmpeg"
        fake.write_text('#!/bin/sh\nfor last; do :; done\nprintf "VIDEO" > "$last"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
        package = rf.build_report(EVIDENCE, title="Örnek", formats=("video",), out_dir=out_dir)
        video = package.artifact("video")
        assert video.available is True
        assert Path(video.path).read_bytes() == b"VIDEO"


class TestManifestSeal:
    def test_manifest_hash_is_verifiable(self, out_dir):
        package = rf.build_report(
            EVIDENCE, title="Mühür Testi", formats=("pdf",), out_dir=out_dir
        )
        manifest = _manifest_of(package)
        sealed = manifest.pop("manifest_sha256")
        body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(body.encode("utf-8")).hexdigest() == sealed
        assert sealed == package.manifest_sha256

    def test_manifest_lists_artifact_hashes_and_evidence(self, out_dir):
        package = rf.build_report(EVIDENCE, title="Liste", formats=("pdf",), out_dir=out_dir)
        manifest = _manifest_of(package)
        assert manifest["evidence_ids"] == list(package.evidence_ids)
        names = {row["name"] for row in manifest["artifacts"]}
        assert names == {"markdown", "pdf"}
        for row in manifest["artifacts"]:
            file_path = Path(package.artifact(row["name"]).path)
            assert row["sha256"] == hashlib.sha256(file_path.read_bytes()).hexdigest()
            assert row["bytes"] == file_path.stat().st_size
        assert "kriptografik imza DEĞİLDİR" in manifest["fidelity"]


class TestAvailability:
    def test_availability_reports_reasons(self, monkeypatch):
        monkeypatch.setattr(rf.shutil, "which", lambda name: None)
        caps = rf.availability()
        assert caps["markdown"] == (True, "")
        assert caps["video"][1] == "dependency_missing:ffmpeg"
        assert caps["pdf"][0] is True or caps["pdf"][1] == "dependency_missing:reportlab"
