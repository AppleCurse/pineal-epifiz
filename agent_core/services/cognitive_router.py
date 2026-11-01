"""Bilişsel yönlendirici — hangi ajanların koşacağına karar veren beyin.

``analyze(input_data)`` görev girdisini (hedef, kullanıcı, aktif hedefler) okuyup
koşacak ajan listesini ve gerekçesini (``RoutePlan``) üretir.

Girdi disiplini: ``aspasia_goals`` içindeki YABANCI/UYDURMA isimler planı
değiştirmez — yalnız tanımlı hedef kümesi planı etkiler; bilinmeyen hedef
reasoning'e "yok sayıldı" notu olarak yazılır (sessiz yutma yok).

Tüketici: ``agent_core/task_executor.py``.
Test: ``tests/unit/test_router.py``, ``tests/unit/test_consolidation_faz1_5.py``.
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Dict

# ASPASIA TRUE CHIEF LAYER — goal sozlesmesinin TEK kaynagi (burasi).
# Goal id'leri UYDURMA degil: her goal, router'in gercekten secip kanit
# kapisiyla korudugu mevcut uzmanlara haritalanir. Yeni bir registry degil;
# mevcut target-leg uzmanlarinin kullanici-dili taksonomisi.
GOAL_FOCUS: Dict[str, tuple] = {
    "profile_analysis": ("autonomous_verifier", "human_behavior", "passion_mapper",
                         "friction_detector", "cognitive_profiler"),  # semsiye goal
    "contradiction_detection": ("authenticity_auditor",),
    "behavioral_assessment": ("human_behavior",),
    "passion_friction": ("passion_mapper", "friction_detector"),
    "cognitive_tone": ("cognitive_profiler",),
    "outreach_bridge": ("resonance_calc", "pattern_interrupt", "resonance_synthesizer"),
    "autonomous_verification": ("autonomous_verifier",),
}

class RoutePlan(BaseModel):
    agents: List[str]
    reasoning: str
    priority: int  # 1: Kritik, 2: Normal, 3: Opsiyonel
    
    model_config = ConfigDict(extra="forbid")

class CognitiveRouter:
    """
    Hangi ajanların çalışacağına karar veren beyin.

    ASPASIA goal katmanı: kullanıcı AMACI (aspasia_goals) yalnız "ne isteniyor"
    bilgisidir; AJAN SEÇİMİ yine bu sınıfta, kanit/kabiliyet kapilariyla
    yapilir. Goal yoksa davranis birebir eskisiyle aynidir (backward compat).
    """

    @staticmethod
    def _normalize_goals(input_data: Dict) -> "tuple[List[str], List[str]]":
        """aspasia_goals: yabanci/uydurma isimler plani DEGISTIRMEZ; reasoning'e
        dürüst not düşülür. (Aspasia girisinde sema zaten reddeder; bu katman
        dogrudan /api/initiate gonderen ic kullanicilar icin son savunma.)"""
        raw = input_data.get("aspasia_goals") if isinstance(input_data, dict) else None
        if not isinstance(raw, list) or not raw:
            return [], []
        known: List[str] = []
        unknown: List[str] = []
        for g in raw:
            if isinstance(g, str) and g in GOAL_FOCUS:
                if g not in known:
                    known.append(g)
            else:
                unknown.append(str(g)[:40])
        return known, unknown

    @staticmethod
    def _goal_selected(goals: List[str], agent: str) -> bool:
        """Agent aktif goal kumesi tarafindan isteniyor mu?
        'profile_analysis' semsiyesi her seyi kapsar; bos goal = daraltma yok."""
        if not goals or "profile_analysis" in goals:
            return True
        return any(agent in GOAL_FOCUS[g] for g in goals)

    async def analyze(self, input_data: Dict) -> RoutePlan:
        target = input_data.get("target_profile") or {}
        user = input_data.get("user_profile") or {}
        if not isinstance(target, dict):
            target = {}
        if not isinstance(user, dict):
            user = {}

        # A present-but-empty object is not analysis-ready input. Route only
        # agents that can receive actual target/user evidence.
        has_target = bool(
            target.get("username") or target.get("name") or target.get("bio")
            or target.get("posts") or target.get("images")
        )
        has_user = bool(
            user.get("bio") or user.get("posts") or user.get("private_rituals")
            or user.get("late_night_playlist") or user.get("secret_envies")
        )
        
        agents = []
        reasoning = []
        goals, unknown_goals = self._normalize_goals(input_data)
        if unknown_goals:
            reasoning.append(
                "Bilinmeyen goal'ler yok sayıldı (uydurma capability çalıştırılmaz): "
                + ", ".join(unknown_goals)
            )
        if goals:
            reasoning.append("Aspasia amaç seti: " + ", ".join(goals))
        
        # Her zaman önce kendine ayna tut
        if has_user:
            agents.append('mirror_truth')
            reasoning.append("Kullanıcı frekansı tespiti zorunlu")
            # Interpreter is NOT on the default analysis route. open-interpreter
            # is an opt-in code-execution surface, reachable only via
            # /api/experimental/interpreter/execute when ENABLE_INTERPRETER=true
            # AND (optionally) when the same env is set we may still register it
            # for explicit experimental use — never auto-schedule on profile jobs.
            from agent_core.capabilities.state import flag_enabled as _flag_enabled
            if _flag_enabled("ENABLE_INTERPRETER") and _flag_enabled("PINEAL_ROUTE_INTERPRETER"):
                agents.append('interpreter')
                reasoning.append("Serbest Görev Yorumlayıcısı (opt-in)")
        
        # Hedef varsa 360 derece analiz et
        if has_target:
            # OSINT is a forensic stamp executed once by PinealExecutor after
            # the routed analysis. Keeping it out of this route prevents a
            # second provider call and AgentRun overwrite.

            # POLICY bacağı: teyit kullanıcı tercihine göre DÜŞMEZ — kanıt
            # doğrulama doktrini her planda zorunludur.
            agents.append('autonomous_verifier')
            reasoning.append("Otonom Teyit (Arama & Kanıt)")

            # Hedef-tercih bacakları: goal seti yalnız BURAYI daraltabilir;
            # kanit-kapili bacaklar (asagidaki authenticity) tercihle silinmez.
            if self._goal_selected(goals, 'human_behavior'):
                agents.append('human_behavior')
                reasoning.append("Hedef Davranış Analizi")

            if self._goal_selected(goals, 'passion_mapper'):
                agents.append('passion_mapper')
                reasoning.append("Tutku ve Neşe Haritalama")

            if self._goal_selected(goals, 'friction_detector'):
                agents.append('friction_detector')
                reasoning.append("Hassasiyet ve Sınır Tespiti")

            if self._goal_selected(goals, 'cognitive_profiler'):
                agents.append('cognitive_profiler')
                reasoning.append("Bilişsel Ton ve Üslup")

            if 'visual_evidence' in input_data:
                # Kanit varsa denetim her amaclarla kosar (kaldirilamaz kanit
                # bacagi); kanit yoksa goal ASLA zorla ajan ekLEMEZ — honest skip.
                agents.append('authenticity_auditor')
                reasoning.append("Özgünlük ve Tutarlılık Denetimi")
            elif 'contradiction_detection' in goals:
                reasoning.append(
                    "goal contradiction_detection: görsel kanıt yok — "
                    "authenticity_auditor ATLANDI (honest skip, sahte denetim yok)"
                )
            
            # Kullanıcı da hedef de varsa rezonans ve sahici köprü hesapla
            if has_user and self._goal_selected(goals, 'resonance_calc'):
                agents.append('resonance_calc')
                reasoning.append("Sahici Değer ve Uyum Hesabı")
                
                agents.append('pattern_interrupt')
                reasoning.append("İletişim Deseni")

                agents.append('resonance_synthesizer')
                reasoning.append("Sahici İletişim Köprüsü")
        
        return RoutePlan(
            agents=agents,
            reasoning=" | ".join(reasoning),
            priority=1 if has_target and has_user else 2
        )
