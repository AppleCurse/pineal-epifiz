import json
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_core.domain.message_context_models import MessageEvidenceContext
from agent_core.services.upstream_findings import upstream_findings_block


class ScenarioResponse(BaseModel):
    scenario_type: str  # "agresif", "savunmaci", "ilgili"
    expected_target_reaction: str
    our_counter_move: str  # saygılı devam ifadesi (karşı-hamle manipülasyonu DEĞİL)


class GeneratedMessage(BaseModel):
    message: str
    strategy: str
    confidence: float
    compliance_score: float  # 0.0 - 100.0 (Kutsal Kural ihlal skoru)
    dialogue_tree: List[ScenarioResponse]
    # [022] fix: fail-closed default'lar. Model doğrudan kurulursa (LLM sonucu
    # ayrıştırılmadan) "doğrulanmış" sayılmaz; execute() açıkça işaretler.
    data_confidence: bool = False
    fallback_reason: str | None = "not_verified"
    evidence_ids_used: List[str] = Field(default_factory=list)
    decision_context_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class PatternInterrupt:
    """
    Beklenti kırma ve mesaj üretimi.
    Kural: Geri çekil ve boşluk bırak. Reaktif olma.
    """

    # Tek gerçek gözlemden türetilen, kanıt DIŞI hiçbir ayrıntı eklemeyen
    # nötr cümle kılavuzları. Rastgele seçilmez, psikolojik iddia içermez,
    # manipülatif dil barındırmaz.
    OBSERVATION_FRAME = "Bu gözlemi doğrudan ifade eden, kanıt dışı ayrıntı eklemeyen tek cümle."

    async def execute(self, input_data: Dict, memory, llm_gateway) -> GeneratedMessage:
        target_analysis = input_data.get("target_analysis", {})
        user_truth = input_data.get("user_mirror", {})
        sacred_rules = input_data.get("sacred_rules", "")

        # Presence is meaningful: when the controlled canonical handoff was
        # requested, an invalid/empty adapter result must not silently fall
        # back to the legacy target-analysis route.
        context_was_supplied = "message_evidence_context" in input_data
        decision_context: MessageEvidenceContext | None = None
        if context_was_supplied:
            try:
                decision_context = MessageEvidenceContext.model_validate(
                    input_data["message_evidence_context"]
                )
            except (ValidationError, TypeError, ValueError):
                return self._unavailable("invalid_canonical_message_context")
            if decision_context.build_status != "ready" or not decision_context.items:
                return self._unavailable(
                    "canonical_message_context_unavailable",
                    context_id=decision_context.context_id,
                )

        # B6 context mode is deliberately isolated: do not mix legacy target
        # analysis or upstream findings into the treatment prompt.
        upstream_block = "" if context_was_supplied else upstream_findings_block(input_data)
        t_dict = (
            target_analysis.model_dump()
            if hasattr(target_analysis, "model_dump")
            else target_analysis if isinstance(target_analysis, dict) else {}
        )
        if decision_context is not None:
            evidence = [item.content for item in decision_context.items]
            detail = evidence[0]
            target_json = "{}  // omitted: canonical context mode"
        else:
            evidence = self._grounded_evidence(t_dict)
            if not evidence:
                return self._unavailable("insufficient_grounded_evidence")
            top_signal = self._extract_micro_signal(t_dict)
            detail = top_signal if (top_signal and top_signal != "unavailable") else evidence[0]
            target_json = (
                target_analysis.model_dump_json(indent=2)
                if hasattr(target_analysis, "model_dump_json")
                else str(target_analysis)
            )

        user_json = (
            user_truth.model_dump_json(indent=2)
            if hasattr(user_truth, "model_dump_json")
            else str(user_truth)
        )
        canonical_context_text = ""
        if decision_context is not None:
            items_json = json.dumps(
                [item.model_dump(mode="json") for item in decision_context.items],
                ensure_ascii=False,
                indent=2,
            )
            canonical_context_text = (
                "CANONICAL OBSERVATION CONTEXT (adapter-selected; only this context may ground the message):\n"
                f"{items_json}\n"
                "Treat each item as a source-emitted observation, not an independently verified fact. "
                "Do not infer causes, personality, life events, or hidden attributes; absence, inference, "
                "and strategy are not admissible evidence. Return the exact supporting evidence IDs in "
                "evidence_ids_used.\n\n"
            )

        prompt = (
            "Sen evidence-temelli, saygılı ilk iletişim taslağı üreten bir ajansın.\n"
            "Yalnızca aşağıdaki kaynak-tagli gözlemlerden doğrudan desteklenen tek bir açılış cümlesi üret.\n"
            "Psikolojik teşhis, gizli niyet, yara, savunma mekanizması veya karşı tarafın kesin tepkisi hakkında iddia üretme.\n"
            "Rıza, sınır ve saygı kurallarını koru; manipülasyon, baskı veya karşı-hamle planı üretme.\n"
            "Kanıt dışında ayrıntı ekleme; kanıt yetersizse boş mesaj ve data_confidence=false döndür.\n\n"
            f"{canonical_context_text}"
            f"BİRİNCİL GÖZLEM (mesajın tek dayanağı): {detail}\n"
            f"Cümle kılavuzu: {self.OBSERVATION_FRAME}\n\n"
            f"Hedef Analizi:\n{target_json}\n\n"
            f"Kullanıcı Gerçeği:\n{user_json}\n\n"
            f"{sacred_rules}\n\n"
            f"{upstream_block}\n\n"
            "Beklenen JSON formatında çıktını üret. 'message' alanı senin nihai açılış mesajındır.\n"
            "'evidence_ids_used' alanı, mesajın dayandığı ve yalnızca bağlamda izin verilen evidence_id değerlerini içeren listedir; "
            "bağlam yoksa boş liste döndür.\n"
            "'dialogue_tree' listesi içinde 3 farklı senaryo ('agresif', 'savunmaci', 'ilgili') için "
            "beklenen tepkiyi ('expected_target_reaction') ve saygılı devam ifadesini "
            "('our_counter_move') tanımla; karşı-hamle/manipülasyon planı ÜRETME.\n"
            "'compliance_score' alanında ise bu mesajın Kutsal Kurallara (varsa) yüzde kaç (0-100) "
            "oranında uyduğunu değerlendir."
        )

        result = await llm_gateway.query_json_chain(
            prompt, GeneratedMessage, task="dialogue", agent_name="pattern_interrupt"
        )
        if decision_context is not None:
            allowed_ids = {item.evidence_id for item in decision_context.items}
            used_ids = result.evidence_ids_used
            if any(evidence_id not in allowed_ids for evidence_id in used_ids):
                return self._unavailable(
                    "unsupported_canonical_evidence_reference",
                    context_id=decision_context.context_id,
                )
            if result.message.strip() and not used_ids:
                return self._unavailable(
                    "canonical_message_missing_evidence_reference",
                    context_id=decision_context.context_id,
                )
            result.evidence_ids_used = list(dict.fromkeys(used_ids)) if result.message.strip() else []
            result.decision_context_id = decision_context.context_id
        else:
            # Do not accept model-invented canonical references on the legacy path.
            result.evidence_ids_used = []
            result.decision_context_id = None

        # The LLM response has been parsed, and canonical references (when
        # present) have passed a deterministic allow-list check.
        result.data_confidence = True
        result.fallback_reason = None
        return result

    @staticmethod
    def _unavailable(reason: str, *, context_id: str | None = None) -> GeneratedMessage:
        return GeneratedMessage(
            message="",
            strategy="UNAVAILABLE",
            confidence=0.0,
            compliance_score=100.0,
            dialogue_tree=[],
            data_confidence=False,
            fallback_reason=reason,
            decision_context_id=context_id,
        )

    @staticmethod
    def _grounded_evidence(analysis: Dict) -> List[str]:
        evidence = []
        for signal in analysis.get("micro_signals", []) or []:
            value = signal.get("evidence") if isinstance(signal, dict) else getattr(signal, "evidence", None)
            if isinstance(value, str) and value.strip():
                evidence.append(value.strip())
        for quote in analysis.get("evidence_quotes", []) or []:
            if isinstance(quote, str) and quote.strip():
                evidence.append(quote.strip())
        return list(dict.fromkeys(evidence))

    def _extract_specific_detail(self, analysis: Dict) -> str:
        """
        En spesifik gözlem kanıtını çıkar. Ölçüm yoksa UYDURMA İFADE ÜRETİLMEZ
        ("arka plandaki detay" gibi placeholder'lar kaldırıldı).
        """
        signals = analysis.get("micro_signals", [])
        if not signals:
            return "unavailable"

        try:
            top_signal = max(
                signals,
                key=lambda x: x.get("psychological_weight", 0)
                if isinstance(x, dict)
                else getattr(x, "psychological_weight", 0),
            )
            evidence = top_signal.get("evidence", "") if isinstance(top_signal, dict) else getattr(top_signal, "evidence", "")
            return evidence[:50] if evidence else "unavailable"
        except Exception:
            return "unavailable"

    def _extract_micro_signal(self, analysis: Dict) -> str:
        """Return the actual evidence from the strongest available signal."""
        signals = analysis.get("micro_signals", [])
        if not signals:
            return "unavailable"
        try:
            top = max(
                signals,
                key=lambda x: x.get("psychological_weight", 0)
                if isinstance(x, dict)
                else getattr(x, "psychological_weight", 0),
            )
            evidence = top.get("evidence", "") if isinstance(top, dict) else getattr(top, "evidence", "")
            return evidence[:50] if evidence else "unavailable"
        except Exception:
            return "unavailable"

    def _extract_temporal_signal(self, analysis: Dict) -> str | None:
        timestamps = analysis.get("evidence_timestamps", []) or []
        if not timestamps:
            return None
        from agent_core.services.timing_forensics import analyze_timing

        timing = analyze_timing(timestamps)
        if not timing:
            return None
        peak_hour = timing.get("peak_hour")
        if not peak_hour or peak_hour == "--":
            return None
        return f"tepe saat {peak_hour}"
