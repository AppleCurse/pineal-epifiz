"""Hedef ruh hâli profiler'ı — üç lensin ortak omurgası (tek gerçek kaynak).

``profile_passions`` / ``profile_frictions`` / ``profile_cognitive`` üçlüsü aynı
kanıt ayrıştırmasını (``_extract_target_context``: metin + görsel delil) paylaşır.
İnce kabuklar (``passion_mapper``, ``friction_detector``, ``cognitive_profiler``)
yalnız bu sınıfı çağırır — kopyalanmış prompt yasaktır.

``profile_all`` üç analizi sıralı/paralel tek koşuda birleştirir. Boş kanıtta
skor/uydurma üretilmez; veri güveni açıkça raporlanır.

Test: ``tests/unit/test_cognitive_profiler.py``, ``tests/unit/test_friction_detector.py``.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from agent_core.domain.memory_models import PassionProfile, FrictionProfile, CognitiveStyle
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.upstream_findings import upstream_findings_block
from agent_core.services.confidence import normalize_confidence
# [P0 · DENETİM 2026-10-16] Kanıt tipi ayrımı: gönderi ↔ arama sonucu.
from agent_core.domain.content_basis import extract_public_text, render_corpus_block

logger = logging.getLogger(__name__)


class TargetPsycheProfiler:
    """
    Hedef Kişilik ve Derinlik Birleşik Profiler'ı (Unified Target Psyche Engine).

    Eski mimarideki passion_mapper, friction_detector ve cognitive_profiler
    ajanlarının veri hazırlama, görsel kanıt işleme ve LLM çıkarım mantıklarını
    tek bir çatı altında birleştiren mimari omurga.

    Hem tek tek facet analizini (backward-compatible) hem de tek seferlik
    bütünleşik çıkarımı (unified multi-lens) destekler.
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    @staticmethod
    def _extract_target_context(payload: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any], str, Dict[str, Any]]:
        """Tüm lensler için tipli hedef bağlamını ve görsel delilleri ayrıştırır.

        [P0 · DENETİM 2026-10-16] Metin corpus'u KANIT TİPİYLE birlikte
        hazırlanır: platform gönderisi ile arama sonucu (snippet) LLM'e
        "gönderi" diye gider. `posts` alanı artık yalnız gerçek gönderileri
        taşır; snippet'lar `search_snippets` altından etiketli gelir.
        """
        payload = payload if isinstance(payload, dict) else {}
        raw_target = payload.get("target_profile")
        target = raw_target if isinstance(raw_target, dict) else {}
        raw_bio = target.get("bio")
        bio = raw_bio.strip() if isinstance(raw_bio, str) else ""
        raw_visual = payload.get("visual_evidence")
        visual_evidence = raw_visual if isinstance(raw_visual, dict) else {}

        corpus_items = extract_public_text(target)
        posts_text = render_corpus_block(
            corpus_items,
            limit=10,
            empty_text="Gönderi metni bulunamadı.",
        )
        upstream_block = upstream_findings_block(payload)
        return bio, posts_text, visual_evidence, upstream_block, target

    # -------------------------------------------------------------------------
    # 1. PASSIONS LENS
    # -------------------------------------------------------------------------
    async def profile_passions(self, payload: Dict[str, Any]) -> PassionProfile:
        """Hedefin tutku, neşe ve coşku alanlarını haritalandırır."""
        bio, posts_text, visual_evidence, upstream_block, _ = self._extract_target_context(payload)

        visual_text = f"""
Görsel İnceleme Kanıtları (Multimodal Vision):
- Tespit Edilen Somut Nesneler: {visual_evidence.get('detected_objects', [])}
- Mekanlar ve Ortam: {visual_evidence.get('environment_and_places', [])}
- Estetik ve Görsel Dil: {visual_evidence.get('aesthetic_style', '')}
- Yapılan Eylemler: {visual_evidence.get('activity_signals', [])}
- Görsel Özeti: {visual_evidence.get('visual_evidence_summary', '')}
""" if visual_evidence else "Görsel kanıt bulunamadı."

        if not bio and posts_text == "Gönderi metni bulunamadı." and not visual_evidence:
            return PassionProfile(
                core_passions=[],
                energizing_topics=[],
                flow_triggers=[],
                sentiment_polarity=0.0,
                evidence_quotes=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_target_data",
            )

        prompt = f"""
Aşağıdaki sosyal medya profil verilerini ve fotoğraflardan çıkarılan SOMUT görsel kanıtları incele.
{upstream_block}
Bu kişinin GERÇEKTE neye tutku duyduğunu, hangi konuların ve eylemlerin onu motive ettiğini analiz et.
Asla genel geçer astroloji veya kişisel gelişim genellemeleri yapma. 
Yalnızca verilen metinlerdeki ve fotoğraflarda fiilen tespit edilen somut nesne/mekan delillerine dayan.

Hedef Biyografi:
"{bio}"

Hedef Metin Corpus'u (kanıt tipi etiketli; 'arama sonucu' satırları hedefin
yazdığı gönderi DEĞİLDİR):
{posts_text}

{visual_text}

Confidence kuralı: confidence alanını yalnızca verilen doğrudan kanıtın tamlığına göre 0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür.

Aşağıdaki JSON şemasına birebir uygun yanıt ver:
{{
  "core_passions": ["Kişinin somut paylaşımlarından ve fotoğraflarından kanıtlanan 1-3 ana tutku alanı"],
  "energizing_topics": ["Konuşmaktan, üretmekten veya görselleştirmekten keyif aldığı spesifik konular"],
  "flow_triggers": ["Onu üretken veya coşkulu kılan somut tetikleyiciler"],
  "sentiment_polarity": 0.6,
  "evidence_quotes": ["Metinden veya görsel kanıttan doğrudan alıntılanan somut detaylar"],
  "confidence": 0.8
}}
"""
        try:
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=PassionProfile,
                task="depth",
                temperature=0.3,
                agent_name="passion_mapper",
            )
            has_passions = bool(
                result.core_passions or result.energizing_topics or result.evidence_quotes
            )
            conf, confidence_valid = normalize_confidence(getattr(result, "confidence", None))
            has_valid_evidence = has_passions and confidence_valid and conf > 0.0
            reason = (
                None if has_valid_evidence
                else "invalid_model_confidence" if not confidence_valid
                else "insufficient_grounded_evidence" if not has_passions
                else "model_confidence_zero"
            )
            return result.model_copy(update={
                "confidence": conf if has_valid_evidence else 0.0,
                "data_confidence": has_valid_evidence,
                "fallback_reason": reason,
            })
        except Exception as e:
            logger.warning(f"TargetPsycheProfiler (Passions) LLM hatası: {e}")
            return PassionProfile(
                core_passions=[],
                energizing_topics=[],
                flow_triggers=[],
                sentiment_polarity=0.0,
                evidence_quotes=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable",
            )

    # -------------------------------------------------------------------------
    # 2. FRICTIONS LENS
    # -------------------------------------------------------------------------
    async def profile_frictions(self, payload: Dict[str, Any]) -> FrictionProfile:
        """Hedefin sınırlarını, hassasiyetlerini ve şikayet noktalarını haritalandırır."""
        bio, posts_text, visual_evidence, upstream_block, _ = self._extract_target_context(payload)

        visual_text = f"""
Görsel İnceleme Kanıtları (Multimodal Vision):
- Tespit Edilen Nesneler: {visual_evidence.get('detected_objects', [])}
- Mekanlar ve Ortam: {visual_evidence.get('environment_and_places', [])}
- Estetik Tarz: {visual_evidence.get('aesthetic_style', '')}
- Görsel Özeti: {visual_evidence.get('visual_evidence_summary', '')}
""" if visual_evidence else "Görsel kanıt bulunamadı."

        if not bio and posts_text == "Gönderi metni bulunamadı." and not visual_evidence:
            return FrictionProfile(
                sensitivities=[],
                stress_triggers=[],
                boundary_signals=[],
                evidence_quotes=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_target_data"
            )

        prompt = f"""
Aşağıdaki profil verilerini ve fotoğraflardan tespit edilen görsel kanıtları incele.
{upstream_block}
Bu kişinin iletişimde nelere mesafe koyduğunu, nelere karşı hassas veya eleştirel olduğunu,
nelerin onu yorup rahatsız edebileceğini tespit et.
Profil az paylaşımlı, ketum veya mesafeli ise, bu mahremiyet ve sessizlik tercihini doğrudan somut bir sınır sinyali (boundary_signals) olarak işle.
Asla sahte derin travmalar veya klişe uydurma. Sadece metinlerdeki ve fotoğraflardaki gerçek sınırları ve hassasiyetleri bul.

Hedef Biyografi:
"{bio}"

Hedef Metin Corpus'u (kanıt tipi etiketli; 'arama sonucu' satırları hedefin
yazdığı gönderi DEĞİLDİR):
{posts_text}

{visual_text}

Confidence kuralı: confidence alanını verilen doğrudan ve gözlemsel kanıtın tamlığına göre 0.1 ile 1.0 arasında ölç.

Aşağıdaki JSON şemasına birebir uygun yanıt ver:
{{
  "sensitivities": ["Kişinin hoşlanmadığı, mesafeli durduğu veya hassas olduğu somut konular"],
  "stress_triggers": ["Onu yoran, tepkisini çeken durumlar"],
  "boundary_signals": ["İletişimde aşılmaması gereken kişisel sınırlar"],
  "evidence_quotes": ["Metinden veya fotoğraflardan doğrudan alıntılanan somut kanıtlar"],
  "confidence": 0.8
}}
"""
        try:
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=FrictionProfile,
                task="depth",
                temperature=0.3,
                agent_name="friction_detector",
            )
            has_frictions = bool(
                result.sensitivities or result.stress_triggers or result.boundary_signals or result.evidence_quotes
            )
            # Empty model findings are not replaced with generic personality
            # claims or a confidence baseline.
            conf, confidence_valid = normalize_confidence(getattr(result, "confidence", None))
            has_valid_evidence = has_frictions and confidence_valid and conf > 0.0
            reason = (
                None if has_valid_evidence
                else "invalid_model_confidence" if not confidence_valid
                else "insufficient_grounded_evidence" if not has_frictions
                else "model_confidence_zero"
            )
            return result.model_copy(update={
                "confidence": conf if has_valid_evidence else 0.0,
                "data_confidence": has_valid_evidence,
                "fallback_reason": reason,
            })
        except Exception as e:
            logger.warning(f"TargetPsycheProfiler (Frictions) LLM hatası: {e}")
            return FrictionProfile(
                sensitivities=[],
                stress_triggers=[],
                boundary_signals=[],
                evidence_quotes=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable",
            )

    # -------------------------------------------------------------------------
    # 3. COGNITIVE LENS
    # -------------------------------------------------------------------------
    async def profile_cognitive(self, payload: Dict[str, Any]) -> CognitiveStyle:
        """Hedefin dilbilimsel tonunu, iletişim üslubunu ve karmaşıklık düzeyini haritalandırır."""
        bio, posts_text, visual_evidence, upstream_block, _ = self._extract_target_context(payload)

        visual_style = visual_evidence.get('aesthetic_style', '') if visual_evidence else ''
        visual_text = f"Fotoğraflardaki Görsel ve Estetik Dil: {visual_style}" if visual_style else ""

        if not bio and posts_text == "Gönderi metni bulunamadı." and not visual_evidence:
            return CognitiveStyle(
                communication_tone="",
                complexity_level="",
                humor_style=None,
                social_orientation="",
                confidence=0.0,
                data_confidence=False,
                fallback_reason="no_target_data"
            )

        prompt = f"""
Aşağıdaki metinlerin dilbilimsel üslubunu, iletişim ritmini ve fotoğrafların estetik dilini incele.
{upstream_block}
Kişinin nasıl bir iletişim tarzı benimsediğini analiz et.

Hedef Biyografi:
"{bio}"

Hedef Metin Corpus'u (kanıt tipi etiketli; 'arama sonucu' satırları hedefin
yazdığı gönderi DEĞİLDİR):
{posts_text}

{visual_text}

Confidence kuralı: confidence alanını yalnızca verilen doğrudan kanıtın tamlığına göre 0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür.

Aşağıdaki JSON şemasına birebir uygun yanıt ver:
{{
  "communication_tone": "doğrudan | analitik | samimi | mesafeli | metaforik",
  "complexity_level": "sade | teknik | kavramsal",
  "humor_style": "ironi | hiciv | kuru mizah | yok",
  "social_orientation": "toplulukçu | bağımsız | gözlemci",
  "confidence": 0.8
}}
"""
        try:
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=CognitiveStyle,
                task="depth",
                temperature=0.3,
                agent_name="cognitive_profiler",
            )
            has_style = bool(
                result.communication_tone and result.communication_tone != "unknown"
            )
            conf, confidence_valid = normalize_confidence(getattr(result, "confidence", None))
            has_valid_evidence = has_style and confidence_valid and conf > 0.0
            reason = (
                None if has_valid_evidence
                else "invalid_model_confidence" if not confidence_valid
                else "insufficient_grounded_evidence" if not has_style
                else "model_confidence_zero"
            )
            return result.model_copy(update={
                "confidence": conf if has_valid_evidence else 0.0,
                "data_confidence": has_valid_evidence,
                "fallback_reason": reason,
            })
        except Exception as e:
            logger.warning(f"TargetPsycheProfiler (Cognitive) LLM hatası: {e}")
            return CognitiveStyle(
                communication_tone="",
                complexity_level="",
                humor_style=None,
                social_orientation="",
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable"
            )

    # -------------------------------------------------------------------------
    # 4. UNIFIED 3-IN-1 EXECUTION (MULTI-LENS)
    # -------------------------------------------------------------------------
    async def profile_all(self, payload: Dict[str, Any]) -> Tuple[PassionProfile, FrictionProfile, CognitiveStyle]:
        """Tüm 3 hedef analizini tek seferde veya paralel çalıştırır."""
        passions = await self.profile_passions(payload)
        frictions = await self.profile_frictions(payload)
        cognitive = await self.profile_cognitive(payload)
        return passions, frictions, cognitive
