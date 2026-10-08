from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict

# Import yeni modüller
from agent_core.nlp.dark_nlp import EmbeddedCommandEngine, PresuppositionEngine
from agent_core.psychology.dark_triad import DarkTriadAnalyzer, DarkTriadProfile
from agent_core.agents.pattern_interrupt import PatternInterrupt
from agent_core.agents.mirror_truth import MirrorOfTruth
from agent_core.services.llm_gateway import LLMGateway

class ShadowResult(BaseModel):
    message: str
    dark_profile: Dict
    strategy: str
    nlp_sequence: list
    confidence: float
    data_confidence: bool = True          # False → LLM kullanılamadı, NLP deterministik
    fallback_reason: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class ShadowExecutor:
    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        # [030] fix: gateway enjekte edilebilir. PinealExecutor kendi (anahtarlı)
        # gateway'ini verir; yetimsiz ikinci gateway production'da LLM katmanlarını
        # yapısal olarak hep fallback'e düşürüyordu.
        self.dark_nlp = EmbeddedCommandEngine()
        self.presupposition = PresuppositionEngine()
        self.dark_triad = DarkTriadAnalyzer()
        self.pattern = PatternInterrupt()
        self.llm_gateway = llm_gateway or LLMGateway()
        self.mirror = MirrorOfTruth(self.llm_gateway)

    @staticmethod
    def _has_target_evidence(task_input: Dict) -> bool:
        """Hedef üzerinde gerçek analiz girdisi var mı?

        [019] kapısı: hedef bio/posts/username/name/images yoksa shadow
        stratejisi ve mesajı ÜRETİLEMEZ; sıfır veriden 'empathy' şablonu
        sahte kanıt olur.
        """
        target = task_input.get("target_profile", {})
        if not isinstance(target, dict):
            target = {}
        return bool(
            target.get("bio") or target.get("posts")
            or target.get("username") or target.get("name")
            or target.get("images")
        )

    async def execute(self, task_input: Dict) -> ShadowResult:
        import logging
        log = logging.getLogger(__name__)

        if not self._has_target_evidence(task_input):
            log.warning(
                "ShadowExecutor: hedef kanıtı yok; shadow profili üretilmedi "
                "(sahte strateji/mesaj yasak)."
            )
            return ShadowResult(
                message="",
                dark_profile=DarkTriadProfile().model_dump(),
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="target_evidence_unavailable",
            )

        # 1. Strateji kaynagı (GÖREV 2 artıgı): psychodynamic_depth verdict
        # ok ise BIRINCIL kaynaktır (yapısal indeksler); yoksa/bozuksa legacy
        # eşik yolu denenir (analyze() sıfırları -> 'unavailable').
        dark = self.dark_triad.analyze(task_input.get('target_profile', {}))
        _depth = task_input.get("psychodynamic_depth")
        if isinstance(_depth, dict) and _depth.get("verdict") == "ok":
            strategy = self.dark_triad.strategy_from_depth(_depth)
        else:
            strategy = self.dark_triad.generate_strategy(dark)

        # [024 devamı] Gözlemlenebilir markör yoksa strateji ÜRETİLMEZ;
        # kısmi markör eşiği geçmediyse de strateji türetilmez. Sahte
        # "empathy" etiketi ve şablon mesaj bu durumda yasaktır.
        if strategy["vector"] == "unavailable":
            return ShadowResult(
                message="",
                dark_profile=dark.model_dump(),
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="dark_triad_markers_unobserved",
            )
        if strategy["vector"] == "unobserved":
            return ShadowResult(
                message="",
                dark_profile=dark.model_dump(),
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="strategy_unobserved",
            )

        routed_pattern = task_input.get("_pattern_interrupt") or {}
        gate_blocked_ids = routed_pattern.get("claim_gate_blocked_ids")
        if isinstance(gate_blocked_ids, list) and gate_blocked_ids:
            return ShadowResult(
                message="",
                dark_profile=dark.model_dump(),
                strategy=strategy.get("vector", "unavailable"),
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="claim_gate_blocked_same_claim",
            )

        # 2. Mirror (LLM gerektirir — fallback ile korumalı)
        # [054] fix: task_input içinde önceden üretilmiş user_mirror varsa onu kullan;
        # aynı görev için gereksiz ikinci kez Mirror LLM çağırma.
        mirror_result = task_input.get("user_mirror")
        if mirror_result is None:
            try:
                mirror_result = await self.mirror.execute(
                    {
                        "user_profile": task_input.get("user_profile", {}),
                        "user_context": task_input.get("user_context", {}),
                    }
                )
            except Exception as e:
                log.warning("ShadowExecutor: Mirror LLM atlandı: %s", e)

        # 3. NLP Sequence (LLM gerektirmez — deterministik)
        # Kullanıcı istem vermediyse varsayılan eylem ÜRETİLMEZ (eski
        # 'cevap ver' default'u sahte istemdi).
        desired_action = task_input.get('desired_action')
        nlp_seq = self.dark_nlp.generate_sequence(
            task_input.get('target_profile', {}),
            desired_action if isinstance(desired_action, str) else ''
        )

        # 4. Presupposition Chain (LLM gerektirmez — deterministik)
        # Kullanıcı inanç listesi vermediyse boş; sahte varsayılan inanç
        # ('anlaşılmak', 'özel hissetmek') artık enjekte edilmez.
        beliefs = task_input.get('target_beliefs') or []
        presup_chain = self.presupposition.generate_chain(beliefs)

        # 5. Pattern Interrupt (LLM gerektirir — fallback ile korumalı)
        # [BOSS-7] Rota zaten bir pattern mesajı ürettiyse LLM'e İKİNCİ kez
        # sorulmaz: görev başına aynı şema (GeneratedMessage) iki kez
        # faturalanıyordu. Kayıt yoksa eski yol (kendi LLM çağrısı) aynen sürer.
        routed_pattern = task_input.get("_pattern_interrupt") or {}
        routed_message = str(routed_pattern.get("message") or "").strip()
        pattern_message = routed_message or strategy.get('vector') or "unavailable"
        reuse_routed = bool(routed_message and routed_message != "unavailable")
        try:
            if not reuse_routed:
                existing_target_analysis = task_input.get("target_analysis") or {}
                if existing_target_analysis and isinstance(existing_target_analysis, dict):
                    p_analysis = dict(existing_target_analysis)
                    if not p_analysis.get("micro_signals"):
                        p_analysis["micro_signals"] = [
                            {
                                'signal_type': 'defense',
                                'confidence': 0.85,
                                'location': 'behavioral',
                                'evidence': f"Strateji vektörü: {strategy.get('vector', 'direct')}",
                                'psychological_weight': 0.7,
                            }
                        ]
                else:
                    p_analysis = {
                        'observations': [],
                        'possible_interpretations': [strategy['vector']],
                        'confidence': 0.85,
                        'alternative_interpretations': [],
                        'unsupported_claims': [],
                        'resonance_potential': dark.exploitability,
                        'micro_signals': [
                            {
                                'signal_type': 'defense',
                                'confidence': 0.85,
                                'location': 'behavioral',
                                'evidence': f"Strateji vektörü: {strategy['vector']}",
                                'psychological_weight': 0.7,
                            }
                        ]
                    }

                p_mirror = (
                    mirror_result.model_dump()
                    if hasattr(mirror_result, "model_dump")
                    else (mirror_result if isinstance(mirror_result, dict) else {})
                )
                pattern_input = {
                    'target_analysis': p_analysis,
                    'user_mirror': p_mirror,
                    'sacred_rules': task_input.get("sacred_rules", "")
                }
                pattern_result = await self.pattern.execute(pattern_input, None, self.llm_gateway)
                if pattern_result and getattr(pattern_result, "message", None):
                    pattern_message = pattern_result.message
        except Exception as e:
            log.warning("ShadowExecutor: Pattern LLM atlandı: %s", e)

        # Fallback mekanizması: pattern_message boşsa veya unavailable ise strateji taktiğini kullan
        if not pattern_message or pattern_message == "unavailable":
            pattern_message = strategy.get('tactic') or strategy.get('vector') or "Doğal ve dengeli ilk temas."

        # 6. Birleştir
        final_message = self._synthesize(
            pattern_message,
            nlp_seq,
            presup_chain,
            strategy
        )

        # [066] fix: exploitability psikolojik manipülasyon metriğidir; ölçüm
        # güveni (confidence) olarak telemetriye verilemez. Ölçüm güveni, markör
        # gözlem kapsamından türetilir.
        observed_traits = sum(
            1 for t in ("machiavellianism", "narcissism", "psychopathy")
            if getattr(dark, t, 0.0) > 0.0
        )
        analysis_confidence = (
            min(round(0.5 + (observed_traits * 0.15), 2), 1.0)
            if observed_traits > 0 else 0.0
        )

        return ShadowResult(
            message=final_message,
            dark_profile=dark.model_dump(),
            strategy=strategy['vector'],
            nlp_sequence=nlp_seq,
            confidence=analysis_confidence
        )
    
    def _synthesize(self, base_msg: str, nlp_seq: list, presup: list, strategy: Dict) -> str:
        """Tüm katmanları birleştir"""
        presup_intro = presup[0]['sentence'] if presup else ""
        nlp_command = nlp_seq[1]['text'] if len(nlp_seq) > 1 else ""

        parts = [p for p in (presup_intro, base_msg, nlp_command) if p and p.strip()]
        return " ".join(parts).strip()
