"""Sorumluluk Zinciri — A-yolu kural testleri (makine bekçisi).

Üç birincil kural (2026-10-14 tasarım belgesi):

1. **Sessiz hata yasaktır** — her ``except`` ya anlamlı davranır ya da
   görevi görünür şekilde ``failed``/``halted`` taşır (log izi zorunlu).
2. **Sessiz yedek yasaktır** — Redis/tarayıcı/dış servis yokluğu → açık
   ``DEGRADED_MODE``/``PRODUCTION_REQUIRES_REDIS`` izi; ``beacon``da
   ``degraded_mode`` anahtarı.
3. **Eksik kanıt başarı değildir** — ``completed`` beyanı + boş
   ``evidence_recorded``/``missing`` alanları → ``FAKE_SUCCESS`` mührü;
   execütor ``InsufficientEvidenceError`` ile durdurur.

Bu dosya davranış + statik ölçüm taşır; ``scripts/audit_regression.py``
bulgu bazlı regresyonu ölçer. İkisi bağımsız, ikisi de yeşil olmalı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent_core.domain.responsibility import TaskContract, build_trail, seal_trail

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 3 — eksik kanıt başarı değildir (davranış)
# ─────────────────────────────────────────────────────────────────────────────


class TestMissingEvidenceIsNotSuccess:
    def test_completed_without_evidence_is_fake_success(self) -> None:
        trail = build_trail(
            claimed="completed",
            evidence_recorded=False,
            attempted_paths=["agent:x"],
            next_action="next_agent:y",
        )
        sealed = seal_trail(trail)
        assert sealed.integrity["violation"] == "FAKE_SUCCESS"
        # Mühürleme REDDEDİLDİ: ihlal taşıyan kayıt mühürlü sayılmaz.
        assert sealed.integrity["sealed"] is False

    def test_completed_with_missing_blocks_is_fake_success(self) -> None:
        trail = build_trail(
            claimed="completed",
            evidence_recorded=True,
            attempted_paths=["agent:x"],
            missing=["data_confidence"],
            next_action="next_agent:y",
        )
        sealed = seal_trail(trail)
        assert sealed.integrity["violation"] == "FAKE_SUCCESS"

    def test_failed_with_empty_fields_is_quit_without_support(self) -> None:
        trail = build_trail(claimed="failed", evidence_recorded=False)
        sealed = seal_trail(trail)
        assert sealed.integrity["violation"] == "QUIT_WITHOUT_SUPPORT"

    def test_honest_partial_seals_clean(self) -> None:
        trail = build_trail(
            claimed="partial",
            evidence_recorded=True,
            attempted_paths=["agent:x", "egress:search:https://a"],
            blockers=["http 429"],
            next_action="retry_with_backoff",
            missing=["depth_2"],
        )
        sealed = seal_trail(trail)
        assert sealed.integrity["violation"] is None
        assert sealed.integrity["sealed"] is True

    def test_handoff_counts_as_not_quitting(self) -> None:
        trail = build_trail(
            claimed="failed",
            evidence_recorded=False,
            blockers=["eşik aşıldı"],
            handoff={"to": "operator", "reason": "kasa kilitli"},
            next_action="operator_kararı",
        )
        sealed = seal_trail(trail)
        assert sealed.integrity["violation"] is None

    def test_incomplete_handoff_is_rejected(self) -> None:
        # Devir "kime/neden" sorusunu boş bırakamaz: şema doğrulaması patlar.
        with pytest.raises(ValueError, match=r"reason"):  # Handoff: "neden" zorunlu
            build_trail(
                claimed="completed",
                evidence_recorded=True,
                attempted_paths=["agent:x"],
                handoff={"to": "operator"},  # reason eksik
            )

    def test_attempted_paths_are_unique_and_sanitized(self) -> None:
        trail = build_trail(
            claimed="partial",
            evidence_recorded=True,
            attempted_paths=["agent:x", "agent:x", "bad\npath", "x" * 400],
        )
        assert trail.attempted_paths[0] == "agent:x"
        assert len(trail.attempted_paths) == 3
        assert all("\n" not in p for p in trail.attempted_paths)
        assert all(len(p) <= 300 for p in trail.attempted_paths)


class TestTaskContract:
    def test_contract_is_complete_for_every_agent(self) -> None:
        contract = TaskContract.for_agent(
            task_id="t",
            agent_id="search_engine",
            required_inputs=["query"],
            acceptance_criteria=["kaynak listesi + alıntı"],
            evidence_output=["evidence_chain"],
        )
        contract.ensure_complete()  # eksik sözleşme başlamaz — hata fırlatır

    def test_incomplete_contract_refuses(self) -> None:
        contract = TaskContract(
            task_id="t",
            agent_id="a",
            required_inputs=[],
            acceptance_criteria=[],
            evidence_output=[],
        )
        with pytest.raises(ValueError, match="TASK_CONTRACT_INCOMPLETE"):
            contract.ensure_complete()


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 2 — sessiz yedek yasak (worker: iz + beacon anahtarı)
# ─────────────────────────────────────────────────────────────────────────────


class TestNoSilentFallback:
    def test_production_fallback_is_hard_refusal(self) -> None:
        src = _read("agent_core/workers/agent_worker.py")
        assert "PRODUCTION_REQUIRES_REDIS" in src
        assert 'os.getenv("PINEAL_ENV"' in src
        # Üretim dalı sert reddeder: RuntimeError yükselir.
        assert re.search(
            r"raise RuntimeError\(\s*[frub]*[\"']PRODUCTION_REQUIRES_REDIS", src
        )

    def test_dev_fallback_is_degraded_not_silent(self) -> None:
        src = _read("agent_core/workers/agent_worker.py")
        assert "DEGRADED_MODE" in src
        # Uyarı seviyesi: in-memory fallback sözü ERROR/WARNING log içinde.
        assert re.search(
            r"logger\.(error|warning)\([^)]*DEGRADED_MODE", src, re.S
        ) or re.search(
            r"logger\.(error|warning)\(\s*\[\%s\]\s*DEGRADED_MODE", src
        )

    def test_beacon_carries_degraded_mode(self) -> None:
        src = _read("agent_core/workers/agent_worker.py")
        assert '"degraded_mode": degraded_mode' in src
        # beacon üretici imzası bayrağı alır.
        assert re.search(r"def build_liveness_message\([^)]*degraded_mode", src, re.S)

    def test_probe_failure_logs_fallback(self) -> None:
        src = _read("agent_core/workers/agent_worker.py")
        idx = src.find("backend sondası başarısız")
        assert idx != -1, "probe fallback log satırı yok"
        window = src[max(0, idx - 300) : idx + 300]
        assert "logger.warning" in window
        assert not re.search(r"except[^:]*:\s*\n\s*pass\b", window)

    def test_closure_publish_failure_logs_error(self) -> None:
        src = _read("agent_core/workers/agent_worker.py")
        idx = src.find("KAPANIŞ İZİ YAYINLANAMADI")
        assert idx != -1, "kapanış yayını arıza izi yok"
        window = src[max(0, idx - 600) : idx + 600]
        assert "logger.error" in window
        assert "exc_info" in window
        # Yasaklı kalıp AST'de yasak (docstring'deki tarihsel anlatım değil).
        import ast

        tree = ast.parse(src)
        forbidden = [
            n.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "tracker"
            and n.attr in {"set_ready", "set_active", "set_done", "set_wait"}
        ]
        assert forbidden == []


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 1 — sessiz hata yasak (bilinen sıcak noktalar açık kalamaz)
# ─────────────────────────────────────────────────────────────────────────────


class TestNoSilentErrors:
    def test_caption_extractor_logs_instead_of_passing(self) -> None:
        src = _read("agent_core/scraper/instagram_ghost.py")
        idx = src.find("def _caption_of(")
        assert idx != -1
        window = src[idx : idx + 700]
        assert not re.search(r"except Exception:\s*\n\s*pass", window)
        assert re.search(r"(logger|logging)\.(warning|error|exception)", window)

    def test_detect_language_error_is_logged(self) -> None:
        src = _read("agent_core/capabilities/adapters_web.py")
        assert re.search(r"logger\.(error|warning)[^\n]*[Dd]il tespiti", src)

    def test_metadata_error_is_logged(self) -> None:
        src = _read("agent_core/capabilities/adapters_web.py")
        assert re.search(r"logger\.(debug|info|warning|error)[^\n]*metadata", src, re.I)

    def test_executor_records_failures_in_responsibility_trails(self) -> None:
        """Hata zincirden gizlenemez: başarısız/ düşük-güven koşuların dürüst
        izi ``run.responsibility`` alanına yazılır (kanıt zinciri uydurma
        kanıtla doldurulmaz); başarı kayıtları ``responsibility`` mührüyle
        ``evidence_chain``e girer."""
        src = _read("agent_core/task_executor.py")
        # Başarı: kanıt kaydı + sorumluluk mührü birlikte.
        assert src.count("self._responsibility_trail(") >= 5  # 2 başarı + 4 hata/halt
        assert '_output_record["responsibility"]' in src
        assert 'output_record["responsibility"]' in src
        # Eksik kanıt mührü reddederse görev durur.
        assert "sorumluluk mührü reddetti" in src
        assert "InsufficientEvidenceError" in src
        # Hata/halt + derinlik-destek başarısızlığı: kanıt zinciri yerine
        # koşunun kendi alanı (2 hata + 2 düşük-güven + 2 derin-araştırma).
        assert src.count("run.responsibility = self._responsibility_trail(") == 6
        # Destek talebi GERÇEKTEN oluşur (kayıt + AwaitingHumanEvent + log).
        assert src.count("self._request_support(") == 6
        assert "AwaitingHumanEvent" in src
        assert "DESTEK TALEBİ" in src
        # AgentRun alanı şemada.
        run_src = _read("agent_core/domain/memory_models.py")
        assert "responsibility: Optional[Dict[str, Any]] = None" in run_src
        assert "support_requests: List[Dict[str, Any]] = []" in run_src
        assert "ingested_outputs: Dict[str, Dict[str, Any]] = {}" in run_src

    def test_executor_egrss_attempts_are_attributed(self) -> None:
        src = _read("agent_core/task_executor.py")
        assert "attempt_mark = len(egress_attempts())" in src
        assert "_egress_slice" in src


# ─────────────────────────────────────────────────────────────────────────────
# Yaprak kapılar (E-GÖZ2-3) — davranış sözleşmesi
# ─────────────────────────────────────────────────────────────────────────────


class TestLeafVaultDoors:
    def test_run_scraper_cli_gate_is_strict(self) -> None:
        src = _read("agent_core/scraper/run_scraper.py")
        assert 'require_open(purpose="scraper", strict=True)' in src
        # Kapı tarayıcı açılmadan ÖNCE çağrılır.
        assert src.find("require_open") < src.find("async_playwright")

    def test_holehe_scan_gates_after_enabled_and_sanitize(self) -> None:
        src = _read("agent_core/services/holehe_scanner.py")
        gate = src.find('require_open(purpose="osint")')
        assert gate != -1
        assert gate > src.find("is_enabled")
        assert gate > src.find("sanitize")

    def test_boundary_marks_authority_on_open_path(self) -> None:
        src = _read("backend/api.py")
        fn = src.find("def _require_vault_open(")
        assert fn != -1
        nxt = src.find("\ndef ", fn + 10)
        body = src[fn : nxt if nxt != -1 else None]
        assert "mark_vault_egress_authorized()" in body
        assert "return None" in body
