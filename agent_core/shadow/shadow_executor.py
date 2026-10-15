"""Gölge yürütücü — NLP katmanlarını temel mesajın ÜZERİNE bindirir.

Katmanlar: gömülü komut motoru, varsayım (presupposition) zinciri ve strateji
sentezi. ``_synthesize`` hepsini tek mesaja indirger (``ShadowResult``).

Dürüstlük kapısı: hedef üzerinde GERÇEK analiz kanıtı yoksa
(``_has_target_evidence``) ajan mesaj ÜRETMEZ — süslenmiş boş içerik yerine
gerekçeli ret döner.

Tüketici: ``task_executor`` + ``backend/api.py`` (``/api/experimental/shadow/*``).
Test: ``tests/unit/test_dark_nlp_and_shadow.py``.
"""

from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict

# Import yeni modüller
from agent_core.nlp.dark_nlp import EmbeddedCommandEngine, PresuppositionEngine
from agent_core.psychology.dark_triad import DarkTriadAnalyzer, DarkTriadProfile
from agent_core.agents.pattern_interrupt import PatternInterrupt
from agent_core.agents.mirror_truth import MirrorOfTruth
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.confidence import normalize_confidence

class ShadowResult(BaseModel):
    message: str
    dark_profile: Dict
    strategy: str
    nlp_sequence: list
    confidence: float
    data_confidence: bool = False  # Strategy basis is grounded in validated input.
    fallback_reason: Optional[str] = "unavailable"
    trait_scores_measured: bool = False  # Dark-triad scores are not depth strategy scores.

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

    @staticmethod
    def _dark_profile_payload(dark: DarkTriadProfile) -> tuple[Dict, bool, list[float]]:
        """Represent unmeasured legacy trait defaults as null in the API output.

        The depth strategy is not a narcissism/machiavellianism/psychopathy
        score. The current DarkTriadAnalyzer deliberately emits zero defaults
        after lexical scoring was removed, so those defaults must not be shown
        as measured zeros.
        """
        payload = dark.model_dump()
        trait_scores: list[float] = []
        for trait in ("machiavellianism", "narcissism", "psychopathy"):
            score, valid = normalize_confidence(getattr(dark, trait, None))
            if valid and score > 0.0:
                payload[trait] = score
                trait_scores.append(score)
            else:
                payload[trait] = None
        exploitability, valid_exploitability = normalize_confidence(
            getattr(dark, "exploitability", None)
        )
        payload["exploitability"] = (
            exploitability if valid_exploitability and exploitability > 0.0 else None
        )
        return payload, bool(trait_scores), trait_scores

    @staticmethod
    def _depth_strategy_confidence(depth: Dict, strategy: Dict) -> tuple[float, Optional[str]]:
        """Validate the selected depth signal and derive confidence from its source channels.

        This deliberately does not inspect the legacy dark-triad feature scores.
        A depth strategy is grounded only when its trigger is finite/in-range
        and the channel(s) used to derive it report non-zero completeness.
        """
        global_confidence, valid_confidence = normalize_confidence(depth.get("confidence"))
        if not valid_confidence or global_confidence <= 0.0:
            return 0.0, "invalid_depth_confidence"

        channels = depth.get("channels")
        if not isinstance(channels, dict):
            return 0.0, "invalid_depth_channels"

        def channel_completeness(name: str) -> Optional[float]:
            channel = channels.get(name)
            if not isinstance(channel, dict):
                return None
            completeness, valid = normalize_confidence(channel.get("completeness"))
            return completeness if valid and completeness > 0.0 else None

        vector = strategy.get("vector")
        required_channels: list[str]
        if vector == "mirroring":
            reaction, valid_reaction = normalize_confidence(depth.get("reaction_formation_index"))
            if not valid_reaction or reaction < 0.40:
                return 0.0, "invalid_depth_strategy_signal"
            required_channels = ["declaration", "staging"]
        elif vector == "alliance":
            declaration = channels.get("declaration")
            signals = declaration.get("signals") if isinstance(declaration, dict) else None
            repetition, valid_repetition = normalize_confidence(
                signals.get("repetition_score") if isinstance(signals, dict) else None
            )
            if not valid_repetition or repetition < 0.40:
                return 0.0, "invalid_depth_strategy_signal"
            required_channels = ["declaration"]
        elif vector == "thrill":
            rhythm = channels.get("rhythm")
            signals = rhythm.get("signals") if isinstance(rhythm, dict) else None
            signals = signals if isinstance(signals, dict) else {}
            ruptures = signals.get("n_ruptures")
            kinds = signals.get("rupture_kinds")
            has_rupture = (
                isinstance(ruptures, int) and not isinstance(ruptures, bool) and ruptures >= 1
            ) or (isinstance(kinds, list) and "entropy_jump" in kinds)
            if not has_rupture:
                return 0.0, "invalid_depth_strategy_signal"
            required_channels = ["rhythm"]
        else:
            return 0.0, "strategy_source_unavailable"

        completeness = [channel_completeness(name) for name in required_channels]
        if any(value is None for value in completeness):
            return 0.0, "depth_channel_incomplete"
        return min([global_confidence, *(value for value in completeness if value is not None)]), None

    async def execute(self, task_input: Dict) -> ShadowResult:
        import logging
        log = logging.getLogger(__name__)

        if not self._has_target_evidence(task_input):
            log.warning(
                "ShadowExecutor: hedef kanıtı yok; shadow profili üretilmedi "
                "(sahte strateji/mesaj yasak)."
            )
            empty_profile, trait_scores_measured, _ = self._dark_profile_payload(DarkTriadProfile())
            return ShadowResult(
                message="",
                dark_profile=empty_profile,
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="target_evidence_unavailable",
                trait_scores_measured=trait_scores_measured,
            )

        # 1. Strateji kaynagı (GÖREV 2 artıgı): psychodynamic_depth verdict
        # ok ise BIRINCIL kaynaktır (yapısal indeksler); yoksa/bozuksa legacy
        # eşik yolu denenir (analyze() sıfırları -> 'unavailable').
        dark = self.dark_triad.analyze(task_input.get('target_profile', {}))
        dark_profile_payload, trait_scores_measured, measured_trait_scores = (
            self._dark_profile_payload(dark)
        )
        _depth = task_input.get("psychodynamic_depth")
        using_depth = isinstance(_depth, dict) and _depth.get("verdict") == "ok"
        if using_depth:
            strategy = self.dark_triad.strategy_from_depth(_depth)
        else:
            strategy = self.dark_triad.generate_strategy(dark)

        # [024 devamı] Gözlemlenebilir markör yoksa strateji ÜRETİLMEZ;
        # kısmi markör eşiği geçmediyse de strateji türetilmez. Sahte
        # "empathy" etiketi ve şablon mesaj bu durumda yasaktır.
        if strategy["vector"] == "unavailable":
            return ShadowResult(
                message="",
                dark_profile=dark_profile_payload,
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="dark_triad_markers_unobserved",
                trait_scores_measured=trait_scores_measured,
            )
        if strategy["vector"] == "unobserved":
            return ShadowResult(
                message="",
                dark_profile=dark_profile_payload,
                strategy="unavailable",
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="strategy_unobserved",
                trait_scores_measured=trait_scores_measured,
            )

        allowed_strategies = {"mirroring", "alliance", "thrill"}
        if using_depth:
            analysis_confidence, confidence_reason = self._depth_strategy_confidence(
                _depth, strategy
            )
            if confidence_reason is not None or strategy.get("vector") not in allowed_strategies:
                return ShadowResult(
                    message="",
                    dark_profile=dark_profile_payload,
                    strategy="unavailable",
                    nlp_sequence=[],
                    confidence=0.0,
                    data_confidence=False,
                    fallback_reason=confidence_reason or "strategy_source_unavailable",
                    trait_scores_measured=trait_scores_measured,
                )
        else:
            if strategy.get("vector") not in allowed_strategies or not measured_trait_scores:
                return ShadowResult(
                    message="",
                    dark_profile=dark_profile_payload,
                    strategy="unavailable",
                    nlp_sequence=[],
                    confidence=0.0,
                    data_confidence=False,
                    fallback_reason="legacy_trait_scores_unavailable",
                    trait_scores_measured=trait_scores_measured,
                )
            analysis_confidence = round(
                sum(measured_trait_scores) / len(measured_trait_scores), 3
            )
            if analysis_confidence <= 0.0:
                return ShadowResult(
                    message="",
                    dark_profile=dark_profile_payload,
                    strategy="unavailable",
                    nlp_sequence=[],
                    confidence=0.0,
                    data_confidence=False,
                    fallback_reason="legacy_trait_scores_unavailable",
                    trait_scores_measured=trait_scores_measured,
                )

        routed_pattern = task_input.get("_pattern_interrupt") or {}
        gate_blocked_ids = routed_pattern.get("claim_gate_blocked_ids")
        if isinstance(gate_blocked_ids, list) and gate_blocked_ids:
            return ShadowResult(
                message="",
                dark_profile=dark_profile_payload,
                strategy=strategy.get("vector", "unavailable"),
                nlp_sequence=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="claim_gate_blocked_same_claim",
                trait_scores_measured=trait_scores_measured,
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

        return ShadowResult(
            message=final_message,
            dark_profile=dark_profile_payload,
            strategy=strategy["vector"],
            nlp_sequence=nlp_seq,
            confidence=analysis_confidence,
            data_confidence=bool(final_message.strip() and analysis_confidence > 0.0),
            fallback_reason=None if final_message.strip() and analysis_confidence > 0.0 else "empty_strategy_message",
            trait_scores_measured=trait_scores_measured,
        )
    
    def _synthesize(self, base_msg: str, nlp_seq: list, presup: list, strategy: Dict) -> str:
        """Tüm katmanları birleştir"""
        presup_intro = presup[0]['sentence'] if presup else ""
        nlp_command = nlp_seq[1]['text'] if len(nlp_seq) > 1 else ""

        parts = [p for p in (presup_intro, base_msg, nlp_command) if p and p.strip()]
        return " ".join(parts).strip()
