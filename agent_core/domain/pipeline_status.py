"""Boru hattı durum kümesi — görev yaşam döngüsünün SÖZLÜĞÜ.

Her değer istemciye/arayüze giden tek gerçek kaynaktır; "başarısız" ile
"bütçe doldu (TIMED_OUT)" ve "kanıt yetersiz (HALTED_INSUFFICIENT_EVIDENCE)"
AYRI durumlardır — aynı darboğazı ikinci kez denemek faturayı katlar
([BOSS-8]).

Durum adları API sözleşmesi sayılır: değiştirmek istemciyi kırar.
"""

from enum import Enum

class PipelineStatus(str, Enum):
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    HALTED_INSUFFICIENT_EVIDENCE = "halted_evidence"
    HALTED_CRITICAL = "halted_critical"
    HALTED_FREQUENCY = "halted_frequency"
    # [BOSS-8] Görev bütçesi doldu: "başarısız"dan AYRI durum. Aynı darboğaz
    # ikinci turda da aynı yerde tıkanır ama LLM faturası katlanır.
    TIMED_OUT = "timed_out"
    FAILED = "failed"
