"""Karar motoru — kanıt taşımayan ajanı "başarılı" saymayan tam durum makinesi.

``make_decision(agent_runs)`` koşu kayıtlarını tarayıp görevin devam/insan
onayı/durma kararını verir. Kritik kural: ``completed`` görünen bir kayıt
GERÇEKTEN kanıt taşımıyorsa (``_run_bears_evidence``) başarı sayılmaz; kaynak
kullanılamazlık sinyalleri (``UNAVAILABLE_WARNING_CODES``) gerekçeye yazılır.

Konfigürasyon ``agent_core/config_loader.DecisionConfig`` üzerinden gelir
(``config/decision_config.yaml``) — eşikler kod içine gömülmez.

Test: ``tests/unit/test_decision_engine.py``,
``tests/unit/test_decision_engine_degraded.py``.
"""

import logging
from typing import Dict, Any

from agent_core.config_loader import DecisionConfig
from agent_core.domain.pipeline_status import PipelineStatus
from agent_core.domain.memory_models import AgentRun
from agent_core.services.uncertainty_engine import UncertaintyEngine

logger = logging.getLogger(__name__)

# Bu uyarı kodları "completed" görünse de ajanın kaynağının KULLANILAMAZ
# olduğunu bildirir; tam başarı sayılmaz.
UNAVAILABLE_WARNING_CODES = frozenset({
    "data_unavailable", "provider_credentials_unavailable", "llm_unavailable",
    "provider_error", "auth_failed", "rate_limited", "timeout",
    "no_target_identity", "target_evidence_unavailable",
})


class DecisionEngine:
    def __init__(self, config: DecisionConfig):
        self.config = config

    @staticmethod
    def _unavailable_reasons(run: Any) -> list:
        """Kaynak kullanılamazlık sinyalleri (boşsa ajan güvenilir)."""
        reasons = []
        if getattr(run, "status", None) == "unavailable":
            reasons.append("status=unavailable")
        for w in getattr(run, "warnings", []) or []:
            if str(w).lower() in UNAVAILABLE_WARNING_CODES:
                reasons.append(str(w))
        summary = getattr(run, "output_summary", None) or {}
        if isinstance(summary, dict) and summary.get("data_confidence") is False:
            reasons.append("data_confidence=False")
        # [RÖNTGEN 2026-09-23] GÖREV TAMAMLANDI ≠ KARAR ÜRETİLDİ:
        # `completed_no_decision` koşusu (veya `decision_grade=False`) ajanın
        # KENDİSİNİN "bu çıktı karar değil" beyanıdır. Özet alanında
        # `data_confidence` taşımasa bile bu koşu karar-Grade sayılmaz —
        # yani hüküm yalnız payload'a değil koşu durumuna da bağlıdır.
        if (
            getattr(run, "status", None) == "completed_no_decision"
            or getattr(run, "decision_grade", True) is False
        ):
            reasons.append("completed_no_decision")
        code = getattr(run, "error_code", None)
        if code and str(code).upper() in ("NO_TARGET_IDENTITY", "TARGET_IDENTITY_MISSING"):
            reasons.append(str(code))
        return reasons

    @staticmethod
    def _run_bears_evidence(run: Any) -> bool:
        """'completed' görünen bir ajan kaydı GERÇEKTEN kanıt taşıyor mu?

        Aynı sözleşme UncertaintyEngine'de kullanılır: placeholder ibareler
        ("veri yok", "bulunamadı", "unknown"...) ve metadata alanları kanıt
        sayılmaz. Böylece boş profil + sahte "completed" -> COMPLETED zinciri
        [019] kırılır.
        """
        summary = getattr(run, "output_summary", None) or {}
        if not isinstance(summary, dict):
            return False
        # data_confidence=False: kaynak verisi yok; sayısal ölçümler bile
        # (0.0 skor, 0 hit) bu durumda kanıt sayılmaz.
        if summary.get("data_confidence") is False:
            return False
        candidates = {
            k: v for k, v in summary.items()
            if k not in UncertaintyEngine.RUNTIME_METADATA_FIELDS
        }
        return any(
            UncertaintyEngine._value_bears_evidence(v)
            for v in candidates.values()
        )

    def make_decision(self, agent_runs: Dict[str, AgentRun]) -> PipelineStatus:
        """[019] Tam state machine.

        - Kritik ajan başarısız/halted  -> HALTED_CRITICAL
        - Hiçbir ajan kanıt üretmedi    -> HALTED_INSUFFICIENT_EVIDENCE
          (boş rota, boş profil, placeholder-şişkin çıktılar dahil)
        - Kanıt var + bazı ajanlar
          başarısız/unavailable         -> PARTIALLY_COMPLETED
        - Kanıt var + hepsi tamam        -> COMPLETED
        """
        failed_runs = {
            name: run for name, run in agent_runs.items()
            if run.status in ("failed", "halted")
        }
        critical_failures = [
            agent_name for agent_name in failed_runs
            if agent_name in self.config.critical_agents
            or not self.config.get_agent_config(agent_name).graceful_degradation
        ]
        if critical_failures:
            logger.error(f"Pipeline halted due to critical failures: {', '.join(critical_failures)}")
            return PipelineStatus.HALTED_CRITICAL

        # KANIT VARLIĞI: 'completed' tek başına başarı değildir. Kaynağı
        # kullanılamaz/placeholder-şişkin olan kayıtlar kanıt sayılmaz.
        # (Gerçek kanıt + kullanılamazlık uyarısı birlikte olabilir: kanıt
        # yine sayılır, ajan ayrıca PARTIAL'a işaret eder.)
        degraded_runs = {
            name: run for name, run in agent_runs.items()
            if self._unavailable_reasons(run)
        }
        evidence_runs = {
            name: run for name, run in agent_runs.items()
            if run.status == "completed" and self._run_bears_evidence(run)
        }

        if not evidence_runs:
            affected = ", ".join(sorted(agent_runs)) if agent_runs else "(boş rota: ajan çalıştırılmadı)"
            logger.warning(
                f"Pipeline halted: no agent produced evidence. "
                f"Runs: {affected}; failed={sorted(failed_runs)}; "
                f"unavailable={sorted(degraded_runs)}"
            )
            return PipelineStatus.HALTED_INSUFFICIENT_EVIDENCE

        if failed_runs or degraded_runs:
            affected = ", ".join(sorted(set(failed_runs) | set(degraded_runs)))
            logger.warning(f"Pipeline partially completed. Unavailable/failed agents: {affected}")
            return PipelineStatus.PARTIALLY_COMPLETED
        return PipelineStatus.COMPLETED
