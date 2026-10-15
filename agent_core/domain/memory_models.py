"""Alan modelleri — görev, profil ve oturum verisinin TİPLİ sözleşmesi.

Kanıt zinciri kayıtları (``AgentRun``), üç kişilik lensinin çıktıları
(``PassionProfile``, ``FrictionProfile``, ``CognitiveStyle``), köprü
(``AuthenticBridge``), 360° birleşik profil (``HolisticProfile``), görev anlık
görüntüsü (``TaskSnapshot``) ve ASPASIA oturumu (``AspasiaSession``) burada
tanımlanır.

Kural: ajan çıktıları sözlük değil MODEL döner; alan eklemek şema değişikliğidir
ve testlerle kilitlenir (``extra="forbid"`` kullanılan yerlerde sessiz alan
şişmesi imkânsızdır).

Tüketici: neredeyse tüm ajanlar, ``task_executor``, ``backend/api.py``.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
import uuid

class AgentRun(BaseModel):
    task_id: str
    agent_name: str
    # pending, running, completed, completed_no_decision, failed, halted,
    # timed_out, unavailable. `completed_no_decision`: ajan koştu ve çıktı
    # verdi ama çıktı KARAR DEĞİL (kendi sözleşmesi data_confidence=False
    # diyor) — güven uydurulmaz, kayıt karar-Grade sayılmaz
    # ([RÖNTGEN 2026-09-23]; bkz. uncertainty_engine.UncertaintyReport.no_decision).
    status: str = "pending"
    #: Koşu KARAR-GRADE mi? `completed_no_decision` için False: ajan koştu, çıktı
    #: kaydedildi ama karar üretilmedi. UI ve DecisionEngine "karar var mı?"
    #: sorusunu yalnız `status == "completed"` ile değil bu alanla da görebilir.
    decision_grade: bool = True
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    input_summary: Dict[str, Any] = {}
    output_summary: Dict[str, Any] = {}
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_ids: List[str] = []
    call_ids: List[str] = []
    warnings: List[str] = []
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    #: [SORUMLULUK ZİNCİRİ] Koşunun mührü. Doğrulanmış ÇIKTILAR
    #: evidence_chain'de taşınır; başarısız/düşük-güven koşuların dürüst
    #: izi (attempted/blockers/next_action) BURADADIR — kanıt zinciri
    #: uydurma kanıtla doldurulmaz (test_deferred_agent_evidence_gate).
    responsibility: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

# --- 360° BÜTÜNCÜL İNSAN PROFİLLEME MODELLERİ ---

class PassionProfile(BaseModel):
    """Kişinin neşe, yaratıcılık, entelektüel merak ve tutku duyduğu alanlar."""
    core_passions: List[str] = []
    energizing_topics: List[str] = []
    flow_triggers: List[str] = []
    sentiment_polarity: float = 0.0  # -1.0 (karamsar) ile +1.0 (coşkulu) arası
    evidence_quotes: List[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"

    model_config = ConfigDict(extra="allow")

class FrictionProfile(BaseModel):
    """Kişinin sınırları, hassasiyetleri, yorulma/tükenme ve şikayet noktaları."""
    sensitivities: List[str] = []
    stress_triggers: List[str] = []
    boundary_signals: List[str] = []
    evidence_quotes: List[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"

    model_config = ConfigDict(extra="allow")

class CognitiveStyle(BaseModel):
    """Kişinin düşünce kalıbı, iletişim üslubu ve sosyal ritmi."""
    communication_tone: str = "unknown"  # doğrudan, analitik, metaforik, samimi, mesafeli
    complexity_level: str = "unknown"  # sade, teknik, kavramsal
    humor_style: Optional[str] = None  # hiciv, ironi, kuru mizah, yok
    social_orientation: str = "unknown"  # toplulukçu, bağımsız, gözlemci
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"

    model_config = ConfigDict(extra="allow")

class AuthenticBridge(BaseModel):
    """Kullanıcı ile hedef arasındaki sahici ortak değerler ve yapıcı iletişim köprüsü."""
    shared_passions: List[str] = []
    complementary_perspectives: List[str] = []
    resonance_score: float = 0.0  # 0.0 - 1.0
    authentic_opening_topic: str = ""
    conversation_starter_rationale: str = ""
    suggested_opening_message: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"

    model_config = ConfigDict(extra="allow")

class HolisticProfile(BaseModel):
    """360 derece tam insan profili."""
    username: str
    passions: Optional[PassionProfile] = None
    frictions: Optional[FrictionProfile] = None
    cognitive: Optional[CognitiveStyle] = None
    bridge: Optional[AuthenticBridge] = None
    verified_claims: List[Dict[str, Any]] = []
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="allow")

from agent_core.domain.pipeline_status import PipelineStatus

class TaskSnapshot(BaseModel):
    task_id: str
    status: PipelineStatus = PipelineStatus.INITIALIZED
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_agent: Optional[str] = None
    planned_agents: List[str] = []
    completed_agents: List[str] = []
    halted_reason: Optional[str] = None
    resonance_score: Optional[float] = None
    required_threshold: float = 0.70
    agent_runs: Dict[str, AgentRun] = {}
    evidence_chain: List[Dict[str, Any]] = []
    holistic_profile: Optional[HolisticProfile] = None
    follower_audit: Optional[Dict[str, Any]] = None
    timing_forensics: Optional[Dict[str, Any]] = None
    psychodynamic_depth: Optional[Dict[str, Any]] = None  # GÖREV 2.3/2.4
    depth_report: Optional[Dict[str, Any]] = None
    visual_evidence: Optional[Dict[str, Any]] = None
    shadow_profile: Optional[Dict[str, Any]] = None
    osint_footprint: Optional[Dict[str, Any]] = None
    telemetry: Optional[Dict[str, Any]] = None
    #: [DESTEK AKIŞI] Desteğe açılan talepler (pending → resolved).
    #: Ekleyici JSON alanı: eski istemciler için uyumlu.
    support_requests: List[Dict[str, Any]] = []
    #: [RESUME] Her tamamlanan ajanın input_data'ya yuttuğu anahtarlar —
    #: görev kaldığı yerden devam ederken geri yüklenir.
    ingested_outputs: Dict[str, Dict[str, Any]] = {}

    # Pineal deterministic 7-Pillar outputs
    frequency_map: Optional[Dict[str, Any]] = None
    seismos_events: Optional[Dict[str, Any]] = None
    void_map: Optional[Dict[str, Any]] = None
    strata_map: Optional[Dict[str, Any]] = None
    gravity_map: Optional[Dict[str, Any]] = None
    pulse_map: Optional[Dict[str, Any]] = None
    key_matrix: Optional[Dict[str, Any]] = None
    pillar_bundle: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

class ChatMessage(BaseModel):
    role: str  # user, aspasia
    content: str
    timestamp: datetime

class AspasiaSession(BaseModel):
    session_id: str
    client_id: str
    active_task_id: Optional[str] = None
    conversation_history: List[ChatMessage] = []
    referenced_evidence: List[str] = []

    @classmethod
    def create(cls, client_id: str) -> "AspasiaSession":
        return cls(
            session_id=str(uuid.uuid4()),
            client_id=client_id,
        )

    def add_message(self, role: str, content: str):
        self.conversation_history.append(
            ChatMessage(role=role, content=content, timestamp=datetime.now(timezone.utc))
        )
