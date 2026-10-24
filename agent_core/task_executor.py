"""PINEAL yürütücüsü — 360° boru hattının orkestra şefi (sistemin kalbi).

``execute_task(input_data, task_id)`` çağrısı, önce plan (``CognitiveRouter``)
sonra ajan sırası olacak şekilde TÜM görevi yönetir:

  1. **Plan**: hangi ajanların koşacağı girdiye göre belirlenir.
  2. **Bellek**: kanonik bellek + kristal hatırlama (``_recall_memory_crystal``);
     görev sonunda kanıt hedef profiliyle birlikte kalıcı yazılır
     (``_merge_task_memory``).
  3. **Ajan koşusu**: her ajan AYRI duvar saati sınırıyla koşar
     (``_execute_with_timeout`` → ``AgentTimeoutError``); ajan başına girdi
     özeti, çıktı kanıt kaydı ve hash üretilir (``_evidence_record``,
     ``_hash_evidence_result``).
  4. **Deterministik motor**: 7-sütun (``PillarOrchestrator``) LLM'siz çalışır;
     çıktısı ``pillar_evidence_adapter`` ile kanonik kanıta ve nötr zaman
     çizelgesine dönüştürülür.
  5. **Kapılar**: ``claim_decision_gate`` engelli iddiayı bastırır; ``quote_guard``
     alıntıyı kaynağa bağlar; Tier-2 alanlar allowlist ile yazılır.
  6. **Sorumluluk zinciri**: her ajan için açılan egress denemeleri ve kanıt
     hash'i mühürlenir (``_responsibility_trail``); Agent Rack durumu YALNIZ
     adı taşıdığı ajanın koşusundan yayınlanır (ödünç slot yasak).
  7. **Destek & devam**: kanıt yetmezse ``ResumeBlockedError``/destek talebi
     üretilir; destek hâlâ açıkken devam REDDEDİLİR. Bitmiş adımlar
     ``_resume_done`` ile atlanır (yan etki tekrarı yok).

Her çıkış yolunda geçici görseller silinir. Hata gizlenmez: loglanır, olay
olarak yayınlanır ve yukarı iletilir.

Tüketici: ``backend/api.py``, ``main.py``, CLI scriptleri.
Test: ``tests/integration/test_task_executor_flow.py``, ``tests/unit/test_execute_with_timeout.py``,
``tests/unit/test_evidence_hash_and_fallback_gate.py``.
"""

import copy
import inspect
import os
import tempfile
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List

from datetime import datetime, timezone
from pydantic import BaseModel

from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent
from agent_core.capabilities.egress import egress_attempts, open_client
from agent_core.agents.autonomous_verifier import AutonomousVerifier
from agent_core.agents.cognitive_profiler import CognitiveProfilerAgent
from agent_core.agents.depth_analyst import DepthAnalyst
from agent_core.agents.friction_detector import FrictionDetectorAgent
from agent_core.agents.human_behavior import HumanBehaviorAnalyzer
from agent_core.agents.interpreter_agent import InterpreterAgent
from agent_core.agents.mirror_truth import MirrorOfTruth
from agent_core.agents.osint_investigator import OsintInvestigatorAgent
from agent_core.agents.passion_mapper import PassionMapperAgent
from agent_core.agents.pattern_interrupt import PatternInterrupt
from agent_core.agents.resonance_calculator import ResonanceCalculator
from agent_core.agents.resonance_synthesizer import ResonanceSynthesizerAgent
from agent_core.domain.evidence_models import EvidenceTimeline
from agent_core.domain.memory_models import (
    AgentRun,
    AuthenticBridge,
    CognitiveStyle,
    FrictionProfile,
    HolisticProfile,
    PassionProfile,
    TaskSnapshot,
)
from agent_core.domain.pipeline_status import PipelineStatus
from agent_core.config_loader import DecisionConfig
from agent_core.services.canonical_memory import MemoryCorruptedError, MemoryState
from agent_core.services.claim_decision_gate import (
    build_claim_decision_gate,
    filter_message_for_claim_gate,
)
from agent_core.services.cognitive_router import CognitiveRouter, RoutePlan
from agent_core.services.decision_engine import DecisionEngine
from agent_core.services.hindsight_memory import build_memory_from_env
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.memory_injector import MemoryInjector
from agent_core.services.search_engine import SearchEngine
from agent_core.services.uncertainty_engine import UncertaintyEngine, UncertaintyReport
from agent_core.services.upstream_findings import classify_upstream_finding
from agent_core.services.vision_analyzer import VisionAnalyzer
from agent_core.shadow.shadow_executor import ShadowExecutor

class InsufficientEvidenceError(RuntimeError):
    pass

class VerifiedNote(BaseModel):
    note: str

class AgentTimeoutError(Exception):
    """[BOSS-8] Ajan kendi duvar saati sınırını aştı (ayrı terminal durum)."""


class ResumeBlockedError(RuntimeError):
    """[B0] Resume REDDEDİLDİ: bloklayan destek talebi hâlâ açık/doğrulanmadı.

    ``support_ids`` hangi taleplerin kapatılmadığını taşır (UI/API 409 için).
    """

    def __init__(self, task_id: str, support_ids):
        self.task_id = task_id
        self.support_ids = [str(s) for s in support_ids]
        super().__init__("RESUME_BLOCKED: " + ", ".join(self.support_ids))


class TaskStatus(TaskSnapshot):
    pass


# [FIX #3] Upstream bulgular bütçesi: downstream ajan promptlarına
# enjekte edilecek toplam metin ≤ bu kadar karakter. Bütçe aşılırsa
# EN ESKİ bulgu atılır (FIFO) — deterministik ve tahmin edilebilir.
UPSTREAM_FINDINGS_BUDGET_CHARS = 2000
CANONICAL_MESSAGE_CONTEXT_ENV = "PINEAL_ENABLE_CANONICAL_MESSAGE_CONTEXT"


def _canonical_message_context_enabled() -> bool:
    return os.getenv(CANONICAL_MESSAGE_CONTEXT_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _channel_from_engine(channel: str, scan: Any) -> Dict[str, Any]:
    """Tarayıcı/kapasite sonucunu kanal durumu sözlüğüne çevirir.

    [P0 · DENETİM 2026-10-16] Boş liste dönmek yerine "koştu / ÇALIŞMADI /
    hata" + sebep yazar.
    """
    from agent_core.domain.channel_status import from_engine_result

    return from_engine_result(channel, scan).to_dict()


def _append_upstream_finding(input_data: dict, agent: str, core: str) -> None:
    """Append only a bounded, explicitly classified inference core.

    Strategy, Verifier A, and unknown/untyped agent outputs remain in their
    own result records and are never copied into the shared prompt channel.
    """
    epistemic_type = classify_upstream_finding(agent)
    if epistemic_type != "inference":
        return

    findings = input_data.setdefault("_upstream_findings", [])
    findings.append(
        {
            "agent": agent,
            "core": core,
            "epistemic_type": epistemic_type,
            "verification_status": "unverified",
            "origin": "task_executor",
        }
    )
    total = sum(len(str(f.get("core", ""))) for f in findings if isinstance(f, dict))
    while len(findings) > 1 and total > UPSTREAM_FINDINGS_BUDGET_CHARS:
        dropped = findings.pop(0)
        if isinstance(dropped, dict):
            total -= len(str(dropped.get("core", "")))


class PinealExecutor:
    # v5.0 Agent Rack mapping - task_executor agent names to Agent Rack IDs
    # [FORENSIC RACK-WIRING] BİREBİR slot eşlemesi. Eskiden `shadow_executor`
    # DEPTH ANALYST slotunu, `pineal_7pillar` + `vision_analyzer` ise PATTERN
    # INTERRUPT slotunu boyuyordu (ödünç slot): o ajanların gerçek durumları
    # ekrandan izlenemiyor, bir ajanın aktivitesi başka ajanın slotunda
    # görünüyordu. Artık her yürütücü KENDİ slotunu boyar; yardımcılar
    # tracker'da kendi dinamik slotlarını açar, 12'li rafın slotlarını
    # ASLA ezmez.
    # (`resonance_calc` -> `resonance_calculator` gerçek bir 1:1 yeniden
    # adlandırmadır; o slota başka ajan yazmaz.)
    _AGENT_RACK_MAP = {
        "mirror_truth": "mirror_truth",
        "autonomous_verifier": "autonomous_verifier",
        "human_behavior": "human_behavior",
        "passion_mapper": "passion_mapper",
        "friction_detector": "friction_detector",
        "cognitive_profiler": "cognitive_profiler",
        "resonance_calc": "resonance_calculator",
        "pattern_interrupt": "pattern_interrupt",
        "osint_investigator": "osint_investigator",
        "authenticity_auditor": "authenticity_auditor",
        "depth_analyst": "depth_analyst",
        "resonance_synthesizer": "resonance_synthesizer",
        # [RÖNTGEN 2026-09-23] ÖDÜNÇ SLOT EŞLEMELERİ KALDIRILDI. Eski tabloda
        #   "shadow_executor": "depth_analyst",
        #   "pineal_7pillar":  "pattern_interrupt",
        #   "vision_analyzer": "pattern_interrupt",
        # satırları vardı: deterministik 7-sütun motoru koştuğunda ekranda
        # PATTERN INTERRUPT slotu READY yanıyor, görsel analizi de aynı slotu
        # boyuyor, shadow_executor ise DEPTH ANALYST slotunu kendi durumuyla
        # değiştiriyordu. Yani Agent Rack'teki durum, adını taşıdığı AJANA
        # izlenemiyordu (kullanıcının 3. talebinin ihlali). Slotu olmayan
        # adımlar None'a eşlenir: gerçek durumları olay akışında ve koşu
        # kayıtlarında (runs / War Room) yaşar, başka ajanın slotunu ÇALMAZ.
        "shadow_executor": None,
        "pineal_7pillar": None,
        "vision_analyzer": None,
    }

    def __init__(self, log_callback=None, emit_event_callback=None, snapshot_callback=None):
        self._log = log_callback or (lambda level, msg: None)
        self._emit = emit_event_callback or (lambda evt: None)
        self._snapshot_cb = snapshot_callback
        self.router = CognitiveRouter()
        self.memory = build_memory_from_env()
        self.injector = MemoryInjector()
        self.config = DecisionConfig.load()
        self.decision_engine = DecisionEngine(self.config)
        self.uncertainty = UncertaintyEngine()
        self.llm_gateway = LLMGateway()
        self.search_engine = SearchEngine()
        self.vision_analyzer = VisionAnalyzer(self.llm_gateway)
        self.agents = {
            "passion_mapper": PassionMapperAgent(self.llm_gateway),
            "friction_detector": FrictionDetectorAgent(self.llm_gateway),
            "cognitive_profiler": CognitiveProfilerAgent(self.llm_gateway),
            "resonance_synthesizer": ResonanceSynthesizerAgent(self.llm_gateway),
            "human_behavior": HumanBehaviorAnalyzer(),
            "mirror_truth": MirrorOfTruth(self.llm_gateway),
            "resonance_calc": ResonanceCalculator(),
            "pattern_interrupt": PatternInterrupt(),
            "autonomous_verifier": AutonomousVerifier(self.search_engine),
            "authenticity_auditor": AuthenticityAuditorAgent(self.llm_gateway),
            "osint_investigator": OsintInvestigatorAgent(self.llm_gateway),
            "shadow_executor": ShadowExecutor(llm_gateway=self.llm_gateway),
            "depth_analyst": DepthAnalyst(self.llm_gateway),
        }
        # [GÖLGE DENETİMİ 2026-10-24] Kapı TEK kaynaktan okunur (state.flag_enabled):
        # `1/true/yes/on` hepsi açık sayılır, `policy_state()` ile aynı gerçek.
        from agent_core.capabilities.state import flag_enabled as _flag_enabled
        if _flag_enabled("ENABLE_INTERPRETER"):
            self.agents["interpreter"] = InterpreterAgent(self.llm_gateway)
        # Agent Rack tracker - optional, graceful degrade
        self._agent_tracker = None
        try:
            from agent_core.services.agent_status_tracker import get_tracker
            self._agent_tracker = get_tracker()
        except Exception:
            self._agent_tracker = None

    def _rack_update(self, agent_name: str, status: str):
        """Agent Rack durum güncelle — sync wrapper for async tracker.

        Yalnız BİRE-BİR slotu olan görev ajanları yayınlar; ``None``'a eşlenen
        adımlar (7-sütun motoru, görsel analizi, shadow) hiçbir slotu
        boyayamaz. Rack'te görünen her durum, adını taşıyan ajanın kendi
        koşusundan gelmek zorundadır.
        """
        if agent_name in self._AGENT_RACK_MAP:
            rack_id = self._AGENT_RACK_MAP[agent_name]
            if rack_id is None:
                return
        else:
            # Tabloda olmayan gerçek görev ajanı (ör. interpreter, aspasia)
            # kendi kimliğiyle yayınlanır — ödünç slot yok.
            rack_id = agent_name
        if self._agent_tracker is None:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # [RÖNTGEN 2026-09-23] Çalışan event loop yok (CLI/senkron bağlam):
            # durum YAYINLANAMAZ. Eski kod burada `self._agent_tracker.statuses`
            # üzerinden senkron yazım deniyordu — ama tracker'ın alanı
            # `_statuses`'tur, yani o yedek DAL HİÇBİR ZAMAN ÇALIŞMADI (ölü
            # kod + sessiz yutma). Dürüst yol: yazamadığını söyle, uydurma.
            self._log(
                "DEBUG",
                f"Agent Rack: '{rack_id}' durumu yayınlanamadı (çalışan event loop yok)",
            )
            return
        try:
            loop.create_task(
                self._agent_tracker.update_status(rack_id, status, {"task_agent": agent_name})
            )
        except Exception as exc:
            self._log("WARNING", f"Agent Rack güncellenemedi ({rack_id}): {exc}")

    @staticmethod
    def _finding_core(result: Any, limit: int = 280) -> str:
        """[FIX #3] Ajan çıktısından deterministik kanıt çekirdeği üretir.

        Uzun string değerler (≥12 karakter — enum/ID gibi kısa alanlar
        gürültüdür) " | " ile birleştirilir ve `limit`'e kesilir.
        Boşsa "" döner (enjeksiyon yapılmaz → eski davranış korunur).
        """
        if result is None:
            return ""
        dump = result.model_dump() if hasattr(result, "model_dump") else result
        if not isinstance(dump, dict):
            return ""
        parts: List[str] = []
        for v in dump.values():
            if isinstance(v, str) and len(v) >= 12:
                v = v.strip()
                if v:
                    parts.append(v)
        return " | ".join(parts)[:limit]

    # [RÖNTGEN 2026-09-23 / SAHİP KARARI §8.7] Kanıt mührünün (SHA-256)
    # girdisinden ÇIKARILAN duvar saati alanları. Ölçülen eski kusur:
    # `computed_at` (ve benzerleri) hash'e girdiği için AYNI kanıt koşudan
    # koşuya farklı mühür üretiyordu — yani mühür tekrar-üretilemiyordu ve
    # bağımsız doğrulama/yeniden-üretim karşılaştırması yapılamıyordu.
    # Mühür artık KANITIN KİMLİĞİDİR: aynı kanıt → aynı mühür.
    # Zaman damgası KAYBOLMAZ, yalnız mühür girdisinden çıkar: koşu kaydında
    # (`AgentRun.started_at/completed_at`) ve olay zamanında ayrıca taşınır.
    _WALL_CLOCK_FIELDS = frozenset({
        "computed_at", "created_at", "updated_at", "generated_at",
        "measured_at", "observed_at", "started_at", "completed_at",
        "timestamp", "ts", "time", "date",
    })

    @classmethod
    def _seal_payload(cls, result: Any) -> Dict[str, Any]:
        """Mühür girdisi: kanıt alanları (duvar saati alanları iç içe dahil çıkarılır)."""
        dump = result.model_dump() if hasattr(result, "model_dump") else result
        if not isinstance(dump, dict):
            return {}

        def _strip(node: Any) -> Any:
            if isinstance(node, dict):
                return {
                    k: _strip(v) for k, v in node.items()
                    if k not in cls._WALL_CLOCK_FIELDS
                }
            if isinstance(node, list):
                return [_strip(v) for v in node]
            return node

        return _strip(dump)

    @classmethod
    def _hash_evidence_result(cls, result: BaseModel) -> str:
        """Canonical SHA-256 hash for a single typed agent result.

        TEKRAR-ÜRETİLEBİLİR: duvar saati alanları mühür girdisinde değildir
        (`_WALL_CLOCK_FIELDS`, sahip kararı §8.7). Aynı kanıt → aynı mühür;
        farklı kanıt → farklı mühür.
        """
        import hashlib
        import json
        canonical = json.dumps(
            cls._seal_payload(result), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # LLM çağrısı yapmayan tamamen deterministik ajanlar. Bu listede olmayan
    # bir ajanın sonucu data_confidence ile kanıtlanmıyorsa UI'da "LLM"
    # rozeti gösterilemez; "kaynak belirsiz" olarak işaretlenir.
    _DETERMINISTIC_AGENTS = frozenset({"resonance_calc"})

    @contextmanager
    def _capture_llm_calls(self, task_id: str, agent_id: str) -> Iterator[Any]:
        """Use gateway task-local capture, with a no-op scope for test doubles."""
        capture = getattr(type(self.llm_gateway), "capture_calls", None)
        if callable(capture):
            with capture(self.llm_gateway, task_id, agent_id) as scope:
                yield scope
            return
        yield SimpleNamespace(records=[], call_ids=[])

    @staticmethod
    def _attach_vector_calls(run: Any, records: list[dict[str, Any]] | None) -> None:
        """[BOSS-6] Authentic-vector LLM çağrılarını koşu kaydına bağlar.

        Bu çağrılar (tier=1, "asla kibar olma" promptu) görev başına 2 adettir ve
        önceden hiçbir telemetride görünmüyordu: harcama vardı, iz yoktu. Kayıtlar
        `run.output_summary["_aux_llm_calls"]` altında (kanıt kaydında
        `aux_llm_calls` olarak) tutulur; `run.call_ids` yalnız ajanın kendi
        çağrılarını taşır — sözleşme bozulmaz.
        """
        if not records:
            return
        summary = getattr(run, "output_summary", None)
        if not isinstance(summary, dict):
            summary = {}
            run.output_summary = summary
        bucket = summary.setdefault("_aux_llm_calls", [])
        bucket.extend(record.copy() for record in records)
        # DİKKAT: run.call_ids'e EKLENMEZ. O alan "bu ajanın kendi çağrıları"
        # sözleşmesidir ve kanıt kaydı + mühür + provenance ile birebir eşleşir
        # (uçtan uca kilit: tests/e2e/test_cross_stack_runtime.py). Yardımcı
        # harcamanın izi `_aux_llm_calls` + kanıt kaydındaki `aux_llm_calls`tır.

    @staticmethod
    async def _bounded(coro, limit: float, label: str):
        """[BOSS-8] Herhangi bir ajan çağrısını duvar saati sınırıyla koşar."""
        import asyncio as _asyncio

        if not limit or limit <= 0:
            return await coro
        try:
            return await _asyncio.wait_for(coro, timeout=limit)
        except TimeoutError as exc:
            raise AgentTimeoutError(f"{label} {limit:g}s sınırını aştı") from exc

    @staticmethod
    def _agent_takes_full_signature(agent: Any) -> bool:
        """``agent.execute`` ``(input_data, memory, gateway)`` imzasını kabul ediyor mu?

        [AUDIT 2026-10-07 · Madde 5] ESKİ YÖNTEM (kusur)::

            try:
                return await agent.execute(input_data, memory, gateway)
            except TypeError:
                return await agent.execute(input_data)

        Bu bir "imza pazarlığı" gibi görünüyordu, ama ``TypeError``
        YALNIZCA "yanlış argüman sayısı" demek değildir: ajanın GÖVDESİNDEKİ
        gerçek bir hatadan da gelir (``None + 1``, beklenmeyen tipte LLM
        yanıtının açılması, hatalı sözlük erişimi...). O durumda eski kod
        ajanı **İKİNCİ KEZ** koşturuyordu:

          * Yan etkiler TEKRAR tetiklenirdi — ücretli LLM çağrıları, ağ
            istekleri, kanıt/kayıt yazımları bir kez daha yapılırdı.
          * Asıl hata MASKELENİRDİ: kullanıcı "execute() missing 2 required
            positional arguments" gibi aldatıcı bir mesajla, gerçek
            hatanın izini süremeden baş başa kalırdı.
          * Maskeleme, 1 argümanlı ajanlarda ikinci çağrının da patlaması
            anlamına geldiğinden görev yine başarısız oluyor, ama iki katı
            maliyetle ve yanlış teşhisle.

        Yeni yöntem: imza, ajanı ÇALIŞTIRMADAN ``inspect.signature`` ile
        okunur. Ajan TAM BİR KEZ koşar; gövdeden gelen TypeError olduğu
        gibi yükselir.

        Returns:
            ``True`` -> tam imzayla (3 konumsal argüman) çağır.
            ``False`` -> yalnızca ``input_data`` ile çağır.
        """
        try:
            parameters = inspect.signature(agent.execute).parameters
        except (TypeError, ValueError):
            # İmza okunamıyor (C uzantısı, egzotik çağrılabilir, Mock
            # davranışı): baskın sözleşme olan tam imzayı dene.
            return True

        kinds = [parameter.kind for parameter in parameters.values()]
        if inspect.Parameter.VAR_POSITIONAL in kinds:
            return True  # *args var: her iki çağrı biçimini de yer.

        positional = sum(
            1
            for kind in kinds
            if kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return positional >= 3

    @staticmethod
    async def _execute_with_timeout(agent: Any, input_data: Dict[str, Any], memory: Any,
                                    gateway: Any, limit: float):
        """[BOSS-8] Ajanı ajan-başı duvar saati sınırıyla koşar.

        `limit <= 0` ise sınır yoktur (eski davranış). Süre aşımı DİĞER
        hatalardan ayrı raporlanır: hangi ajanın bütçeyi yediği görünür olur
        ve görev, tüm emeği çöpe atan bir "baştan koş" turuna girmez.

        [AUDIT 2026-10-07 · Madde 5] İmza, ÇAĞIRMADAN (inspect ile) okunur.
        Ayrıntı: :meth:`_agent_takes_full_signature`.
        """
        async def _call():
            # TEK koşu. TypeError burada yakalanMAZ: ajanın gövdesinden
            # gelen gerçek bir hata olduğu gibi yükselir, ajan ikinci kez
            # koşturulmaz (yan etki tekrarı + hata maskeleme kusuru).
            if PinealExecutor._agent_takes_full_signature(agent):
                return await agent.execute(input_data, memory, gateway)
            return await agent.execute(input_data)

        return await PinealExecutor._bounded(
            _call(), limit, f"{getattr(agent, 'AGENT_NAME', type(agent).__name__)} ajanı"
        )

    def _provenance_for(
        self,
        agent_name: str,
        result: Any,
        call_records: list[dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build output provenance only from records captured for this agent."""
        records = list(call_records or [])
        call_ids = [record["call_id"] for record in records if record.get("call_id")]
        fallback = getattr(result, "fallback_reason", None)
        data_confidence = getattr(result, "data_confidence", True)

        if data_confidence is False or fallback:
            return {
                "source": "fallback",
                "fallback_reason": fallback or "low_confidence",
                "call_ids": call_ids,
                "call_id": None,
                "model": None,
                "provider": None,
            }
        if agent_name in self._DETERMINISTIC_AGENTS:
            return {
                "source": "deterministic",
                "fallback_reason": None,
                "call_ids": call_ids,
                "call_id": None,
                "model": None,
                "provider": None,
            }

        successful = [record for record in records if not record.get("error")]
        if successful:
            selected = successful[-1]
            return {
                "source": "llm_cache" if selected.get("cache_hit") else "llm",
                "fallback_reason": None,
                "call_ids": call_ids,
                "call_id": selected.get("call_id"),
                "model": selected.get("model"),
                "provider": selected.get("provider"),
            }
        if records:
            selected = records[-1]
            return {
                "source": "llm_error",
                "fallback_reason": selected.get("error") or "llm_call_failed",
                "call_ids": call_ids,
                "call_id": selected.get("call_id"),
                "model": selected.get("model"),
                "provider": selected.get("provider"),
            }
        return {
            "source": "unknown",
            "fallback_reason": "no_llm_trace",
            "call_ids": [],
            "call_id": None,
            "model": None,
            "provider": None,
        }

    def _life_rupture_record(self, status: TaskStatus, input_data: dict) -> Dict[str, Any]:
        """Yaşam Kırılması katmanı: kişinin KENDİ geçmişine göre sapma kaydı.

        Panelin kuralları burada uygulanır:
          * kişiye özel kod yok — aynı fonksiyon her özne için koşar;
          * teşhis yok — rapor ``root_cause = UNKNOWN`` taşır;
          * fail-closed — analiz çökerse sessiz boşluk değil, "ölçülemedi"
            kaydı zincire düşer.

        Tam rapor (kanıt zaman çizelgesiyle) ZİNCİRE, hafif özet ANLIK
        GÖRÜNTÜYE yazılır: anlık görüntü her adımda yeniden serileştirilir,
        yüzlerce kanıt satırını oraya koymak durumu şişirirdi.
        """
        from datetime import datetime as _dt, timezone as _tz

        from agent_core.lifecycle.pipeline import analyze_life_rupture

        try:
            report = analyze_life_rupture(
                input_data.get("target_profile"),
                visual_evidence=input_data.get("visual_evidence"),
                frequency_map=status.frequency_map,
                strata_map=status.strata_map,
                subject_id=str(status.task_id),
            )
            payload = report.model_dump(mode="json")
        except Exception as error:  # noqa: BLE001 — fail-closed, kayıt zorunlu
            self._log(
                "WARNING",
                "[" + status.task_id + "] LIFE-RUPTURE ölçülemedi: " + type(error).__name__,
            )
            return {
                "agent": "life_rupture",
                "evidence_type": "life_rupture_report",
                "result": {
                    "schema_version": "life-rupture-v1",
                    "status": "unavailable",
                    "reason_code": type(error).__name__,
                    "root_cause": "UNKNOWN",
                },
                "timestamp": _dt.now(_tz.utc).isoformat(),
            }

        status.life_rupture = {
            key: payload.get(key)
            for key in (
                "schema_version", "status", "family_count", "families",
                "persistence_days", "cluster_window_start", "cluster_window_end",
                "medium_shift_rate", "confounded_axes", "root_cause",
                "prior_pillar_counts_toward_cluster", "evidence_entry_count",
                "summary", "machine_note", "falsification_checks",
            )
        }
        timeline = payload.get("evidence_timeline") or {}
        self._log(
            "INFO",
            "[" + status.task_id + "] LIFE-RUPTURE: " + str(payload.get("status"))
            + " · eksen=" + str(payload.get("family_count"))
            + " · kanıt=" + str(payload.get("evidence_entry_count")),
        )
        return {
            "agent": "life_rupture",
            "evidence_type": "life_rupture_report",
            "result": payload,
            "evidence_timeline_entry_count": len(timeline.get("entries") or []),
            "timestamp": _dt.now(_tz.utc).isoformat(),
        }

    def _snapshot(self, status: TaskStatus):
        cache_stats = self.llm_gateway.cache.stats() if hasattr(self.llm_gateway, "cache") else {}
        hits = cache_stats.get("hits", 0)
        hit_rate = cache_stats.get("hit_rate", "0.0%")

        budget_reader = getattr(type(self.llm_gateway), "budget_status", None)
        budget = budget_reader(self.llm_gateway) if callable(budget_reader) else {}
        real_cost = budget.get("spend_usd", getattr(self.llm_gateway, "spend_usd", None))
        if not isinstance(real_cost, (int, float)):
            real_cost = getattr(self.llm_gateway, "total_cost", 0.0)
        if not isinstance(real_cost, (int, float)):
            real_cost = 0.0
        reserved_cost = budget.get("reserved_usd", 0.0)
        active_reservations = budget.get("active_reservations", 0)

        # [034] fix: telemetri yalnızca GERÇEK gözlemlenebilirlerden oluşur.
        # - 'saved_llm_cost' varsayımsal $0.005/call sabitiyle uyduruluyordu;
        #   cache hit'leri model/fiyat bilgisi taşımadığı için kesin tasarruf
        #   hesaplanamaz -> hit sayısı dürüstçe raporlanır.
        # - 'decision_weight_updates' hiçbir ağırlık güncellemesi yapılmayan
        #   yolda ajan sayısını yanlış etiketliyordu -> gerçek LLM çağrı
        #   gözlem sayısı raporlanır (gateway call_log).
        call_log = getattr(self.llm_gateway, "call_log", None)
        memory_telemetry = {}
        memory_inspector = getattr(type(self.memory), "inspect_task_memory", None)
        if callable(memory_inspector):
            inspection = memory_inspector(self.memory, status.task_id)
            memory_telemetry["memory_state"] = inspection.get("state")
            if inspection.get("error_code"):
                memory_telemetry["memory_error_code"] = inspection["error_code"]

        status.telemetry = {
            **(status.telemetry or {}),
            **memory_telemetry,
            "cache_hit_rate": hit_rate,
            "cache_hits": hits if isinstance(hits, (int, float)) else 0,
            "llm_calls_observed": len(call_log) if isinstance(call_log, list) else 0,
            "total_llm_cost": f"${real_cost:.5f}",
            "llm_spend_usd": real_cost,
            "llm_reserved_spend_usd": reserved_cost,
            "llm_active_reservations": active_reservations,
        }
        
        if self._snapshot_cb:
            self._snapshot_cb(status)
            
    def _summarize_input(self, input_data: dict, agent_name: str) -> dict:
        profile = input_data.get("target_profile", {})
        if not isinstance(profile, dict):
            profile = {}
        # [P6 · CANLI PANEL] "Hangi ajan o anda nereyi kazıyor" bilgisi.
        # Önceden yalnız SAYI veriliyordu (bio_len/post_count) → canlı panelde
        # "hangi ajan hangi URL'de" sorusu CEVAPLANAMIYORDU. Burada yalnız
        # URL listesi (host+path) eklenir; profil İÇERİĞİ (bio/gönderi) eklenmez.
        urls: list[str] = []
        for key in ("detected_urls", "scraped_urls"):
            for url in profile.get(key) or []:
                text = str(url).strip()
                if text and text not in urls:
                    urls.append(text)
        return {
            "bio_len": len(profile.get("bio", "")),
            "post_count": len(profile.get("posts", [])),
            "has_images": bool(profile.get("images")),
            "has_mirror": "user_mirror" in input_data,
            "has_target_analysis": "target_analysis" in input_data,
            "urls": urls[:6],
            "url_count": len(urls),
        }

    def _recall_memory_crystal(self, task_id: str, input_data: dict, status: Any) -> str:
        """[FAZ B · B2/B3] Aynı hedefin GEÇMİŞİNİ kristalden çeker.

        Bu görevin kendi kanıtı HARİÇTIR (zaten elinde); yalnız önceki
        taramalardan kalan hatıralar getirilir. Hatıralar UNTRUSTED'dır:
        `recall_block` onları kafesler ve temizler — geçmiş bağlam TALİMAT
        değildir. Kristal yoksa boş metin döner (uydurma hatıra yok).
        """
        try:
            from agent_core.services import memory_crystal
            from agent_core.services.change_tracker import target_key

            profile = input_data.get("target_profile") or {}
            if not isinstance(profile, dict):
                profile = {}
            evidence = input_data.get("forensic_evidence") or []
            target = target_key(profile, evidence if isinstance(evidence, list) else [])
            if not target:
                return ""
            query = " ".join(
                str(profile.get(field) or "") for field in ("username", "name", "bio")
            ).strip() or target
            block = memory_crystal.recall_block(
                target,
                query,
                base=getattr(self.memory, "storage_path", None),
                exclude_task_id=str(task_id or ""),
            )
            result = memory_crystal.recall(
                target,
                query,
                base=getattr(self.memory, "storage_path", None),
                exclude_task_id=str(task_id or ""),
            )
            status.evidence_chain.append(
                {
                    "agent": "memory_crystal",
                    "evidence_type": "memory_recall",
                    "result": {
                        "schema_version": memory_crystal.SCHEMA_VERSION,
                        "target": target,
                        "available": result.available,
                        "reason": result.reason,
                        "recalled": len(result.hits),
                        "selected_fragment_ids": [hit.fragment_id for hit in result.hits],
                        "machine_note": result.machine_note,
                    },
                }
            )
            if result.available:
                self._log("INFO", f"[{task_id}] HAFIZA KRİSTALİ: {len(result.hits)} hatıra geri çağrıldı")
            return block
        except Exception as exc:  # hafıza asıl akışı asla bozmasın
            self._log("WARNING", f"[{task_id}] HAFIZA KRİSTALİ devre dışı: {type(exc).__name__}")
            return ""

    async def _download_images(self, urls: List[str]) -> List[str]:
        import asyncio

        def _write_file(content):
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(content)
            tmp.close()
            return tmp.name

        async def fetch_image(c, u):
            from agent_core.utils.security import safe_get

            try:
                r = await safe_get(c, u, max_redirects=3)
                r.raise_for_status()
                if len(r.content) > 8 * 1024 * 1024:
                    raise ValueError("IMAGE_TOO_LARGE")
                # Offload synchronous file I/O to a thread to avoid blocking the event loop
                return await asyncio.to_thread(_write_file, r.content)
            except Exception as e:
                self._log("WARNING", "Gorsel indirilemedi: " + type(e).__name__)
                return None

        # [E-GÖZ1-3] Tek sırt (egress) üzerinden paylaşımlı HTTP havuzu
        async with open_client(purpose="media", follow_redirects=False, timeout=15.0) as client:
            # [E7-muaf] `fetch_image` her istisnayı yakalar, loglar ve None
            # döner; kalan görsel yine indirilir (`paths` filtresi).
            results = await asyncio.gather(*(fetch_image(client, u) for u in urls[:2]))
        
        paths = [p for p in results if p is not None]
        return paths

    async def _deep_research(self, original_result: BaseModel, check, agent_name: str) -> VerifiedNote:
        """Request a separate review without changing the originating agent output."""
        prompt = (
            f"{agent_name} ajaninin onceki analizi supheli bulundu.\n"
            f"Suphe nedeni: {check.reason}\n"
            "Orijinal ajan ciktisi (degistirilemez kayit): " + original_result.model_dump_json() +
            "\nKurallar: 1) Emin degilsen 'bilmiyorum' de 2) Tahmin uretme "
            "3) Sadece verilen veriyi degerlendir 4) Orijinal analizi yeniden yazma; "
            "yalnizca dogrulama/degerlendirme notu ver."
        )
        verified = await self.llm_gateway.query(prompt, temperature=0.1, tier=1)
        return VerifiedNote(note=verified)

    @staticmethod
    def _resume_done(status: Any, agent_name: str) -> bool:
        """[RESUME] Bu ajan önceki koşuda tamamlanmış mı? (yan etki tekrarı yok)"""
        run = (getattr(status, "agent_runs", None) or {}).get(agent_name)
        return bool(run and run.status in {"completed", "completed_no_decision"})

    @staticmethod
    def _record_ingested(
        status: Any, agent_name: str, before: Dict[str, Any], input_data: Dict[str, Any]
    ) -> None:
        """[RESUME] Bu ajanın input_data'ya yuttuğu anahtarları kaydet."""
        chunk: Dict[str, Any] = {}
        for key, value in input_data.items():
            if key not in before or before[key] != value:
                chunk[key] = value
        if chunk:
            status.ingested_outputs[agent_name] = chunk

    def _request_support(
        self,
        status: Any,
        *,
        task_id: str,
        agent_name: str,
        reason: str,
        options: list[str],
        next_action: str,
        kind: str = "operator_response",
        blocks_resume: bool = False,
    ) -> dict:
        """[DESTEK AKIŞI] Destek talebini GERÇEKTEN oluşturur.

        Üç zorunlu bağlantı: (1) ``status.support_requests`` kaydı (sahipli),
        (2) ``AwaitingHumanEvent`` → backend ``sync_event`` → WS operatör
        olayı, (3) görünür WARNING logu. Sadece kayıt ALANI değil.
        """
        from agent_core.schemas.telemetry import AwaitingHumanEvent

        entry = {
            "support_id": f"sup_{task_id}_{len(status.support_requests) + 1}",
            "task_id": task_id,
            "agent_name": agent_name,
            "owner": agent_name,
            "reason": str(reason).replace("\n", " ")[:200],
            "options": list(options),
            "next_action": str(next_action)[:200],
            "status": "pending",
            # [B0] Talep TÜRÜ ve resume'u bloklayıp bloklamadığı ayrı ayrı
            # izlenir: birden fazla açık talep birbirine karışmaz; yalnız
            # ``blocks_resume`` talepleri kapana kadar resume engellenir.
            "kind": kind,
            "requires": (
                "vault_open" if kind == "vault_open"
                else "budget_authority" if kind == "spend_cap"
                else "operator_response"
            ),
            "blocks_resume": bool(blocks_resume),
            "responses": [],
            "approved": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        status.support_requests.append(entry)
        self._emit(AwaitingHumanEvent(
            task_id=task_id,
            agent_name=agent_name,
            reason=entry["reason"],
            options=list(options),
        ))
        self._log(
            "WARNING",
            f"[{task_id}] DESTEK TALEBİ: {agent_name} → {entry['reason']} "
            f"seçenekler={entry['options']} sonraki_adım={entry['next_action']}",
        )
        # Destek GÖRÜNÜR ve KALICI olsun: kayıt anında checkpoint'e yazılır
        # (snapshot kancası → backend/checkpoint_store); kritik yükselme anında
        # kayıt kaybolmaz.
        self._snapshot(status)
        return entry

    def _egress_slice(self, attempt_mark: int) -> list[str]:
        """[SORUMLULUK] Bu ajanın açtığı egress denemeleri (dürüst iz)."""
        try:
            attempts = egress_attempts()[attempt_mark:]
        except Exception:  # ölçüm arızası zinciri KIRMAZ ama kayıt düşer
            return []
        return [
            f"egress:{a.purpose}:{a.target}" if a.target else f"egress:{a.purpose}"
            for a in attempts
        ]

    @staticmethod
    def _next_agent_action(route: Any, agent_name: str) -> str:
        agents = list(getattr(route, "agents", None) or [])
        try:
            idx = agents.index(agent_name)
        except ValueError:
            return "pipeline_continue"
        if idx + 1 < len(agents):
            return f"next_agent:{agents[idx + 1]}"
        return "deferred_message_steps_or_finalize"

    def _responsibility_trail(
        self,
        *,
        agent_name: str,
        run: Any,
        claimed: str,
        attempted_paths: tuple | list = (),
        blockers: tuple | list = (),
        support_requested: tuple | list = (),
        missing: tuple | list = (),
        next_action: str | None = None,
        evidence_recorded: bool = True,
    ) -> dict:
        """[SORUMLULUK ZİNCİRİ] Ajan koşusunu mühürler.

        Mühür ``seal_trail`` kurallarını uygular: sahte başarı ve desteksiz
        pes GİZLENMEZ — ``integrity.violation`` alanına yazılır ve ERROR
        olarak izlenir; ``completed`` + eksik kanıt ``InsufficientEvidenceError``
        ile görevi durdurur (execütor çağrısında).
        """
        from agent_core.domain.responsibility import TaskContract, build_trail

        # [2026-10-23 · SORUMLULUK ZİNCİRİ] `TaskContract` üretimde HİÇ
        # kullanılmıyordu (yalnız testte). Silinmedi; mühürün parçası oldu:
        # her ajan koşusu için sözleşme kurulur ve zincire yazılır. Sözleşme
        # eksikse `ensure_complete` ValueError fırlatır — bu yüzden alanlar
        # koşunun GERÇEK durumundan türetilir, uydurulmuş kabul kriteri yok.
        _run_status = getattr(run, "status", None) or "unknown"
        contract = TaskContract.for_agent(
            task_id=str(getattr(run, "task_id", "") or "task"),
            agent_id=agent_name,
            required_inputs=["task_payload"],
            acceptance_criteria=[f"ajan koşusu '{_run_status}' durumuyla kapandı"],
            evidence_output=["agent_run", "responsibility_trail"],
        )

        trail = build_trail(
            claimed=claimed,
            evidence_recorded=evidence_recorded,
            attempted_paths=[f"agent:{agent_name}", *attempted_paths],
            blockers=list(blockers),
            support_requested=list(support_requested),
            missing=list(missing),
            next_action=next_action,
            extra_integrity={
                "run_status": getattr(run, "status", None),
                "confidence": getattr(run, "confidence", None),
                "error_code": getattr(run, "error_code", None),
                # Sözleşme mühürde taşınır: hangi kriterlerle kapandığı görünür.
                "contract": contract.model_dump(mode="json"),
            },
        )
        if trail.integrity.get("violation"):
            self._log(
                "ERROR",
                f"SORUMLULUK İHLALİ: {agent_name} \u2192 {trail.integrity['violation']} "
                "(mühür reddetti; zincirde görünür)",
            )
        return trail.model_dump(mode="json")

    @staticmethod
    def _evidence_record(agent_name: str, result: BaseModel, *, evidence_type: str,
                         uncertainty=None, source_agent: str | None = None,
                         llm_calls: list | None = None,
                         aux_llm_calls: list | None = None) -> dict:
        """Build an auditable evidence entry while retaining its provenance."""
        record = {
            "agent": agent_name,
            "result": result.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence_type": evidence_type,
        }
        if source_agent is not None:
            record["source_agent"] = source_agent
        if uncertainty is not None:
            record["uncertainty"] = uncertainty.model_dump()
        if llm_calls is not None:
            # Records were captured in this agent's context-local scope. They
            # are already plain dictionaries and remain JSON serializable.
            record["call_ids"] = [call["call_id"] for call in llm_calls if call.get("call_id")]
            record["llm_calls"] = [call.copy() for call in llm_calls]
        if aux_llm_calls:
            # [BOSS-6] Ajanın KENDİ çağrıları (call_ids/llm_calls) ile executor'ın
            # o ajan adına yaptığı yardımcı çağrılar (ör. authentic vector) ayrı
            # alanda durur: `call_ids` = "bu ajan ne çağırdı" sözleşmesi korunur,
            # yardımcı harcama ise mühürde AÇIK bir adla görünür (eskiden hiç
            # görünmüyordu). Aynı kayıtlar run.output_summary["_aux_llm_calls"]'ta da var.
            record["aux_llm_calls"] = [call.copy() for call in aux_llm_calls]
        return record

    @staticmethod
    def _apply_claim_decision_gate(
        result: BaseModel,
        gate: dict | None,
    ) -> tuple[BaseModel, list[str]]:
        """Deterministically suppress output containing a fully linked blocked claim."""
        updates: dict[str, Any] = {}
        blocked_ids: list[str] = []
        for field in ("message", "suggested_opening_message"):
            value = getattr(result, field, None)
            if not isinstance(value, str) or not value:
                continue
            filtered, ids = filter_message_for_claim_gate(value, gate)
            if ids:
                updates[field] = filtered
                blocked_ids.extend(ids)

        blocked_ids = sorted(set(blocked_ids))
        if not blocked_ids:
            return result, []
        if hasattr(result, "data_confidence"):
            updates["data_confidence"] = False
        if hasattr(result, "fallback_reason"):
            updates["fallback_reason"] = "claim_gate_blocked_same_claim"
        if hasattr(result, "evidence_ids_used"):
            updates["evidence_ids_used"] = []
        return result.model_copy(update=updates), blocked_ids

    @staticmethod
    def _append_tier2_canonical_output(status: TaskStatus, agent_name: str, result: BaseModel) -> None:
        """Record only allowlisted, explicitly classified Tier-2 fields."""
        from agent_core.services.tier2_evidence_adapter import canonicalize_tier2_output

        items = canonicalize_tier2_output(agent_name, result)
        if not items:
            return
        status.evidence_chain.append(
            {
                "agent": "tier2_evidence_adapter",
                "source_agent": agent_name,
                "evidence_type": "tier2_canonical_output",
                "result": {
                    "schema_version": "tier2-evidence-adapter-v1",
                    "build_status": "ready",
                    "item_count": len(items),
                    "items": [item.model_dump(mode="json") for item in items],
                },
            }
        )

    @staticmethod
    def _refresh_internal_verification_checks(
        status: TaskStatus,
        input_data: Dict[str, Any],
    ) -> None:
        """Append Tier-2 observation integrity checks without widening prompts/timeline."""
        report = input_data.get("verifications")
        if not isinstance(report, dict):
            return

        tier2_items = []
        for record in status.evidence_chain:
            if (
                not isinstance(record, dict)
                or record.get("agent") != "tier2_evidence_adapter"
                or record.get("source_agent") != "human_behavior"
                or record.get("evidence_type") != "tier2_canonical_output"
            ):
                continue
            result = record.get("result")
            items = result.get("items") if isinstance(result, dict) else None
            if isinstance(items, list):
                tier2_items.extend(
                    item for item in items
                    if isinstance(item, dict) and item.get("epistemic_type") == "observation"
                )
        if not tier2_items:
            return

        check_input = dict(input_data)
        check_input["forensic_evidence"] = []
        check_input["canonical_observation_evidence"] = tier2_items
        checks, rejected = AutonomousVerifier._check_canonical_observations(check_input)
        serialized = [item.model_dump(mode="json") for item in checks]

        existing = report.get("canonical_observation_checks")
        existing = existing if isinstance(existing, list) else []
        seen_ids = {
            item.get("claim_id") for item in existing if isinstance(item, dict)
        }
        merged = list(existing)
        for item in serialized:
            if item["claim_id"] not in seen_ids:
                merged.append(item)
                seen_ids.add(item["claim_id"])
        report["canonical_observation_checks"] = merged
        report["rejected_canonical_observation_count"] = (
            int(report.get("rejected_canonical_observation_count") or 0) + rejected
        )

        for record in status.evidence_chain:
            if (
                isinstance(record, dict)
                and record.get("agent") == "autonomous_verifier"
                and record.get("evidence_type") == "agent_output"
                and isinstance(record.get("result"), dict)
            ):
                record["result"]["canonical_observation_checks"] = merged
                record["result"]["rejected_canonical_observation_count"] = report[
                    "rejected_canonical_observation_count"
                ]

        verifier_run = status.agent_runs.get("autonomous_verifier")
        if verifier_run is not None:
            provenance = verifier_run.output_summary.get("_provenance")
            verifier_run.output_summary = dict(report)
            if provenance is not None:
                verifier_run.output_summary["_provenance"] = provenance

    async def _merge_task_memory(self, task_id: str, status: Any) -> None:
        """[FAZ B · B7] Kanıtı HEDEF PROFİLİYLE birlikte kalıcı belleğe yazar.

        Değişim izleme (change_tracker) ve ilişki grafı görevin HEDEFİNİ
        bilmek zorundadır; eskiden bellek yalnız kanıt zincirini saklıyordu ve
        hedef sonradan okunamıyordu (aynı hedef iki farklı anahtarla
        kaydedilebiliyordu). Yazma asla görevi düşürmez.
        """
        profile = getattr(self, "_current_target_profile", None) or {}
        await self.memory.merge_evidence(
            task_id, status.evidence_chain, metadata={"target_profile": profile}
        )

    async def execute_task(
        self,
        input_data: Dict[str, Any],
        task_id: str,
        *,
        resume_from: Any = None,
    ) -> TaskStatus:
        """Public entry: impl'i saran güvenli yaşam döngüsü.

        ``resume_from`` (ek uyumlu): destek/güç sağlandıktan sonra ÖNCEKİ
        ``TaskStatus`` ile görev KALDIĞI YERDEN devam eder: tamamlanan
        ajanlar atlanır (yan etki tekrarı yok), yutulan çıktılar input_data'ya
        geri yüklenir, pending destek talepleri ``resolved`` işaretlenir.
        

        [035] fix: göreve ait geçici görseller başarı/halt/exception HER
        durumunda temizlenir; hedefin kişisel görselleri temp dizinde kalıcı
        artefakt olarak bırakılamaz (retention sözleşmesi).
        """
        try:
            if resume_from is not None:
                return await self._execute_task_impl(
                    input_data, task_id, resume_from=resume_from
                )
            return await self._execute_task_impl(input_data, task_id)
        except MemoryCorruptedError as exc:
            # A corrupt canonical record is not equivalent to an absent record.
            # Halt before further analysis and require explicit recovery.
            from agent_core.schemas.telemetry import ErrorHaltEvent, Severity

            now = datetime.now(timezone.utc)
            status = TaskStatus(
                task_id=task_id,
                status=PipelineStatus.HALTED_CRITICAL,
                created_at=now,
                completed_at=now,
                halted_reason=exc.error_code,
                telemetry={
                    "memory_initial_state": MemoryState.CORRUPTED.value,
                    "memory_state": MemoryState.CORRUPTED.value,
                    "memory_error_code": exc.error_code,
                    "memory_corruption_reason": exc.reason,
                },
            )
            self._log("ERROR", f"[{task_id}] {exc}")
            self._emit(ErrorHaltEvent(
                task_id=task_id,
                agent_name="CanonicalMemory",
                error_code=exc.error_code,
                error_message=f"Canonical memory requires explicit recovery ({exc.reason})",
                severity=Severity.Critical,
            ))
            self._snapshot(status)
            return status
        finally:
            self._cleanup_temp_images(input_data)

    def _cleanup_temp_images(self, input_data: Dict[str, Any]) -> None:
        import os
        for path in (input_data.pop("_downloaded_temp_images", None) or []):
            try:
                os.remove(path)
            except OSError:
                pass

    async def _execute_task_impl(
        self, input_data: Dict[str, Any], task_id: str, resume_from: Any = None
    ) -> TaskStatus:
        from agent_core.schemas.telemetry import (
            TaskStartedEvent, StepCompletedEvent, ErrorHaltEvent, TaskCompletedEvent, Severity
        )
        # [FAZ B · B7] Hedef profili bellek yazımlarında taşınır (değişim
        # izleme + ilişki grafı için kararlı hedef anahtarı).
        self._current_target_profile = input_data.get("target_profile") or {}
        status = TaskStatus(task_id=task_id, status="processing", created_at=datetime.now(timezone.utc))
        # [P0 · DENETİM 2026-10-16] Hedef kanal durumu (X sensörü, web araması,
        # Instagram kazıma...) görev payload'ından devralınır; görev içinde
        # koşan kanallar buna eklenir. Böylece "ÇALIŞMADI: sebep" telemetriye
        # ve UI'a taşınır.
        _inherited_channels = input_data.get("channel_status") or []
        if isinstance(_inherited_channels, list):
            status.channel_status = [c for c in _inherited_channels if isinstance(c, dict)]
        _task_wall_start = datetime.now(timezone.utc)

        # [RESUME · DESTEKLE DEVAM] Önceki koşudan devralma: tamamlanan
        # ajanlar & kanıtlar & yutulan çıktılar taşınır; destek talepleri
        # çözümlenir. Durum makinesi DEĞİŞMEZ (processing → ... aynı akış).
        if resume_from is not None:
            status.completed_agents = list(resume_from.completed_agents or [])
            status.agent_runs = dict(resume_from.agent_runs or {})
            status.evidence_chain = list(resume_from.evidence_chain or [])
            status.planned_agents = list(resume_from.planned_agents or [])
            status.resonance_score = resume_from.resonance_score
            status.ingested_outputs = {
                k: dict(v) for k, v in (resume_from.ingested_outputs or {}).items()
            }
            status.support_requests = [
                dict(r) for r in (resume_from.support_requests or [])
            ]
            # Döngü-dışı blokların (osint/depth/shadow/sütunlar) alanları da
            # devredilir — yeniden üretildiğinde aynı değere düşerdi.
            for _fld in (
                "osint_footprint", "depth_report", "psychodynamic_depth",
                "shadow_profile", "follower_audit", "timing_forensics",
                "holistic_profile", "frequency_map", "seismos_events",
                "void_map", "strata_map", "gravity_map", "pulse_map",
                "key_matrix", "visual_evidence",
            ):
                _prior = getattr(resume_from, _fld, None)
                if _prior is not None:
                    setattr(status, _fld, _prior)
            # [B0 · OTOMATİK KAPATMA YOK] Yalnızca İLGİLİ talebin
            # gerektirdiği destek SAĞLANMIŞ ve engel CANLI doğrulanmışsa o
            # talep kapanır; açık talepler ayrı ayrı izlenir. Bloklayan bir
            # talep hâlâ doğrulanmamışsa resume REDDEDİLİR.
            _resolved = 0
            _unresolved_blocking: list = []
            for _req in status.support_requests:
                if _req.get("status") != "pending":
                    continue
                _requires = _req.get("requires") or "operator_response"
                _kind = _req.get("kind") or "operator_response"
                _verified = False
                if _kind == "vault_open":
                    _state = getattr(self.search_engine, "_vault_state", None)
                    try:
                        _verified = bool(_state()) if callable(_state) else False
                    except Exception:
                        _verified = False
                elif _kind == "spend_cap":
                    try:
                        _budget = self.llm_gateway.budget_status()
                        _cap = float(_budget.get("cap_usd") or 0.0)
                        _verified = _cap <= 0 or (
                            float(_budget.get("spend_usd") or 0.0)
                            + float(_budget.get("reserved_usd") or 0.0)
                            < _cap
                        )
                    except Exception:
                        _verified = False
                else:
                    _verified = bool(_req.get("approved")) and bool(
                        _req.get("responses")
                    )
                if _verified:
                    _req["status"] = "resolved"
                    _req["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    _req["resolution"] = f"verified_{_requires}"
                    _resolved += 1
                elif _req.get("blocks_resume"):
                    _unresolved_blocking.append(
                        str(_req.get("support_id") or _req.get("agent_name") or "?")
                    )
            for _agent, _chunk in status.ingested_outputs.items():
                input_data.update(_chunk)
            self._log(
                "WARNING",
                f"[{task_id}] RESUME: {len(status.completed_agents)} tamamlanmış ajan devralındı, "
                f"{_resolved} destek doğrulandı/kapandı, "
                f"{len(_unresolved_blocking)} bloklayan talep açık — "
                "görev kaldığı yerden sürüyor.",
            )
            if _unresolved_blocking:
                raise ResumeBlockedError(task_id, _unresolved_blocking)

        # Only concrete memory engines participate in the health contract; test
        # doubles without the method retain their existing behavior.
        inspector = getattr(type(self.memory), "inspect_task_memory", None)
        if callable(inspector):
            memory_inspection = inspector(self.memory, task_id)
            memory_state = memory_inspection.get("state", MemoryState.CORRUPTED.value)
            status.telemetry = {
                "memory_initial_state": memory_state,
                "memory_state": memory_state,
            }
            if memory_state == MemoryState.CORRUPTED.value:
                profile_file = self.memory._profile_file(task_id)
                raise MemoryCorruptedError(
                    task_id,
                    memory_inspection.get("reason") or "UNKNOWN",
                    profile_file,
                )

        # Cross-agent findings are task-local executor output. Do not trust a
        # caller-supplied raw list as a typed source or prompt context.
        input_data["_upstream_findings"] = []
        input_data.pop("message_evidence_context", None)
        # Verification outputs and their downstream gate are executor-owned;
        # never accept a caller-injected claim verdict as a message veto.
        input_data.pop("verifications", None)
        input_data.pop("claim_gate", None)
        input_data["forensic_evidence"] = []
        input_data["forensic_evidence_status"] = "unavailable"
        input_data["evidence_timeline"] = EvidenceTimeline().model_dump(mode="json")
        input_data["evidence_timeline_status"] = "unavailable"
        input_data["sacred_rules"] = self.injector.fetch_active_rules()
        # The shared diagnostic call log is intentionally not cleared here.
        # Concurrent tasks bind records through per-agent context-local scopes.

        # Deterministik Takipçi ve Zamanlama Forensiği
        try:
            from agent_core.services.follower_audit import audit_followers
            from agent_core.services.timing_forensics import analyze_timing
            tp_info = input_data.get("target_profile", {})
            # Canonical platform payload uses followers/following; accept the
            # scraper model spellings too. Missing counts remain None (never 0).
            fol_cnt = tp_info.get("followers")
            if fol_cnt is None:
                fol_cnt = tp_info.get("follower_count")
            # [024] fix: following=None "ölçülmedi" demektir; 0'a çevrilmez.
            fing_cnt = tp_info.get("following")
            if fing_cnt is None:
                fing_cnt = tp_info.get("following_count")
            # [027] fix: sahte 1-post sentinel'i kaldırıldı. Boş posts_meta
            # olduğu gibi iletilir; audit "İncelenen Post: 0" der, 1 demez.
            posts_meta = tp_info.get("posts_meta") or []
            audit_res = audit_followers(fol_cnt, fing_cnt, posts_meta)
            input_data["follower_audit"] = audit_res.model_dump()
            status.follower_audit = audit_res.model_dump()
            self._log("INFO", f"[{task_id}] TAKİPÇİ DENETİMİ: {audit_res.verdict.upper()}")
            
            p_times = tp_info.get("post_times", [])
            # GÖREV 2.2: hizali sayimlar yorungeye hiz-sinyali olarak verilir.
            t_res = analyze_timing(p_times, engagement=posts_meta)
            if t_res:
                input_data["timing_forensics"] = t_res
                status.timing_forensics = t_res
                # W1: timing_forensics'in GERCEK alanlari (night_share, peak_hour,
                # median_drift_hours) okunur; olmayan alanlarla %0 gosterilmez.
                gece = int(t_res.get("night_share", 0) * 100)
                tepe = str(t_res.get("peak_hour", "--"))
                kayma = t_res.get("median_drift_hours", 0)
                kayma_str = f"+{kayma:.1f}sa" if kayma >= 0 else f"{kayma:.1f}sa"
                self._log("INFO", f"[{task_id}] ZAMAN FORENSİĞİ: gece %{gece} | tepe {tepe} | kayma {kayma_str}")
        except Exception as e:
            self._log("WARNING", f"[{task_id}] Forensik veri analizi uyarısı: {e}")

        raw_imgs = input_data.get("target_profile", {}).get("images", [])
        if raw_imgs and isinstance(raw_imgs, list) and len(raw_imgs) > 0 and isinstance(raw_imgs[0], str) and raw_imgs[0].startswith("http"):
            self._log("INFO", f"[{task_id}] MULTIMODAL VISION: {len(raw_imgs)} fotoğraf görsel zeka ile inceleniyor...")
            self._rack_update("vision_analyzer", "active")
            try:
                target_bio = input_data.get("target_profile", {}).get("bio", "")
                with self._capture_llm_calls(task_id, "vision_analyzer") as vision_scope:
                    visual_ev = await self.vision_analyzer.analyze_images(raw_imgs, target_context=target_bio)
                input_data["visual_evidence"] = visual_ev.model_dump()
                status.visual_evidence = visual_ev.model_dump()
                status.visual_evidence["_provenance"] = self._provenance_for(
                    "vision_analyzer", visual_ev, vision_scope.records
                )
                self._log("INFO", f"[{task_id}] GÖRSEL KANIT: {visual_ev.visual_evidence_summary}")
                self._rack_update("vision_analyzer", "ready")
                # [FIX #3] Görsel kanıtları upstream bütçesine ekle.
                _core = self._finding_core(visual_ev)
                if _core:
                    _append_upstream_finding(input_data, "vision_analyzer", _core)
            except Exception as e:
                self._rack_update("vision_analyzer", "wait")
                self._log("WARNING", f"[{task_id}] Vision analizi atlandı: {str(e)[:80]}")

        # [FIX #1] OSINT DISCOVERY FAZINA TAŞINDI. Eski konum tüm ajan
        # loop'unun SONUNDAydı: (a) çıktı input_data'ya yazılmadığı
        # için hiçbir ajan onu kullanamıyordu, (b) derinlik motoru
        # zaten bitmişti — bulgu KULLANILMADI. Şimdi discovery'de koşar;
        # input_data["public_osint"] derinlik motorunu ve ajan
        # promptlarını besler. Ajan username/name sürücülüdür (ilk veri
        # gerektirmez), taşımak güvenli.
        _tp = input_data.get("target_profile", {}) or {}
        if (_tp.get("username") or _tp.get("name")) and not self._resume_done(
            status, "osint_investigator"
        ):
            self._rack_update("osint_investigator", "active")
            try:
                with self._capture_llm_calls(task_id, "osint_investigator") as osint_scope:
                    osint_result = await self.agents["osint_investigator"].execute(input_data)
                status.osint_footprint = osint_result.model_dump() if hasattr(osint_result, "model_dump") else osint_result
                status.osint_footprint["_provenance"] = self._provenance_for(
                    "osint_investigator", osint_result, osint_scope.records
                )
                data_conf = getattr(osint_result, "data_confidence", True)
                fallback = getattr(osint_result, "fallback_reason", None)
                # [P0 · DENETİM 2026-10-16] OSINT kanallarının (maigret/holehe)
                # koşu durumu görev telemetrisine yazılır: "koştu" / "ÇALIŞMADI
                # (sebep)" / "hata". "Bulunamadı" ile "hiç çalışmadı" ayrımı
                # buradan okunur. Kanal görevin parçası DEĞİLSE satır yazılmaz
                # (olmayan kanal "koşmadı" diye raporlanmaz).
                _osint_channels = []
                _username_scan = status.osint_footprint.get("username_scan")
                if _username_scan is not None:
                    _osint_channels.append(
                        _channel_from_engine("sensor.identity.maigret", _username_scan)
                    )
                _email_scan = status.osint_footprint.get("email_scan")
                if _email_scan is not None:
                    _osint_channels.append(
                        _channel_from_engine("sensor.identity.holehe", _email_scan)
                    )
                status.channel_status = list(status.channel_status or []) + _osint_channels
                status.agent_runs["osint_investigator"] = AgentRun(
                    task_id=task_id, agent_name="osint_investigator", status="completed",
                    started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                    output_summary=status.osint_footprint, call_ids=list(osint_scope.call_ids),
                    confidence=(
                        getattr(osint_result, "confidence", None)
                        if data_conf and isinstance(getattr(osint_result, "confidence", None), (int, float))
                        else None
                    ),
                    warnings=[] if data_conf else [fallback or "data_unavailable"],
                )
                # [FIX #1] Çıktı ARTIK KULLANILIYOR: derinlik motoru +
                # ajan promptları okuyabilir.
                input_data["public_osint"] = status.osint_footprint
                self._log("INFO", f"[{task_id}] DİJİTAL AYAK İZİ: Platform varlık skorlaması yapıldı (discovery)")
                self._rack_update("osint_investigator", "ready")
                # [FIX #3] OSINT bulgusunu upstream bütçesine ekle.
                _core = self._finding_core(osint_result)
                if _core:
                    _append_upstream_finding(input_data, "osint_investigator", _core)
            except Exception as e:
                self._rack_update("osint_investigator", "wait")
                status.agent_runs["osint_investigator"] = AgentRun(
                    task_id=task_id, agent_name="osint_investigator", status="failed",
                    started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                    error_message=str(e)[:200],
                )
                self._log("WARNING", f"[{task_id}] OSINT taraması atlandı: {e}")

        # [P1 · DERİN PROFİL ÇÖZÜMLEME] detected_urls yetenek omurgasına bağlanır.
        # KOŞUM TEK YERDE: `deep_profile_resolver` → `profile_router` (saf
        # sınıflandırma) → `CapabilityRunner` (kapılar, çocuk kilidi, timeout).
        # API katmanı yalnız adresleri taşır; ikinci bir koşum yolu açılsaydı
        # aynı yetenek iki kez çağrılırdı.
        _deep_items: list[Any] = []
        # [2026-10-23 · KABLO] Instagram bio linkleri (`external_urls`),
        # X gönderi metinlerindeki adresler ve OSINT yoklaması bulguları TEK
        # fonksiyonda birleşir. Kural (yalnız `classify_url.runnable`) ve
        # üst sınır orada; burası yalnız taşır.
        from agent_core.services.deep_url_cables import merge_detected_profile_urls

        _detected_urls = merge_detected_profile_urls(
            input_data.get("target_profile"), status.osint_footprint
        )
        if _detected_urls:
            input_data.setdefault("target_profile", {})["detected_urls"] = list(_detected_urls)
            try:
                from agent_core.services.deep_profile_resolver import (
                    resolve_deep_profiles_detailed,
                )
                _resolution = await resolve_deep_profiles_detailed(
                    _detected_urls, payload=input_data
                )
                _deep_items = list(_resolution.items)
                if _resolution.channel_runs:
                    _cur_channels = [c for c in (status.channel_status or []) if (c.get("channel") if isinstance(c, dict) else getattr(c, "channel", "")) != "profile.deep_scan"]
                    status.channel_status = _cur_channels + [c.to_dict() if hasattr(c, "to_dict") else c for c in _resolution.channel_runs]
                _tp = input_data.setdefault("target_profile", {})
                if _resolution.identities:
                    _tp["socid_identities"] = _resolution.identities
                # [P1] KAZANAN ALAN DEFTERİ: hangi profil tarandı, kaç gönderi
                # geldi, neden koşmadı. UI rozeti bu defterden okur.
                _tp["scanned_urls"] = list(_resolution.scanned_urls)
                _tp["scanned_profiles"] = dict(_resolution.profiles)
                self._log(
                    "INFO",
                    f"[{task_id}] DERİN PROFİL: {len(_resolution.scanned_urls)} profil tarandı, "
                    f"{len(_resolution.identities)} kimlik kaydı, {len(_deep_items)} kanıt",
                )
            except Exception as _d_exc:
                self._log("WARNING", f"[{task_id}] Derin profil çözümleme atlandı: {_d_exc}")

        # [P2 · ÇAPRAZ PROFİLLEME] Farklı platform hesaplarını deterministik eşleştirir
        _cross_items: list[Any] = []
        try:
            from agent_core.services.cross_profiler import correlate_profiles
            _corr = correlate_profiles(
                input_data.get("target_profile"),
                status.osint_footprint or input_data.get("public_osint"),
            )
            _cross_items = _corr.items
            if _corr.matches:
                _matches = [m.model_dump() for m in _corr.matches]
                input_data["cross_profile_matches"] = _matches
                # [P2] Eşleşmeler hedef profilin içinde de taşınır: UI rozeti
                # "kapsam" etiketiyle okur (olasılık olarak sunulmaz).
                _tp2 = input_data.setdefault("target_profile", {})
                _tp2["cross_profile_matches"] = _matches
                self._log("INFO", f"[{task_id}] ÇAPRAZ PROFİL: {len(_corr.matches)} platform hesabı eşleştirildi")
        except Exception as _c_exc:
            self._log("WARNING", f"[{task_id}] Çapraz profilleme atlandı: {_c_exc}")

        # GÖREV 2.3/2.4: psikodinamik derinlik motoru (deterministik).
        # Metin yoksa agirlik otomatik gorsel+zamansala kayar; motor ASLA
        # halt etmez (hic kanal yoksa no_evidence verdict'i doner).
        self._rack_update("depth_analyst", "active")
        try:
            from agent_core.services.psychodynamic_depth import analyze_depth
            depth_res = analyze_depth(input_data)
            input_data["psychodynamic_depth"] = depth_res
            status.psychodynamic_depth = depth_res
            _dw = depth_res.get("epistemic_weights", {})
            self._log(
                "INFO",
                f"[{task_id}] DERİNLİK MOTORU: {depth_res.get('verdict')} "
                f"guven={depth_res.get('confidence')} "
                f"telafi={depth_res.get('compensation_index')} "
                f"reaksiyon={depth_res.get('reaction_formation_index')}"
            )
            self._rack_update("depth_analyst", "ready")
        except Exception as e:
            self._rack_update("depth_analyst", "wait")
            self._log("WARNING", f"[{task_id}] Derinlik motoru atlandı: {str(e)[:80]}")

        # HÜKÜM-MÜHÜR: derinlik özeti kanonik kanıta yazılır (salt-okur
        # Aspasia okuması için). evidence_type forensic_digest ->
        # overall_confidence hesabına KATILMAZ (sayı şişirmez).
        try:
            _depth_doc = input_data.get("psychodynamic_depth")
            if isinstance(_depth_doc, dict) and _depth_doc.get("verdict") == "ok":
                status.evidence_chain.append({
                    "agent": "psychodynamic_depth",
                    "evidence_type": "forensic_digest",
                    "result": {"depth": _depth_doc,
                               "confidence": _depth_doc.get("confidence")},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provenance": {"engine": "psychodynamic_depth",
                                   "deterministic": True},
                })
        except Exception as e:
            self._log("WARNING", f"[{task_id}] Derinlik kanıtı yazılamadı: {str(e)[:80]}")

        imgs = input_data.get("target_profile", {}).get("images", [])
        if imgs and isinstance(imgs[0], str) and imgs[0].startswith("http"):
            downloaded = await self._download_images(imgs)
            input_data["target_profile"]["images"] = downloaded
            # [035] fix: task bitince (her çıkış yolunda) silinecekleri kaydet.
            input_data["_downloaded_temp_images"] = downloaded
            # GÖREV 2 artığı: PIL varsa sahneleme doygunluğu yerel
            # dosyalardan ölçülür (yoksa None+not aynen kalır).
            try:
                _depth = input_data.get("psychodynamic_depth")
                if isinstance(_depth, dict):
                    from agent_core.services.psychodynamic_depth import measure_saturation
                    _sat = measure_saturation(downloaded)
                    if _sat.get("mean_saturation") is not None:
                        _sig = (_depth.get("channels") or {}).get("staging", {})
                        _sig = (_sig or {}).get("signals", {})
                        if isinstance(_sig, dict):
                            _sig["color_saturation"] = _sat["mean_saturation"]
                            _sig["saturation_note"] = _sat["note"]
                            status.psychodynamic_depth = _depth
            except Exception as e:
                self._log("WARNING", f"[{task_id}] Doygunluk ölçümü atlandı: {str(e)[:80]}")

        # --- PINEAL DETERMINISTIC 7-PILLAR ---
        # Internal evidence carriers were reset at task start; the canonical
        # list and neutral timeline are rebuilt from this typed pillar bundle.
        pillar_start = datetime.now(timezone.utc)
        self._log("INFO", f"[{task_id}] 7-PILLAR analizi başlatılıyor...")
        self._rack_update("pineal_7pillar", "active")
        try:
            from agent_core.engines.pillar_orchestrator import PillarOrchestrator

            # [BOSS-8] Deterministik motor da ajan-başı sınırla koşar: takılan
            # bir motor görev bütçesini yiyip görevi baştan başlatamaz.
            pillar_fields = await self._bounded(
                PillarOrchestrator().run(input_data),
                self.config.get_agent_config("pineal_7pillar").timeout_seconds,
                "pineal_7pillar",
            )
            for field in (
                "frequency_map", "seismos_events", "void_map", "strata_map",
                "gravity_map", "pulse_map", "key_matrix", "pillar_bundle",
            ):
                setattr(status, field, pillar_fields.get(field))
            input_data["pillar_bundle"] = pillar_fields.get("pillar_bundle")
            # B1/B2: preserve typed pillar outputs. B3 builds a neutral,
            # sourced timeline; neither representation is injected into prompts.
            adapter_record = None
            timeline_record = None
            try:
                from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle

                # [P1 · 2026-10-16] Derin tarama ve çapraz profilleme
                # kanıtları adaptörün `extra_items` kanalıyla kanonik kanıt
                # zincirine girer (pillar paketi boş olsa bile kanıt kaybolmaz).
                canonical_items = adapt_pillar_bundle(
                    input_data["pillar_bundle"],
                    target_profile=input_data.get("target_profile"),
                    extra_items=[*_deep_items, *_cross_items],
                )
                input_data["forensic_evidence"] = [
                    item.model_dump(mode="json") for item in canonical_items
                ]
                input_data["forensic_evidence_status"] = "ready" if canonical_items else "empty"
                adapter_record = {
                    "agent": "pillar_evidence_adapter",
                    "evidence_type": "canonical_evidence",
                    "result": {
                        "schema_version": "evidence-item-v1",
                        "build_status": input_data["forensic_evidence_status"],
                        "item_count": len(canonical_items),
                        "items": input_data["forensic_evidence"],
                    },
                }
                try:
                    from agent_core.services.evidence_timeline import build_evidence_timeline

                    timeline = build_evidence_timeline(canonical_items)
                    timeline_entries = (
                        timeline.entries if timeline.rejected_item_count == 0 else []
                    )
                    timeline_payload = timeline.model_dump(mode="json")
                    if timeline.rejected_item_count:
                        timeline_payload["entries"] = []
                    input_data["evidence_timeline"] = timeline_payload
                    timeline_status = (
                        "failed"
                        if timeline.rejected_item_count
                        else "ready"
                        if timeline_entries
                        else "empty"
                    )
                    input_data["evidence_timeline_status"] = timeline_status
                    timeline_record = {
                        "agent": "evidence_timeline",
                        "evidence_type": "neutral_timeline",
                        "result": {
                            "schema_version": timeline.schema_version,
                            "source_status_note": timeline.source_status_note,
                            "build_status": timeline_status,
                            "entry_count": len(timeline_entries),
                            "excluded_strategy_count": timeline.excluded_strategy_count,
                            "rejected_item_count": timeline.rejected_item_count,
                            "entries": [
                                {
                                    "evidence_id": entry.evidence_id,
                                    "timeline_at": (
                                        entry.timeline_at.isoformat()
                                        if entry.timeline_at is not None
                                        else None
                                    ),
                                    "temporal_basis": entry.temporal_basis,
                                    "epistemic_type": entry.epistemic_type,
                                    "epistemic_note": entry.epistemic_note,
                                    "source_engine": entry.source_engine,
                                    "source_status": (
                                        entry.source_status.value
                                        if entry.source_status is not None
                                        else None
                                    ),
                                    "content": entry.content,
                                    "provenance_refs": entry.provenance_refs,
                                    "scope": entry.scope,
                                }
                                for entry in timeline_entries
                            ],
                        },
                    }
                except Exception as timeline_error:
                    input_data["evidence_timeline"] = EvidenceTimeline().model_dump(mode="json")
                    input_data["evidence_timeline_status"] = "failed"
                    timeline_record = {
                        "agent": "evidence_timeline",
                        "evidence_type": "execution_failure",
                        "result": {
                            "schema_version": "evidence-timeline-v1",
                            "build_status": "failed",
                            "error_code": "EVIDENCE_TIMELINE_FAILED",
                            "error_type": type(timeline_error).__name__,
                            "error_message": "Canonical evidence could not be ordered into a timeline.",
                        },
                    }
                    self._log(
                        "ERROR",
                        f"[{task_id}] Evidence timeline failed: {type(timeline_error).__name__}",
                    )
            except Exception as adapter_error:
                # Keep the successful engine run distinct from an adapter
                # contract failure. No malformed/partial evidence is handed on.
                input_data["forensic_evidence"] = []
                input_data["forensic_evidence_status"] = "failed"
                input_data["evidence_timeline"] = EvidenceTimeline().model_dump(mode="json")
                input_data["evidence_timeline_status"] = "unavailable"
                timeline_record = {
                    "agent": "evidence_timeline",
                    "evidence_type": "not_built",
                    "result": {
                        "schema_version": "evidence-timeline-v1",
                        "build_status": "unavailable",
                        "reason_code": "CANONICAL_EVIDENCE_UNAVAILABLE",
                    },
                }
                adapter_record = {
                    "agent": "pillar_evidence_adapter",
                    "evidence_type": "execution_failure",
                    "result": {
                        "schema_version": "evidence-item-v1",
                        "build_status": "failed",
                        "error_code": "EVIDENCE_ADAPTER_FAILED",
                        "error_type": type(adapter_error).__name__,
                        "error_message": "Pillar bundle did not match the canonical evidence contract.",
                    },
                }
                # Do not echo a validation exception: it may contain rejected
                # input values from the target profile.
                self._log(
                    "ERROR",
                    f"[{task_id}] 7-PILLAR evidence adapter failed: "
                    f"{type(adapter_error).__name__}",
                )
            pillar_end = datetime.now(timezone.utc)
            elapsed_ms = int((pillar_end - pillar_start).total_seconds() * 1000)
            # [BOSS-5] Özet 7 anahtar mühürde yeterli değildir: motorların ham
            # çıktısı (7 rapor) hesaplanıp SÜREÇ BELLEĞİNDE kayboluyordu —
            # "adli mühür" iddiası kapsam dışı kalıyordu. Tam kayıt (raporlar +
            # bundle sürümü) kanıt zincirine eklenir; mühür yalnız zinciri
            # yazdığı için veri artık diske de iner.
            status.evidence_chain.append({
                "agent": "pineal_7pillar",
                "result": {
                    "frequency": (status.frequency_map or {}).get("status"),
                    "seismos_events": (status.seismos_events or {}).get("event_count", 0),
                    "void_top": (status.void_map or {}).get("top_voids", []),
                    "gravity_dominant": (status.gravity_map or {}).get("dominant_attractor"),
                    "pulse_rhythm": (status.pulse_map or {}).get("rhythm_signature"),
                    "key_confidence": (status.key_matrix or {}).get("confidence", 0),
                    "elapsed_ms": elapsed_ms,
                    "pillars": {
                        "frequency_map": status.frequency_map,
                        "seismos_events": status.seismos_events,
                        "void_map": status.void_map,
                        "strata_map": status.strata_map,
                        "gravity_map": status.gravity_map,
                        "pulse_map": status.pulse_map,
                        "key_matrix": status.key_matrix,
                        "version": (status.pillar_bundle or {}).get("version"),
                        "computed_at": (status.pillar_bundle or {}).get("computed_at"),
                    },
                },
                "timestamp": pillar_end.isoformat(),
            })
            if adapter_record is not None:
                adapter_record["timestamp"] = pillar_end.isoformat()
                status.evidence_chain.append(adapter_record)
            if timeline_record is not None:
                timeline_record["timestamp"] = pillar_end.isoformat()
                status.evidence_chain.append(timeline_record)
            status.agent_runs["pineal_7pillar"] = AgentRun(
                task_id=task_id, agent_name="pineal_7pillar", status="completed",
                started_at=pillar_start, completed_at=pillar_end,
                confidence=(status.key_matrix or {}).get("confidence", 0),
                output_summary={
                    name: (pillar_fields.get(field) or {}).get("machine_note", "")
                    for name, field in (
                        ("frequency", "frequency_map"), ("seismos", "seismos_events"),
                        ("void", "void_map"), ("strata", "strata_map"),
                        ("gravity", "gravity_map"), ("pulse", "pulse_map"),
                        ("key", "key_matrix"),
                    )
                },
            )
            self._log("INFO", f"[{task_id}] 7-PILLAR tamamlandı ({elapsed_ms}ms)")
            self._rack_update("pineal_7pillar", "ready")
            # [LIFE-RUPTURE] Boylamsal katman: 7 sütunun ürettiği haritalar +
            # hedef profil + görsel kanıt tek geçişte kişinin kendi baseline'ıyla
            # karşılaştırılır. Deterministik, LLM'siz; rapor mühürlenen zincire girer.
            status.evidence_chain.append(self._life_rupture_record(status, input_data))
            self._snapshot(status)
        except Exception as e:
            self._rack_update("pineal_7pillar", "wait")
            error_time = datetime.now(timezone.utc)
            # [BOSS-8] Zaman aşımı ayrı kodla raporlanır.
            error_code = "AGENT_TIMEOUT" if isinstance(e, AgentTimeoutError) else type(e).__name__
            self._log("ERROR", f"[{task_id}] 7-PILLAR failure: {error_code}: {e}")
            status.agent_runs["pineal_7pillar"] = AgentRun(
                task_id=task_id, agent_name="pineal_7pillar", status="failed",
                started_at=pillar_start, completed_at=error_time,
                error_code=error_code,
                error_message=str(e)[:250],
            )
            # Failures are evidence too: retain a serializable record instead
            # of leaving an unexplained gap in the chain.
            status.evidence_chain.append({
                "agent": "pineal_7pillar",
                "evidence_type": "execution_failure",
                "result": {"error_code": error_code, "error_message": str(e)[:250]},
                "timestamp": error_time.isoformat(),
            })
            if input_data.get("evidence_timeline_status") == "unavailable":
                status.evidence_chain.append({
                    "agent": "evidence_timeline",
                    "evidence_type": "not_built",
                    "result": {
                        "schema_version": "evidence-timeline-v1",
                        "build_status": "unavailable",
                        "reason_code": "PILLAR_BUNDLE_UNAVAILABLE",
                    },
                    "timestamp": error_time.isoformat(),
                })
            pillar_cfg = self.config.get_agent_config("pineal_7pillar")
            if not pillar_cfg.graceful_degradation:
                status.status = PipelineStatus.HALTED_CRITICAL
                status.halted_reason = "7-pillar evidence foundation failed"
                status.completed_at = error_time
                self._emit(ErrorHaltEvent(
                    task_id=task_id,
                    agent_name="pineal_7pillar",
                    error_code=error_code,
                    error_message=str(e)[:200],
                    severity=Severity.Critical,
                ))
                await self._merge_task_memory(task_id, status)
                self._snapshot(status)
                return status
            self._snapshot(status)

        self._emit(TaskStartedEvent(
            task_id=task_id,
            agent_name="PinealExecutor",
            input_summary="Profil verisi işleniyor, ajan rotası çiziliyor."
        ))

        route: RoutePlan = await self.router.analyze(input_data)
        self._log("INFO", "[" + task_id + "] ROUTE: " + " -> ".join(route.agents))
        status.planned_agents = route.agents.copy()
        self._snapshot(status)
        
        deferred = []
        try:
            for agent_name in route.agents:
                if self._resume_done(status, agent_name):
                    self._log(
                        "INFO",
                        f"[{task_id}] RESUME: {agent_name} atlandı — yan etki tekrarı yok.",
                    )
                    continue
                if agent_name in ["pattern_interrupt", "resonance_synthesizer"]:
                    deferred.append(agent_name)
                    continue
                if agent_name not in self.agents:
                    raise KeyError("Bilinmeyen yetenek: " + agent_name)
                status.current_agent = agent_name
                self._log("WARNING", "[" + task_id + "] AGENT " + agent_name + ": calisiyor")
                self._rack_update(agent_name, "active")
                
                run = AgentRun(
                    task_id=task_id,
                    agent_name=agent_name,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    input_summary=self._summarize_input(input_data, agent_name),
                )
                status.agent_runs[agent_name] = run
                self._snapshot(status)
                
                self._emit(TaskStartedEvent(
                    task_id=task_id,
                    agent_name=agent_name,
                    input_summary="Ajan tetiklendi"
                ))
                agent_cfg = self.config.get_agent_config(agent_name)
                
                if agent_name == "resonance_synthesizer" and not input_data.get("outreach_intent"):
                    if input_data.get("aspasia_goals"):
                        input_data["outreach_intent"] = "; ".join(str(g) for g in input_data["aspasia_goals"])
                    else:
                        prof = input_data.get("user_profile") or {}
                        ctx = input_data.get("user_context") or {}
                        has_user_evidence = any((
                            prof.get("bio"), prof.get("posts"), prof.get("private_rituals"),
                            prof.get("late_night_playlist"), prof.get("secret_envies"),
                            ctx.get("rituals"), ctx.get("playlist"), ctx.get("envies")
                        ))
                        if not has_user_evidence:
                            input_data["outreach_intent"] = (
                                "Doğal & Etkileyici İlk Temas: Karşı tarafın bilişsel tarzına, "
                                "tutkularına ve hassasiyetlerine saygılı, merak uyandıran ve "
                                "karşı tarafı gerçekten anladığını hissettiren doğrudan ilk temas (Opening Hook)."
                            )

                agent_llm_calls: list[dict[str, Any]] = []
                attempt_mark = len(egress_attempts())
                resume_marker = copy.deepcopy(input_data)
                try:
                    agent = self.agents[agent_name]
                    with self._capture_llm_calls(task_id, agent_name) as agent_scope:
                        try:
                            result = await self._execute_with_timeout(
                                agent, input_data, self.memory, self.llm_gateway,
                                agent_cfg.timeout_seconds,
                            )
                        finally:
                            agent_llm_calls = list(agent_scope.records)
                            run.call_ids = list(agent_scope.call_ids)
                    if not isinstance(result, BaseModel):
                        raise TypeError(agent_name + " gecersiz cikti: " + str(type(result)))
                except InsufficientEvidenceError:
                    raise
                except Exception as e:
                    # [BOSS-8] Zaman aşımı "başarısız"dan ayrı raporlanır: hangi
                    # ajanın bütçeyi yediği telemetride görünür olur.
                    if isinstance(e, AgentTimeoutError):
                        run.status = "timed_out"
                        run.error_code = "AGENT_TIMEOUT"
                        self._log("ERROR", f"[{task_id}] AGENT {agent_name} ZAMAN AŞIMI: {str(e)[:180]}")
                    else:
                        run.status = "failed"
                        run.error_code = type(e).__name__
                        self._log("ERROR", f"[{task_id}] AGENT {agent_name} BASTARISIZ: {type(e).__name__}: {str(e)[:200]}")
                    run.error_message = str(e)[:200]
                    self._rack_update(agent_name, "wait")

                    # [SORUMLULUK ZİNCİRİ] Hata GİZLENMEZ: koşunun dürüst izi
                    # agent_runs'taki run.responsibility alanına yazılır
                    # (kanıt zinciri uydurma kanıtla doldurulmaz).
                    run.responsibility = self._responsibility_trail(
                        agent_name=agent_name,
                        run=run,
                        claimed=("timed_out" if isinstance(e, AgentTimeoutError) else "failed"),
                        attempted_paths=self._egress_slice(attempt_mark),
                        blockers=[f"{run.error_code}: {run.error_message}"],
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "graceful_degradation_continue"
                        ),
                        evidence_recorded=False,
                    )
                    _fail_next = (
                        "task_halted_critical"
                        if (agent_name in self.config.critical_agents
                            or not agent_cfg.graceful_degradation)
                        else "graceful_degradation_continue"
                    )
                    if (
                        _fail_next == "task_halted_critical"
                        or run.error_code in {"VaultLockedError", "SpendCapExceeded"}
                        or isinstance(e, AgentTimeoutError)
                    ):
                        _fail_opts = (
                            ["open_vault", "grant_boundary_authority"]
                            if run.error_code == "VaultLockedError"
                            else ["raise_spend_cap", "operator_budget_review"]
                            if run.error_code == "SpendCapExceeded"
                            else ["extend_timebox", "operator_review"]
                            if isinstance(e, AgentTimeoutError)
                            else ["retry_task", "operator_review"]
                        )
                        self._request_support(
                            status,
                            task_id=task_id,
                            agent_name=agent_name,
                            reason=f"{run.error_code}: {run.error_message}",
                            options=_fail_opts,
                            next_action=_fail_next,
                            kind=(
                                "vault_open" if run.error_code == "VaultLockedError"
                                else "spend_cap" if run.error_code == "SpendCapExceeded"
                                else "timebox" if isinstance(e, AgentTimeoutError)
                                else "operator_response"
                            ),
                            blocks_resume=True,
                        )
                    if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                        status.status = "halted_critical"
                        status.completed_at = datetime.now(timezone.utc)
                        self._snapshot(status)
                        self._emit(ErrorHaltEvent(
                            task_id=task_id,
                            agent_name=agent_name,
                            error_code=type(e).__name__,
                            error_message=str(e)[:200],
                            severity=Severity.Critical
                        ))
                        self._log("ERROR", f"[{task_id}] PIPELINE FAILED; critical agent failed.")
                        await self._merge_task_memory(task_id, status)
                        return status
                    else:
                        self._log("WARNING", f"[{task_id}] Non-critical agent {agent_name} failed. Continuing pipeline (graceful degradation).")
                        self._snapshot(status)
                        continue

                check = self.uncertainty.evaluate(result, agent_name)
                if agent_name == "autonomous_verifier" and (
                    getattr(result, "data_confidence", True) is False
                    or (
                        isinstance(getattr(check, "confidence", None), (int, float))
                        and check.confidence < agent_cfg.min_llm_confidence
                    )
                ):
                    # The verifier report is a structured record, not a final
                    # pipeline decision. Preserve UNVERIFIED/internal checks
                    # for downstream consumers instead of dropping them at the
                    # generic confidence threshold.
                    check = UncertaintyReport(
                        is_suspicious=False,
                        confidence=0.0,
                        reason="Structured verifier report retained without a decision-grade verdict.",
                        data_score=float(getattr(check, "data_score", 0.0) or 0.0),
                        breakdown=getattr(check, "breakdown", {}) or {},
                        no_decision=True,
                    )
                # GÖREV TAMAMLANDI ≠ KARAR ÜRETİLDİ: ajan kendi çıktısını
                # "karar değil" (data_confidence=False) diye işaretlediyse koşu
                # LOW_CONFIDENCE ile halted YAZILMAZ; çıktı kaydedilir ama
                # karar-Grade sayılmaz (run.status = "completed_no_decision").
                # Eskiden bu ayrım resonance_calc için 0.75'lik UYDURMA güven
                # tabanıyla yapılıyordu (uncertainty_engine).
                # `is True` ŞART: MagicMock tabanlı testlerde getattr truthy bir
                # mock döndürür ve fail-closed kapısını yanlışlıkla atlatırdı.
                no_decision = getattr(check, "no_decision", False) is True
                if no_decision:
                    self._log(
                        "WARNING",
                        f"[{task_id}] {agent_name}: çıktı KARAR DEĞİL — {check.reason} "
                        f"Koşu kaydedildi, güven uydurulmadı.",
                    )

                if check.confidence < agent_cfg.min_llm_confidence and not no_decision:
                    halt_reason = check.reason
                    self._log("ERROR", f"[{task_id}] COGNITIVE ROUTER: {halt_reason}")
                    run.status = "halted"
                    run.error_code = "LOW_CONFIDENCE"
                    run.error_message = halt_reason
                    self._rack_update(agent_name, "wait")

                    # [SORUMLULUK ZİNCİRİ] Düşük güven = kanıt yetersiz;
                    # "tamamlanmış" gibi gösterilmez, zincirde izi kalır.
                    run.responsibility = self._responsibility_trail(
                        agent_name=agent_name,
                        run=run,
                        claimed="halted_evidence",
                        attempted_paths=self._egress_slice(attempt_mark),
                        blockers=[f"LOW_CONFIDENCE: {halt_reason}"],
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "evidence_degradation_continue"
                        ),
                        evidence_recorded=False,
                    )
                    self._request_support(
                        status,
                        task_id=task_id,
                        agent_name=agent_name,
                        reason=f"LOW_CONFIDENCE: {halt_reason}",
                        options=["deep_verify", "operator_input", "defer_agent"],
                        blocks_resume=(
                            agent_name in self.config.critical_agents
                            or not agent_cfg.graceful_degradation
                        ),
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "evidence_degradation_continue"
                        ),
                    )

                    if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                        status.halted_reason = halt_reason
                        status.status = "halted_critical"
                        self._snapshot(status)
                        raise InsufficientEvidenceError(halt_reason)
                    else:
                        self._log("WARNING", f"[{task_id}] Non-critical agent {agent_name} halted due to evidence. Continuing pipeline.")
                        self._snapshot(status)
                        continue

                research_note = None
                _deep_llm_calls: list[dict[str, Any]] = []
                if check.is_suspicious:
                    self._log("ERROR", "[" + task_id + "] UNCERTAINTY: " + check.reason)
                    try:
                        # Preserve `result`: downstream dependencies must receive the
                        # actual typed agent output, never a generic research note.
                        with self._capture_llm_calls(task_id, "deep_research") as research_scope:
                            try:
                                research_note = await self._deep_research(result, check, agent_name)
                            finally:
                                _deep_llm_calls = list(research_scope.records)
                    except Exception as e:
                        # [DESTEK AKIŞI] Zombi koşu YOK: durum + mühür + talep.
                        run.status = "halted"
                        run.error_code = "SUSPICIOUS_EVIDENCE"
                        run.error_message = str(e)[:200]
                        run.completed_at = datetime.now(timezone.utc)
                        run.responsibility = self._responsibility_trail(
                            agent_name=agent_name,
                            run=run,
                            claimed="halted_evidence",
                            attempted_paths=self._egress_slice(attempt_mark),
                            blockers=[f"SUSPICIOUS_EVIDENCE: {run.error_message}"],
                            support_requested=["uncertainty:deep_research"],
                            next_action="rerun_deep_research_or_operator_review",
                            evidence_recorded=False,
                        )
                        self._request_support(
                            status,
                            task_id=task_id,
                            agent_name=agent_name,
                            reason=f"Şüpheli kanıt doğrulanamadı: {run.error_message}",
                            options=["rerun_deep_research", "operator_review"],
                            blocks_resume=(
                                agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation
                            ),
                            next_action="rerun_deep_research_or_operator_review",
                        )
                        if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                            raise InsufficientEvidenceError("Supheli kanit dogrulanamadi: " + str(e)[:80])
                        self._log("WARNING", f"[{task_id}] Non-critical agent {agent_name} deep research failed. Continuing.")
                        continue

                # [BOSS-6] Authentic vector çağrıları ayrı bir yakalama kapsamında
                # koşar: aksi hâlde LLM harcaması HİÇBİR kayıtta görünmüyordu
                # (ne runs[*].llm_calls ne kanıt zinciri). Kayıtlar burada
                # toplanır, koşu raporuna output_summary YAZILDIKTAN SONRA eklenir
                # — aksi hâlde run.output_summary ataması izi ezer.
                aux_call_records: list[dict[str, Any]] = []
                claim_gate_record = None
                if agent_name == "mirror_truth":
                    input_data["user_mirror"] = result.model_dump()
                    with self._capture_llm_calls(task_id, "authentic_vector:user") as vector_scope:
                        user_vector = await self._calculate_authentic_vector(input_data["user_mirror"])
                    self._store_authentic_vector(input_data, "user", user_vector)
                    aux_call_records = list(vector_scope.records)
                elif agent_name == "human_behavior":
                    input_data["target_analysis"] = result.model_dump()
                    with self._capture_llm_calls(task_id, "authentic_vector:target") as vector_scope:
                        target_vector = await self._calculate_authentic_vector(input_data["target_analysis"])
                    self._store_authentic_vector(input_data, "target", target_vector)
                    aux_call_records = list(vector_scope.records)
                elif agent_name == "passion_mapper":
                    input_data["passions"] = result.model_dump()
                elif agent_name == "friction_detector":
                    input_data["frictions"] = result.model_dump()
                elif agent_name == "cognitive_profiler":
                    input_data["cognitive"] = result.model_dump()
                elif agent_name == "autonomous_verifier":
                    input_data["verifications"] = result.model_dump(mode="json")
                    gate = build_claim_decision_gate(result)
                    input_data["claim_gate"] = gate.model_dump(mode="json")
                    claim_gate_record = {
                        "agent": "claim_decision_gate",
                        "evidence_type": "decision_gate",
                        "result": gate.model_dump(mode="json"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                _output_record = self._evidence_record(
                    agent_name,
                    result,
                    evidence_type="agent_output",
                    uncertainty=check,
                    llm_calls=agent_llm_calls,
                    aux_llm_calls=aux_call_records,
                )
                # [SORUMLULUK ZİNCİRİ] Çıktı = koşu + kanıt birlikte mühürlenir.
                _output_record["responsibility"] = self._responsibility_trail(
                    agent_name=agent_name,
                    run=run,
                    claimed=("completed_no_decision" if no_decision else "completed"),
                    attempted_paths=self._egress_slice(attempt_mark),
                    support_requested=(["uncertainty:deep_research"]
                                        if research_note is not None else []),
                    next_action=self._next_agent_action(route, agent_name),
                    evidence_recorded=bool(_output_record.get("result")),
                )
                if _output_record["responsibility"]["integrity"].get("violation"):
                    # Eksik kanıt başarı değildir: mühür görevi durdurur.
                    raise InsufficientEvidenceError(
                        f"{agent_name}: sorumluluk mührü reddetti (eksik kanıt)"
                    )
                status.evidence_chain.append(_output_record)
                if claim_gate_record is not None:
                    status.evidence_chain.append(claim_gate_record)
                self._append_tier2_canonical_output(status, agent_name, result)
                if research_note is not None:
                    status.evidence_chain.append(self._evidence_record(
                        "deep_research",
                        research_note,
                        evidence_type="verification_note",
                        source_agent=agent_name,
                        uncertainty=check,
                        llm_calls=_deep_llm_calls,
                    ))

                run.status = "completed_no_decision" if no_decision else "completed"
                run.decision_grade = not no_decision
                run.completed_at = datetime.now(timezone.utc)
                run.output_summary = result.model_dump()
                run.output_summary["_provenance"] = self._provenance_for(agent_name, result, agent_llm_calls)
                self._attach_vector_calls(run, aux_call_records)
                run.confidence = round(check.confidence, 3)
                if agent_name not in status.completed_agents:
                    status.completed_agents.append(agent_name)
                self._rack_update(agent_name, "ready")

                # [FIX #3] Sınırlı upstream bulgu
                _core = self._finding_core(result)
                if _core:
                    _append_upstream_finding(input_data, agent_name, _core)

                if agent_name == "resonance_calc":
                    status.resonance_score = getattr(result, "compatibility_score", None)
                self._record_ingested(status, agent_name, resume_marker, input_data)
                self._snapshot(status)
                
                self._emit(StepCompletedEvent(
                    task_id=task_id,
                    agent_name=agent_name,
                    step_name="execute",
                    output_hash=self._hash_evidence_result(result)
                ))

                if agent_name == "resonance_calc" and hasattr(result, "compatibility_score") and result.compatibility_score < 0.70:
                    # [FIX #11] Eski hata etiketi klinik/romantik bir
                    # yargı çağrıştırıyordu; mekanik gerçek: skor EŞİĞİN
                    # ALTINDA kaldığı için sentez ispat yüküyle REDDEDİLDİ.
                    # Log + reason artık mekanik durumu raporlar
                    # (status kodu DEĞİŞMEZ — "halted_frequency" 5 test
                    # tarafından kilitli).
                    self._log("ERROR", "[" + task_id + "] INSUFFICIENT_RESONANCE_EVIDENCE: " + str(round(result.compatibility_score, 2)) + " < 0.70 esigi; sentez reddedildi")
                    status.status = "halted_frequency"
                    status.halted_reason = "Resonans kaniti esigin altinda: " + str(round(result.compatibility_score, 2)) + " < 0.70; sentez reddedildi"
                    status.completed_at = datetime.now(timezone.utc)
                    await self._merge_task_memory(task_id, status)
                    self._snapshot(status)
                    return status

            # Deferred agents run after their dependencies, not outside the
            # evidence contract.  Ordering must never bypass validation,
            # uncertainty thresholds, or graceful-degradation policy.
            for agent_name in deferred:
                if self._resume_done(status, agent_name):
                    self._log(
                        "INFO",
                        f"[{task_id}] RESUME: {agent_name} atlandı — yan etki tekrarı yok.",
                    )
                    continue
                if agent_name not in self.agents:
                    raise KeyError("Bilinmeyen yetenek: " + agent_name)
                status.current_agent = agent_name
                self._log("WARNING", "[" + task_id + "] AGENT " + agent_name + ": calisiyor")
                self._rack_update(agent_name, "active")
                run = AgentRun(
                    task_id=task_id,
                    agent_name=agent_name,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    input_summary=self._summarize_input(input_data, agent_name),
                )
                status.agent_runs[agent_name] = run
                self._snapshot(status)
                self._emit(TaskStartedEvent(
                    task_id=task_id,
                    agent_name=agent_name,
                    input_summary="Ajan tetiklendi",
                ))
                agent_cfg = self.config.get_agent_config(agent_name)

                if agent_name == "pattern_interrupt" and _canonical_message_context_enabled():
                    from agent_core.domain.message_context_models import MessageEvidenceContext
                    from agent_core.services.message_decision_context import (
                        build_message_evidence_context,
                    )

                    adapter_error = None
                    try:
                        message_context = build_message_evidence_context(
                            input_data.get("evidence_timeline")
                        )
                    except Exception as exc:
                        adapter_error = type(exc).__name__
                        message_context = MessageEvidenceContext(
                            context_id="ctx_00000000000000000000",
                            build_status="failed",
                            excluded_counts={"adapter_error": 1},
                        )
                        self._log(
                            "ERROR",
                            f"[{task_id}] Message decision-context adapter failed: {adapter_error}",
                        )

                    input_data["message_evidence_context"] = message_context.model_dump(
                        mode="json"
                    )
                    status.evidence_chain.append(
                        {
                            "agent": "message_decision_context_adapter",
                            "evidence_type": "decision_context",
                            "result": {
                                "schema_version": message_context.schema_version,
                                "build_status": (
                                    "failed" if adapter_error else message_context.build_status
                                ),
                                "context_id": message_context.context_id,
                                "policy": message_context.policy,
                                "selected_evidence_ids": [
                                    item.evidence_id for item in message_context.items
                                ],
                                "excluded_counts": message_context.excluded_counts,
                                **({"error_code": adapter_error} if adapter_error else {}),
                            },
                        }
                    )

                agent_llm_calls: list[dict[str, Any]] = []
                attempt_mark = len(egress_attempts())
                resume_marker = copy.deepcopy(input_data)
                try:
                    agent = self.agents[agent_name]
                    with self._capture_llm_calls(task_id, agent_name) as agent_scope:
                        try:
                            result = await self._execute_with_timeout(
                                agent, input_data, self.memory, self.llm_gateway,
                                agent_cfg.timeout_seconds,
                            )
                        finally:
                            agent_llm_calls = list(agent_scope.records)
                            run.call_ids = list(agent_scope.call_ids)
                            if agent_name == "pattern_interrupt":
                                input_data.pop("message_evidence_context", None)
                    if not isinstance(result, BaseModel):
                        raise TypeError(agent_name + " gecersiz cikti: " + str(type(result)))
                except InsufficientEvidenceError:
                    raise
                except Exception as e:
                    if isinstance(e, AgentTimeoutError):
                        run.status = "timed_out"
                        run.error_code = "AGENT_TIMEOUT"
                        self._log("ERROR", f"[{task_id}] AGENT {agent_name} ZAMAN AŞIMI: {str(e)[:180]}")
                    else:
                        run.status = "failed"
                        run.error_code = type(e).__name__
                        self._log("ERROR", f"[{task_id}] AGENT {agent_name} BASTARISIZ: {type(e).__name__}: {str(e)[:200]}")
                    run.error_message = str(e)[:200]
                    self._rack_update(agent_name, "wait")
                    # [SORUMLULUK ZİNCİRİ] Geciken ajan hatası da zincire girer.
                    run.responsibility = self._responsibility_trail(
                        agent_name=agent_name,
                        run=run,
                        claimed=("timed_out" if isinstance(e, AgentTimeoutError) else "failed"),
                        attempted_paths=self._egress_slice(attempt_mark),
                        blockers=[f"{run.error_code}: {run.error_message}"],
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "graceful_degradation_continue"
                        ),
                        evidence_recorded=False,
                    )
                    _fail_next = (
                        "task_halted_critical"
                        if (agent_name in self.config.critical_agents
                            or not agent_cfg.graceful_degradation)
                        else "graceful_degradation_continue"
                    )
                    if (
                        _fail_next == "task_halted_critical"
                        or run.error_code in {"VaultLockedError", "SpendCapExceeded"}
                        or isinstance(e, AgentTimeoutError)
                    ):
                        _fail_opts = (
                            ["open_vault", "grant_boundary_authority"]
                            if run.error_code == "VaultLockedError"
                            else ["raise_spend_cap", "operator_budget_review"]
                            if run.error_code == "SpendCapExceeded"
                            else ["extend_timebox", "operator_review"]
                            if isinstance(e, AgentTimeoutError)
                            else ["retry_task", "operator_review"]
                        )
                        self._request_support(
                            status,
                            task_id=task_id,
                            agent_name=agent_name,
                            reason=f"{run.error_code}: {run.error_message}",
                            options=_fail_opts,
                            next_action=_fail_next,
                            kind=(
                                "vault_open" if run.error_code == "VaultLockedError"
                                else "spend_cap" if run.error_code == "SpendCapExceeded"
                                else "timebox" if isinstance(e, AgentTimeoutError)
                                else "operator_response"
                            ),
                            blocks_resume=True,
                        )
                    if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                        status.status = "halted_critical"
                        status.completed_at = datetime.now(timezone.utc)
                        self._snapshot(status)
                        self._emit(ErrorHaltEvent(
                            task_id=task_id,
                            agent_name=agent_name,
                            error_code=type(e).__name__,
                            error_message=str(e)[:200],
                            severity=Severity.Critical,
                        ))
                        await self._merge_task_memory(task_id, status)
                        return status
                    self._log("WARNING", f"[{task_id}] Non-critical deferred agent {agent_name} failed. Continuing pipeline.")
                    self._snapshot(status)
                    continue

                claim_gate_blocked_ids: list[str] = []
                if agent_name in {"pattern_interrupt", "resonance_synthesizer"}:
                    result, claim_gate_blocked_ids = self._apply_claim_decision_gate(
                        result, input_data.get("claim_gate")
                    )
                check = self.uncertainty.evaluate(result, agent_name)
                if claim_gate_blocked_ids:
                    check = UncertaintyReport(
                        is_suspicious=False,
                        confidence=0.0,
                        reason="Generated message suppressed by the deterministic same-claim gate.",
                        data_score=float(getattr(check, "data_score", 0.0) or 0.0),
                        breakdown=getattr(check, "breakdown", {}) or {},
                        no_decision=True,
                    )
                # `is True` ŞART: MagicMock tabanlı testlerde getattr truthy bir
                # mock döndürür ve fail-closed kapısını yanlışlıkla atlatırdı.
                no_decision = getattr(check, "no_decision", False) is True
                if no_decision:
                    self._log(
                        "WARNING",
                        f"[{task_id}] {agent_name}: çıktı KARAR DEĞİL — {check.reason} "
                        f"Koşu kaydedildi, güven uydurulmadı.",
                    )
                if check.confidence < agent_cfg.min_llm_confidence and not no_decision:
                    halt_reason = check.reason
                    run.status = "halted"
                    run.error_code = "LOW_CONFIDENCE"
                    run.error_message = halt_reason
                    self._log("ERROR", f"[{task_id}] COGNITIVE ROUTER: {halt_reason}")
                    self._rack_update(agent_name, "wait")
                    # [SORUMLULUK ZİNCİRİ] Geciken ajan düşük-güven izi.
                    run.responsibility = self._responsibility_trail(
                        agent_name=agent_name,
                        run=run,
                        claimed="halted_evidence",
                        attempted_paths=self._egress_slice(attempt_mark),
                        blockers=[f"LOW_CONFIDENCE: {halt_reason}"],
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "evidence_degradation_continue"
                        ),
                        evidence_recorded=False,
                    )
                    self._request_support(
                        status,
                        task_id=task_id,
                        agent_name=agent_name,
                        reason=f"LOW_CONFIDENCE: {halt_reason}",
                        options=["deep_verify", "operator_input", "defer_agent"],
                        blocks_resume=(
                            agent_name in self.config.critical_agents
                            or not agent_cfg.graceful_degradation
                        ),
                        next_action=(
                            "task_halted_critical"
                            if (agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation)
                            else "evidence_degradation_continue"
                        ),
                    )

                    if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                        status.halted_reason = halt_reason
                        status.status = "halted_critical"
                        self._snapshot(status)
                        raise InsufficientEvidenceError(halt_reason)
                    self._log("WARNING", f"[{task_id}] Non-critical deferred agent {agent_name} halted due to evidence.")
                    self._snapshot(status)
                    continue

                research_note = None
                _deep_llm_calls: list[dict[str, Any]] = []
                if check.is_suspicious:
                    self._log("ERROR", "[" + task_id + "] UNCERTAINTY: " + check.reason)
                    try:
                        with self._capture_llm_calls(task_id, "deep_research") as research_scope:
                            try:
                                research_note = await self._deep_research(result, check, agent_name)
                            finally:
                                _deep_llm_calls = list(research_scope.records)
                    except Exception as e:
                        run.status = "halted"
                        run.error_code = "SUSPICIOUS_EVIDENCE"
                        run.error_message = str(e)[:200]
                        run.completed_at = datetime.now(timezone.utc)
                        run.responsibility = self._responsibility_trail(
                            agent_name=agent_name,
                            run=run,
                            claimed="halted_evidence",
                            attempted_paths=self._egress_slice(attempt_mark),
                            blockers=[f"SUSPICIOUS_EVIDENCE: {run.error_message}"],
                            support_requested=["uncertainty:deep_research"],
                            next_action="rerun_deep_research_or_operator_review",
                            evidence_recorded=False,
                        )
                        self._request_support(
                            status,
                            task_id=task_id,
                            agent_name=agent_name,
                            reason=f"Şüpheli kanıt doğrulanamadı: {run.error_message}",
                            options=["rerun_deep_research", "operator_review"],
                            blocks_resume=(
                                agent_name in self.config.critical_agents
                                or not agent_cfg.graceful_degradation
                            ),
                            next_action="rerun_deep_research_or_operator_review",
                        )
                        if agent_name in self.config.critical_agents or not agent_cfg.graceful_degradation:
                            raise InsufficientEvidenceError("Supheli kanit dogrulanamadi: " + str(e)[:80])
                        self._log("WARNING", f"[{task_id}] Non-critical deferred agent {agent_name} deep research failed.")
                        self._rack_update(agent_name, "wait")
                        self._snapshot(status)
                        continue

                output_record = self._evidence_record(
                    agent_name,
                    result,
                    evidence_type="agent_output",
                    uncertainty=check,
                    llm_calls=agent_llm_calls,
                )
                if claim_gate_blocked_ids:
                    output_record["claim_gate"] = {
                        "decision_state": "BLOCKED_SAME_CLAIM",
                        "claim_ids": claim_gate_blocked_ids,
                        "policy": "exact_claim_only",
                    }
                # [SORUMLULUK ZİNCİRİ] Geciken ajanların da koşusu mühürlenir.
                output_record["responsibility"] = self._responsibility_trail(
                    agent_name=agent_name,
                    run=run,
                    claimed=("completed_no_decision" if no_decision else "completed"),
                    attempted_paths=self._egress_slice(attempt_mark),
                    support_requested=(["uncertainty:deep_research"]
                                        if research_note is not None else []),
                    next_action="deferred_message_steps_or_finalize",
                    evidence_recorded=bool(output_record.get("result")),
                )
                if output_record["responsibility"]["integrity"].get("violation"):
                    raise InsufficientEvidenceError(
                        f"{agent_name}: sorumluluk mührü reddeti (eksik kanıt)"
                    )
                status.evidence_chain.append(output_record)
                self._append_tier2_canonical_output(status, agent_name, result)
                if research_note is not None:
                    status.evidence_chain.append(self._evidence_record(
                        "deep_research",
                        research_note,
                        evidence_type="verification_note",
                        source_agent=agent_name,
                        uncertainty=check,
                        llm_calls=_deep_llm_calls,
                    ))
                run.status = "completed_no_decision" if no_decision else "completed"
                run.decision_grade = not no_decision
                run.completed_at = datetime.now(timezone.utc)
                run.output_summary = result.model_dump()
                run.output_summary["_provenance"] = self._provenance_for(agent_name, result, agent_llm_calls)
                run.confidence = round(check.confidence, 3)
                if agent_name not in status.completed_agents:
                    status.completed_agents.append(agent_name)
                self._rack_update(agent_name, "ready")
                # [FIX #3] Geciken ajanlar da upstream bütçesine eklenir.
                _core = self._finding_core(result)
                if _core:
                    _append_upstream_finding(input_data, agent_name, _core)
                if agent_name == "pattern_interrupt":
                    # [BOSS-7] Rota çıktısı input_data'ya yazılır: ShadowExecutor
                    # aynı mesajı ikinci kez LLM'e soruyordu (görev başına 2×
                    # GeneratedMessage). İkinci çağrı artık bu kaydı tüketir.
                    input_data["_pattern_interrupt"] = {
                        "message": str(getattr(result, "message", "") or ""),
                        "evidence_ids_used": list(
                            getattr(result, "evidence_ids_used", []) or []
                        ),
                        "claim_gate_blocked_ids": claim_gate_blocked_ids,
                        "decision_context_id": getattr(
                            result, "decision_context_id", None
                        ),
                        "agent": "pattern_interrupt",
                        "source": "route",
                    }
                self._record_ingested(status, agent_name, resume_marker, input_data)
                self._snapshot(status)
                self._emit(StepCompletedEvent(
                    task_id=task_id,
                    agent_name=agent_name,
                    step_name="execute",
                    output_hash=self._hash_evidence_result(result),
                ))

            # The verifier runs before some Tier-2 agents by route policy.
            # Once all primary outputs exist, append internal-only checks for
            # any separately stored human_behavior observations. These are
            # not copied into forensic_evidence or the B6 message timeline.
            self._refresh_internal_verification_checks(status, input_data)

            # --- 360° HOLISTIC PROFILE OLUŞTURMA ---
            passions_obj = None
            frictions_obj = None
            cognitive_obj = None
            bridge_obj = None
            for item in status.evidence_chain:
                ag = item.get("agent")
                res = item.get("result", {})
                if ag == "passion_mapper":
                    passions_obj = PassionProfile(**res)
                elif ag == "friction_detector":
                    frictions_obj = FrictionProfile(**res)
                elif ag == "cognitive_profiler":
                    cognitive_obj = CognitiveStyle(**res)
                elif ag == "resonance_synthesizer":
                    bridge_obj = AuthenticBridge(**res)

            status.holistic_profile = HolisticProfile(
                username=input_data.get("target_profile", {}).get("username", "target"),
                passions=passions_obj,
                frictions=frictions_obj,
                cognitive=cognitive_obj,
                bridge=bridge_obj,
                overall_confidence=self._holistic_confidence(status.agent_runs)
            )
            self._log("INFO", "[" + task_id + "] 360 İnsan Tanıma Profili Oluşturuldu")

            # --- P1 + P7 + P8 DERİNLİK VE GERÇEKLİK ANALİZİ (QuoteGuard Korumalı) ---
            # depth_analyst ana döngü dışında çalışır; success/failure must be
            # recorded on status.agent_runs so DecisionEngine sees the gap
            # instead of silently treating depth as unused.
            if self._resume_done(status, "depth_analyst"):
                self._log("INFO", f"[{task_id}] RESUME: depth_analyst atlandı — LLM turu tekrarlanmadı.")
            else:
                depth_start = datetime.now(timezone.utc)
                self._rack_update("depth_analyst", "active")
                try:
                    depth_agent = self.agents.get("depth_analyst") or DepthAnalyst(self.llm_gateway)
                    # [FAZ B · B2/B3] Geçmiş hafıza: kristalden çağrılan hatıralar
                    # prompt'a kafesli girer (boşsa hiçbir şey eklenmez).
                    input_data["memory_crystal"] = self._recall_memory_crystal(task_id, input_data, status)
                    with self._capture_llm_calls(task_id, "depth_analyst") as depth_scope:
                        depth_rep = await self._bounded(
                            depth_agent.analyze(input_data, status.evidence_chain),
                            self.config.get_agent_config("depth_analyst").timeout_seconds,
                            "depth_analyst",
                        )
                    depth_end = datetime.now(timezone.utc)
                    status.depth_report = depth_rep.model_dump()
                    status.depth_report["_provenance"] = self._provenance_for(
                        "depth_analyst", depth_rep, depth_scope.records
                    )
                    _depth_summary = dict(status.depth_report)
                    status.agent_runs["depth_analyst"] = AgentRun(
                        task_id=task_id, agent_name="depth_analyst", status="completed",
                        started_at=depth_start, completed_at=depth_end,
                        output_summary=_depth_summary, call_ids=list(depth_scope.call_ids),
                        confidence=(
                            getattr(depth_rep, "reality_index", None)
                            if isinstance(getattr(depth_rep, "reality_index", None), (int, float))
                            else None
                        ),
                    )
                    q_stats = depth_rep.quote_guard or {}
                    kept = q_stats.get("kept", len(depth_rep.reality_findings))
                    checked = q_stats.get("checked", kept + q_stats.get("dropped_fake_quote", 0))
                    self._log("INFO", f"[{task_id}] DERİNLİK TURU: gerçeklik endeksi %{int(depth_rep.reality_index * 100)}")
                    self._log("INFO", f"[{task_id}] KALKAN: {kept}/{checked} bulgu kanıtla ayakta")
                    # [A-KAPANIŞ] Hakem → DepthReport izi: hangi claim_id hangi bulguyu etkiledi.
                    trace = getattr(depth_rep, "verification_trace", None) or {}
                    if trace.get("claims_available"):
                        self._log(
                            "INFO",
                            f"[{task_id}] HAKEM İZİ: {len(trace.get('linked_findings') or [])} bulgu "
                            f"{trace.get('claims_available')} iddiadan {len(trace.get('claim_ids_used') or [])} kimliğe bağlı; "
                            f"reddedilen kimlik={trace.get('rejected_claim_ids', 0)}",
                        )
                    self._rack_update("depth_analyst", "ready")
                except Exception as e:
                    self._rack_update("depth_analyst", "wait")
                    depth_end = datetime.now(timezone.utc)
                    error_code = "AGENT_TIMEOUT" if isinstance(e, AgentTimeoutError) else type(e).__name__
                    status.agent_runs["depth_analyst"] = AgentRun(
                        task_id=task_id, agent_name="depth_analyst", status="failed",
                        started_at=depth_start, completed_at=depth_end,
                        error_code=error_code,
                        error_message=str(e)[:200],
                    )
                    status.evidence_chain.append({
                        "agent": "depth_analyst",
                        "evidence_type": "execution_failure",
                        "result": {"error_code": error_code, "error_message": str(e)[:250]},
                        "timestamp": depth_end.isoformat(),
                    })
                    status.depth_report = {
                        "available": False,
                        "reason": "DEPTH_ANALYSIS_UNAVAILABLE",
                        "error_code": error_code,
                        "error_message": str(e)[:250],
                    }
                    self._log("WARNING", f"[{task_id}] Derinlik analizi atlandı: {e}")



            # --- 5. ve 6. DAMGA: SHADOW & OSINT FORENSİKLERİ ---
            # Bu iki ajan ana döngünün dışında çalıştığı için, başarılı/başarısız
            # durumlarını da status.agent_runs'a kaydediyoruz ki DecisionEngine
            # onları görsün ve sessizce "COMPLETED" damgalanmasınlar.
            if self._resume_done(status, "shadow_executor"):
                self._log("INFO", f"[{task_id}] RESUME: shadow_executor atlandı — LLM turu tekrarlanmadı.")
            else:
                self._rack_update("shadow_executor", "active")
                try:
                    with self._capture_llm_calls(task_id, "shadow_executor") as shadow_scope:
                        shadow_result = await self._bounded(
                            self.agents["shadow_executor"].execute(input_data),
                            self.config.get_agent_config("shadow_executor").timeout_seconds,
                            "shadow_executor",
                        )
                    shadow_result, shadow_gate_blocked_ids = self._apply_claim_decision_gate(
                        shadow_result, input_data.get("claim_gate")
                    )
                    if (
                        not shadow_gate_blocked_ids
                        and getattr(shadow_result, "fallback_reason", None) == "claim_gate_blocked_same_claim"
                    ):
                        routed_pattern = input_data.get("_pattern_interrupt") or {}
                        ids = routed_pattern.get("claim_gate_blocked_ids")
                        if isinstance(ids, list):
                            shadow_gate_blocked_ids = [str(item) for item in ids]
                    status.shadow_profile = shadow_result.model_dump()
                    if shadow_gate_blocked_ids:
                        status.shadow_profile["claim_gate"] = {
                            "decision_state": "BLOCKED_SAME_CLAIM",
                            "claim_ids": shadow_gate_blocked_ids,
                            "policy": "exact_claim_only",
                        }
                    status.shadow_profile["_provenance"] = self._provenance_for(
                        "shadow_executor", shadow_result, shadow_scope.records
                    )
                    _shadow_summary = shadow_result.model_dump() if hasattr(shadow_result, "model_dump") else {}
                    _shadow_summary["_provenance"] = status.shadow_profile["_provenance"]
                    if shadow_gate_blocked_ids:
                        _shadow_summary["claim_gate"] = status.shadow_profile["claim_gate"]
                    status.agent_runs["shadow_executor"] = AgentRun(
                        task_id=task_id, agent_name="shadow_executor", status="completed",
                        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                        output_summary=_shadow_summary, call_ids=list(shadow_scope.call_ids),
                        confidence=(
                            getattr(shadow_result, "confidence", None)
                            if isinstance(getattr(shadow_result, "confidence", None), (int, float))
                            and getattr(shadow_result, "data_confidence", True)
                            else None
                        ),
                        warnings=[] if getattr(shadow_result, "data_confidence", True) else [
                            getattr(shadow_result, "fallback_reason", None) or "data_unavailable"
                        ],
                    )
                    self._log("INFO", f"[{task_id}] GÖLGE FORENSİĞİ: Manipülasyon ve NLP dizisi eklendi")
                    self._rack_update("shadow_executor", "ready")
                except Exception as e:
                    self._rack_update("shadow_executor", "wait")
                    status.agent_runs["shadow_executor"] = AgentRun(
                        task_id=task_id, agent_name="shadow_executor",
                        status="timed_out" if isinstance(e, AgentTimeoutError) else "failed",
                        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
                        error_code="AGENT_TIMEOUT" if isinstance(e, AgentTimeoutError) else None,
                        error_message=str(e)[:200],
                    )
                    self._log("WARNING", f"[{task_id}] Gölge forensiği atlandı: {e}")

            # [FIX #1] OSINT artık discovery fazında çalışıyor (derinlik
            # motorundan ÖNCE). Eski sondaki blok KALDIRILDI: çıktı
            # input_data'ya yazılmadığı için kullanılamıyordu.

            # Determine final status via DecisionEngine
            final_status = self.decision_engine.make_decision(status.agent_runs)
            status.status = final_status
            
            if final_status == PipelineStatus.PARTIALLY_COMPLETED:
                failed_agents = [name for name, run in status.agent_runs.items() if run.status in ("failed", "halted")]
                self._log("WARNING", f"[{task_id}] TAMAMLANDI (KISMİ). Başarısız ajanlar: {', '.join(failed_agents)}")
            else:
                self._log("INFO", f"[{task_id}] TAMAMLANDI. Kanıt adımı: {len(status.evidence_chain)}")
                
            status.completed_at = datetime.now(timezone.utc)
            await self._merge_task_memory(task_id, status)
            self._snapshot(status)
            
            # P0-FIX: Gercek SHA-256 kanit hash'i ve gercek sure (ms)
            import hashlib, json as _json
            _chain_bytes = _json.dumps(status.evidence_chain, default=str, sort_keys=True).encode()
            _real_hash = hashlib.sha256(_chain_bytes).hexdigest()
            _duration_ms = int((datetime.now(timezone.utc) - _task_wall_start).total_seconds() * 1000)
            self._emit(TaskCompletedEvent(
                task_id=task_id,
                agent_name="PinealExecutor",
                final_result_hash=_real_hash,
                duration_ms=_duration_ms
            ))
        except InsufficientEvidenceError as e:
            self._log("ERROR", "[" + task_id + "] KANIT KILIDI: " + str(e))
            status.status = "halted_evidence"
            status.completed_at = datetime.now(timezone.utc)
            await self._merge_task_memory(task_id, status)
            self._snapshot(status)
        return status

    def _store_authentic_vector(self, input_data: Dict[str, Any], subject: str, vector: dict | None) -> None:
        """Store a vector only when it was actually calculated from the supplied data.

        A missing vector is represented explicitly in metadata.  It must never be
        replaced with neutral-looking numeric values because downstream resonance
        calculations treat numeric vectors as decision-ready evidence.

        Successful vectors carry an epistemic marker so consumers can distinguish
        LLM-derived estimates from measured evidence without mistaking the
        numbers for ground truth.
        """
        vector_key = f"{subject}_authentic_vector"
        status_key = f"{subject}_authentic_vector_status"
        if vector is None:
            input_data.pop(vector_key, None)
            input_data[status_key] = {
                "available": False,
                "reason": "AUTHENTIC_VECTOR_UNAVAILABLE",
                "epistemic": "unavailable",
            }
            return

        # Stamp the vector itself so any downstream consumer (resonance, UI,
        # evidence export) can see the estimate is model-derived, not measured.
        stamped = dict(vector)
        stamped.setdefault("_epistemic", "model_estimate")
        stamped.setdefault("_provenance", "authentic_vector_llm")
        input_data[vector_key] = stamped
        input_data[status_key] = {
            "available": True,
            "reason": None,
            "epistemic": "model_estimate",
            "provenance": "authentic_vector_llm",
        }

    @staticmethod
    def _holistic_confidence(agent_runs: Dict[str, AgentRun]) -> float:
        """Aggregate finite [0,1] model scores; absence is not neutral confidence."""
        from agent_core.services.confidence import normalize_confidence

        profile_agents = ("passion_mapper", "friction_detector", "cognitive_profiler", "resonance_synthesizer")
        values = []
        for name, run in agent_runs.items():
            if name not in profile_agents or run.status != "completed":
                continue
            score, valid = normalize_confidence(run.confidence)
            if valid:
                values.append(score)
        return round(sum(values) / len(values), 3) if values else 0.0

    async def _calculate_authentic_vector(self, data_dict: dict) -> dict | None:
        import json
        from pydantic import BaseModel
        
        class AuthenticVectorResult(BaseModel):
            depth: float
            energy: float
            achilles_heel: str
            core_wound: str
            dark_detail: str

        prompt = (
            "Sen Pineal-Heretic analitik motorunun baş teşhis uzmanısın (Frekans ve Yara Çıkarıcı).\n"
            "Aşağıdaki veri profilini incele ve şu hedefleri eksiksiz yerine getir:\n"
            "1. 'depth' (psikolojik karmaşıklık, zeka, saklanma) ve 'energy' (agresyon, yoğunluk, dışa vurum) değerlerini 0.1 ile 1.0 arasında derecelendir.\n"
            "2. 'achilles_heel' (Aşil Tendonu): Hedefin zırhındaki o en zayıf, tek bir darbeyle yıkılacağı hassas noktayı (örneğin: terk edilme korkusu, yetersizlik hissi) acımasızca tespit et.\n"
            "3. 'core_wound' (Ana Yara İz): Hedefin tüm savunma mekanizmalarını (maskesini) inşa etmesine sebep olan o geçmiş travmayı veya çocukluk yarasını tanımla.\n"
            "4. 'dark_detail' (Karanlık Detay): Metinlerdeki veya eylemlerindeki en çiğ, en saklamaya çalıştığı ama sızan o çelişkili veya karanlık arzuyu/detayı bul.\n"
            "DİKKAT: ASLA KİBAR OLMA. ASLA YUMUŞATMA. En acımasız, çiğ ve analitik tespiti yap.\n\n"
            f"Profil Verisi:\n{json.dumps(data_dict, ensure_ascii=False)[:3000]}\n\n"
            "Sadece belirtilen alanları içeren geçerli bir JSON döndür."
        )
        try:
            m = "pineal-deep-reasoning" if "20128" in getattr(self.llm_gateway, "openrouter_base_url", "") else None
            res = await self.llm_gateway.query_json(prompt, AuthenticVectorResult, tier=1, model=m)
            return {
                "depth": round(max(0.1, min(res.depth, 1.0)), 3), 
                "energy": round(max(0.1, min(res.energy, 1.0)), 3),
                "achilles_heel": res.achilles_heel,
                "core_wound": res.core_wound,
                "dark_detail": res.dark_detail
            }
        except Exception as e:
            # Do not manufacture a neutral-looking vector.  A numeric fallback
            # would be consumed by ResonanceCalculator as real user evidence.
            self._log("WARNING", f"Vektör hesaplanamadı; veri kullanılamaz olarak işaretlendi: {e}")
            return None

# [AUDIT 2026-10-07 · P2] Burada `executor = PinealExecutor()` duruyordu.
# Kaldırıldı. Gerekçe — `PinealExecutor.__init__` AĞIR ve YAN ETKİLİDİR:
#   * `build_memory_from_env()` / `DecisionConfig.load()` -> ortam + DİSK okur
#     (bozuk/eksik yapılandırmada içe aktarım PATLAR),
#   * `LLMGateway()` / `SearchEngine()` / `VisionAnalyzer()` ve 13 ajanı kurar
#     (içe aktarımda onlarca nesne, gereksiz bellek),
#   * `agent_status_tracker.get_tracker()` çağırır -> modül içe aktarımı
#     yan etkisiyle GLOBAL durum tekilini (singleton) oluşturur.
# Yani `from agent_core.task_executor import AgentTimeoutError` yazmak bile
# tüm bu işleri tetikliyordu. İhtiyacı olan YERİNDE kursun:
#   * FastAPI/API katmanı istemci başına `get_executor(client_id)` ile kurar,
#   * betikler (`main.py`, `scripts/run_task.py`) kendi örneğini kurar.
# Tek tüketici `scripts/archive/e2e_test.py` idi; o da artık kendi örneğini
# kuruyor. Sözleşmeyi `tests/unit/test_task_executor_import_purity.py` kilitler.

