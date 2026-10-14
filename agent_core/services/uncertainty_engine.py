"""Belirsizlik motoru — veri kalitesini ayrıştırarak puanlar.

``evaluate(result, agent_name)`` her ajan çıktısı için alan alan veri skoru
üretir (``UncertaintyReport``). Placeholder/boş metin kanıt SAYILMAZ
(``_is_non_evidence_text``); ``None``/yer tutucu değerler skora katkı vermez
(``_value_bears_evidence``).

Amaç: "ajan koştu" ile "ajan kanıt üretti" arasındaki farkı ölçülebilir kılmak.
Eşikler ``config/decision_config.yaml``'dan gelir.

Tüketici: ``task_executor`` + ``decision_engine``.
Test: ``tests/unit/test_executor_confidence_semantics.py``.
"""

import json
import logging
from typing import Any, Dict, Tuple
from pydantic import BaseModel, ConfigDict

from agent_core.config_loader import DecisionConfig


class UncertaintyReport(BaseModel):
    is_suspicious: bool
    confidence: float
    reason: str
    data_score: float = 0.0
    breakdown: Dict[str, Any] = {}
    #: [RÖNTGEN 2026-09-23] GÖREV TAMAMLANDI ≠ KARAR ÜRETİLDİ.
    #: True ise ajan koştu ve çıktı verdi ama bu çıktı KARAR DEĞİL: ajanın
    #: kendi sözleşmesi `data_confidence=False` diyor. Executor böyle bir
    #: koşuyu `completed_no_decision` olarak kaydeder — ne "halted" (ajan
    #: gerçekten çalıştı) ne de karar-Grade "completed". Güven UYDURULMAZ
    #: (eski resonance_calc 0.75 tabanı).
    no_decision: bool = False
    model_config = ConfigDict(extra="forbid")

class UncertaintyEngine:
    HALUCINATION_MARKERS = [
        'kesinlikle', 'mutlaka', 'her zaman', 'asla',
        'kesin olarak', 'şüphesiz'
    ]

    # ------------------------------------------------------------------ #
    # Kanıt kalitesi sözleşmesi ([017]/[018] fix):
    # "Alan dolu" ≠ "kanıt var". Aşağıdaki ibareler bilgi taşımaz; veri
    # kalitesi hesabında 0.0 sayılır. Kural ANLAM bazlıdır, UZUNLUK bazlı
    # DEĞİLDİR: karakter sayısı confidence üretmez.
    # ------------------------------------------------------------------ #
    NON_EVIDENCE_PHRASES = (
        'bulunamadı', 'bulunamadi', 'veri yok', 'bilgi yok', 'kayıt yok',
        'kayit yok', 'sonuç yok', 'sonuc yok', 'veri bulunamadı',
        'veri bulunamadi', 'bilinmiyor', 'belirsiz', 'tanımlı değil',
        'tanimli degil', 'yetersiz veri', 'veri yetersiz', 'yetersiz gönderi',
        'sentez yapılamadı', '< min', 'not found',
        'no data', 'no results', 'no info', 'no evidence', 'unknown',
    )
    NON_EVIDENCE_EXACT = frozenset({
        '', '-', '—', '–', '…', '...', '?', 'n/a', 'na', 'yok', 'yok.',
        'bilinmiyor', 'belirsiz', 'unknown', 'tanımlı değil', 'tanimli degil',
    })
    # Çalışma zamanı metadata'sı: varlığı KANIT DEĞİLDİR (oranı şişiremez,
    # boş veriyi kurtaramaz). Adları yalnızca bu seti kapsar; status/reason
    # gibi sonuç-anlamlı alanlar hariç tutulur.
    RUNTIME_METADATA_FIELDS = frozenset({
        'confidence', 'data_confidence', 'fallback_reason',
        'model', 'model_name', 'provider', 'source_provider',
        'usage', 'tokens', 'token_usage', 'metrics',
        'duration_ms', 'elapsed_ms', 'latency_ms', 'elapsed',
        'agent', 'agent_name', 'request_id', 'task_id', 'trace_id',
        'created_at', 'timestamp', 'ts', 'version',
    })

    @classmethod
    def _is_non_evidence_text(cls, value: Any) -> bool:
        """Bir metin gerçekten bilgi taşıyor mu? (placeholder/boş -> True)"""
        if not isinstance(value, str):
            return False
        text = value.strip().lower()
        if not text:
            return True
        if text in cls.NON_EVIDENCE_EXACT:
            return True
        return any(phrase in text for phrase in cls.NON_EVIDENCE_PHRASES)

    @classmethod
    def _value_bears_evidence(cls, value: Any) -> bool:
        """Değer kanıt kalitesine katkı sağlıyor mu? (None/placeholder -> False)"""
        if value is None:
            return False
        if isinstance(value, str):
            return not cls._is_non_evidence_text(value)
        if isinstance(value, (list, tuple)):
            return any(cls._value_bears_evidence(item) for item in value)
        if isinstance(value, dict):
            return any(cls._value_bears_evidence(v) for v in value.values())
        if isinstance(value, BaseModel):
            return any(cls._value_bears_evidence(v) for v in value.model_dump().values())
        # sayı/bool/vb. tipli değerler: kanıt olarak sayılır (0.0 gibi
        # anlamlı ölçümler silinmez).
        return True

    def __init__(self):
        self.config = DecisionConfig.load()
        self.logger = logging.getLogger(__name__)

    def calculate_data_score(
        self, 
        output_dict: Dict[str, Any], 
        agent_name: str
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate data quality score with detailed breakdown based on config.
        """
        agent_config = self.config.get_agent_config(agent_name)
        field_weights = agent_config.field_weights
        empty_list_penalty = agent_config.empty_list_penalty
        
        breakdown = {}
        total_score = 0.0
        total_weight = 0.0
        
        # If no specific field weights are defined, just use a simple ratio
        if not field_weights:
            # Yalnızca KANIT alanları sayılır; metadata alanları (model,
            # provider, süre, token vb.) veri kalitesi oranını ŞİŞİREMEZ.
            data_fields = [
                (k, v) for k, v in output_dict.items()
                if k not in self.RUNTIME_METADATA_FIELDS
            ]
            total_fields = len(data_fields)
            if total_fields == 0:
                return 0.0, {"reason": "No data fields"}

            evidence_fields = sum(1 for _, v in data_fields if self._value_bears_evidence(v))
            data_score = evidence_fields / total_fields
            return data_score, {
                "simple_ratio": data_score,
                "evidence_bearing_fields": evidence_fields,
                "total_candidate_fields": total_fields,
                "metadata_excluded": [
                    k for k in output_dict if k in self.RUNTIME_METADATA_FIELDS
                ],
            }

        for field, weight in field_weights.items():
            if field not in output_dict:
                breakdown[field] = {"present": False, "score": 0.0, "weight": weight, "evidence_bearing": False}
                total_weight += weight
                continue
            
            value = output_dict[field]
            field_score = self._score_field_value(value, empty_list_penalty)
            evidence_bearing = self._value_bears_evidence(value)
            
            breakdown[field] = {
                "present": True,
                "score": field_score,
                "weight": weight,
                "weighted_score": field_score * weight,
                "evidence_bearing": evidence_bearing,
            }
            
            total_score += field_score * weight
            total_weight += weight
        
        final_score = total_score / total_weight if total_weight > 0 else 0.0
        
        self.logger.info(
            f"Data score for {agent_name}: {final_score:.2f}\n"
            f"Breakdown: {json.dumps(breakdown, indent=2)}"
        )
        
        return final_score, breakdown

    def _score_field_value(self, value: Any, empty_list_penalty: float) -> float:
        """Score individual field value (0.0 to 1.0).

        P1-B2 SÖZLEŞMESİ:
        - Güven, içerik UZUNLUĞUNDAN üretilmez (karakter sayısı confidence'ı artırmaz).
        - Kanıt KALİTESİ ayrı değerlendirilir: "alan dolu" tek başına 1.0 DEĞİLDİR.
          Boolean placeholder ibareler ("bulunamadı", "veri yok", "bilinmiyor",
          "n/a", "unknown"...) ve yalnızca bu ibarelerden oluşan liste/dict
          0.0 sayılır; karışık listeler kanıt oranına göre puanlanır.
        - Tüm elemanları kanıt taşıyan dolu liste -> sabit katkı (1.0).
        - Boş -> ceza (empty_list_penalty / 0.0).
        - Başka sihirli uzunluk eşiği YOKTUR.
        """
        if value is None:
            return 0.0
        
        if isinstance(value, (list, tuple)):
            if len(value) == 0:
                # Boş liste cezası
                return empty_list_penalty
            evidence_count = sum(
                1 for item in value if self._value_bears_evidence(item)
            )
            if evidence_count == 0:
                # Dolu görünen ama tamamı placeholder -> sıfır kanıt
                return 0.0
            # Gerçek kanıt oranı; eleman UZUNLUĞU veya sayısı skoru YÜKSELTMEZ.
            return evidence_count / len(value)
        
        if isinstance(value, dict):
            if len(value) == 0:
                return empty_list_penalty
            evidence_count = sum(
                1 for v in value.values() if self._value_bears_evidence(v)
            )
            if evidence_count == 0:
                return 0.0
            return 0.8 * (evidence_count / len(value))
        
        if isinstance(value, str):
            if self._is_non_evidence_text(value):
                return 0.0
            # Dolu ve şema-geçerli string -> sabit katkı; uzunluk fark yaratmaz.
            return 1.0
        
        if isinstance(value, (int, float, bool)):
            return 0.8  # Primitives are moderate confidence
        
        return 0.5  # Default for other types

    def evaluate(self, result: Any, agent_name: str) -> UncertaintyReport:
        result_text = str(result)
        has_absolutes = any(marker in result_text.lower() for marker in self.HALUCINATION_MARKERS)
        llm_confidence = getattr(result, 'confidence', None)
        data_conf_flag = getattr(result, 'data_confidence', True)
        
        agent_config = self.config.get_agent_config(agent_name)
        
        data_score = 0.0
        breakdown = {}
        is_empty = False

        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
            data_score, breakdown = self.calculate_data_score(result_dict, agent_name)
            
            # is_empty artık KANIT KALİTESİNE bakar: placeholder ibarelerden
            # oluşan dolu alanlar kanıt sayılmaz (metadata alanları da sayılmaz).
            data_fields = [
                (k, v) for k, v in result_dict.items()
                if k not in self.RUNTIME_METADATA_FIELDS
            ]
            if data_fields and not any(
                self._value_bears_evidence(v) for _, v in data_fields
            ):
                is_empty = True
        elif 'evidence' in result_text and 'bulunamadı' in result_text:
            is_empty = True

        # Calculate combined confidence
        if llm_confidence is None:
            combined_confidence = data_score
        else:
            # Weighted approach or taking the minimum if data score is too low
            if data_score >= agent_config.min_data_score:
                # LLM confidence is acceptable
                combined_confidence = min(llm_confidence, data_score)
            else:
                combined_confidence = data_score

        # Check conditions
        if not data_conf_flag:
            if agent_name == "resonance_calc":
                # [RÖNTGEN 2026-09-23] UYDURMA 0.75 TABANI KALDIRILDI.
                # Eski kod `conf = max(0.75, comp_score)` dönüyordu: ajanın
                # KENDİ sözleşmesi "data_confidence=False => çıktı KARAR
                # DEĞİLDİR (fail-closed)" derken (resonance_calculator.py:111)
                # burada ÖLÇÜLMEYEN bir güven üretiliyor ve executor'ın
                # LOW_CONFIDENCE kapısı atlatılıyordu.
                # Tabanı kaldırmanın naif bedeli de vardı: güven 0.0 olunca
                # koşu "halted" yazılıyor ve çıktısı status'a İŞLENMİYORDU,
                # yani `state=inference_gap` bilgisi kayboluyordu.
                # Çözüm = üçüncü durum: `no_decision=True`. Executor koşuyu
                # `completed_no_decision` olarak KAYBEDER (çıktı ve state
                # raporda kalır) ama karar-Grade saymaz. DecisionEngine zaten
                # `data_confidence=False` taşıyan kaydı kanıt kabul etmiyor
                # (`_run_bears_evidence`) ve görevi PARTIALLY_COMPLETED'a
                # düşürüyor — "görev tamamlandı ≠ karar üretildi" uçtan uca
                # tutarlı. Kilit: tests/unit/test_no_decision_run_status.py
                _raw_score = getattr(result, 'compatibility_score', None)
                if _raw_score is None and isinstance(result, dict):
                    _raw_score = result.get('compatibility_score')
                comp_score = float(_raw_score or 0.0)
                _raw_state = getattr(result, 'state', None)
                if _raw_state is None and isinstance(result, dict):
                    _raw_state = result.get('state')
                state_label = _raw_state or 'inference_gap' 
                return UncertaintyReport(
                    is_suspicious=False,
                    confidence=comp_score,
                    no_decision=True,
                    reason=(
                        "Rezonans çıktısı KARAR DEĞİL (data_confidence=False, "
                        f"state={state_label}); "
                        f"ölçülen benzerlik {comp_score:.2f}, güven uydurulmadı."
                    ),
                    data_score=data_score,
                    breakdown=breakdown
                )
            # An unavailable/fallback source is never safe evidence.
            return UncertaintyReport(
                is_suspicious=True,
                confidence=0.0,
                reason="Kaynak verisi kullanılamıyor; fallback sonuç kabul edilmedi.",
                data_score=data_score,
                breakdown=breakdown
            )

        if is_empty:
            return UncertaintyReport(
                is_suspicious=True, 
                confidence=0.1, 
                reason="Eksik kanıt (Tüm alanlar boş veya veri yetersiz).",
                data_score=data_score,
                breakdown=breakdown
            )

        if combined_confidence > 0.95 and has_absolutes:
            return UncertaintyReport(
                is_suspicious=True, 
                confidence=0.9, 
                reason="Aşırı kesinlik + yüksek confidence = Halüsinasyon şüphesi",
                data_score=data_score,
                breakdown=breakdown
            )

        if combined_confidence < agent_config.min_llm_confidence:
            return UncertaintyReport(
                is_suspicious=True,
                confidence=combined_confidence,
                reason=f"Düşük güven ({combined_confidence:.2f} < {agent_config.min_llm_confidence}).",
                data_score=data_score,
                breakdown=breakdown
            )

        return UncertaintyReport(
            is_suspicious=False, 
            confidence=combined_confidence, 
            reason="Güvenli",
            data_score=data_score,
            breakdown=breakdown
        )
