"""Kanıt taşıyan çıkarımların güven filtresi. LLM'e sorulmaz, SAYILIR."""

from typing import Any, Dict
from agent_core.services.uncertainty_engine import UncertaintyEngine
from agent_core.services.confidence import normalize_confidence

#: measured   → doğrudan gönderi/biyografi metni, birebir alıntı var
#: derived    → en az 2 ölçülmüş kanaldan türetildi
#: assumed    → yalnız LLM yorumu, alıntı yok
#: absent     → girdi yok
VERIFICATION = ("measured", "derived", "assumed", "absent")

CHANNEL_WEIGHT = {
    "posts": 1.0,
    "bio": 0.8,
    "visual": 0.9,
    "osint": 0.5,
    "search": 0.4,
}


def _bears_evidence(val: Any) -> bool:
    return UncertaintyEngine._value_bears_evidence(val)


def build_epistemic_state(
    payload: Dict[str, Any],
    *,
    profiles: Dict[str, Any],
    has_verified_proof: bool = False,
) -> Dict[str, Any]:
    """Hedef verisi kanallarından ve profil alanlarından epistemik doğrulama durumu üretir.
    
    LLM'e güven sorulmaz; kanıt kanalları ve alıntı varlığı deterministik olarak SAYILIR.
    Girdi varlığı (input_data_present) tek başına veri güvenilirliği (data_confidence) DEĞİLDİR.
    data_confidence ancak bağımsız kanıt doğrulaması (has_verified_proof=True)
    veya alıntıyla ölçülmüş alanlar (measured_count > 0 ve kanıt kanalları mevcut) var olduğunda True olur.
    """
    channels = {k: _bears_evidence((payload or {}).get(k)) for k in CHANNEL_WEIGHT}
    present = any(channels.values())
    ceiling = max((CHANNEL_WEIGHT[k] for k, v in channels.items() if v), default=0.0)

    statuses: Dict[str, str] = {}
    for field, values in (profiles or {}).items():
        if not values or not _bears_evidence(values):
            statuses[field] = "absent"
        elif isinstance(values, list):
            if any(_bears_evidence(q) for q in values):
                statuses[field] = "measured"
            else:
                statuses[field] = "absent"
        elif isinstance(values, dict):
            if any(_bears_evidence(v) for v in values.values()):
                statuses[field] = "measured"
            else:
                statuses[field] = "absent"
        elif isinstance(values, str) and _bears_evidence(values):
            statuses[field] = "measured"
        else:
            statuses[field] = "assumed"

    measured_count = sum(1 for s in statuses.values() if s == "measured")
    
    # Girdi varlığı doğruluk iddiası değildir:
    # data_confidence = Yalnızca girdi mevcutsa VE bağımsız doğrulanmış kanıt (has_verified_proof=True) varsa True.
    data_confidence = bool(present and ceiling > 0.0 and has_verified_proof)

    return {
        "input_data_present": present,
        "data_confidence": data_confidence,
        "confidence_ceiling": round(ceiling, 2),
        "evidence_verification_status": statuses,
        "channels_used": [k for k, v in channels.items() if v],
        "measured_count": measured_count,
    }


def clamp(model_conf: Any, state: Dict[str, Any]) -> float:
    """Model güveni tavanı AŞAMAZ; sadece kanıt tavanına kadar indirebilir.
    
    Kural:
    - normalize_confidence ile doğrula: geçersiz ise (NaN, None, <0, >1, bool, non-finite) daima 0.0 döner.
    - Girdi yoksa (input_data_present=False) -> 0.0
    - Tavan <= 0 ise -> 0.0
    - Kelepçe modeli asla yukarı çekemez (tavan 0.9, model 0.3 ise 0.3 kalır).
    - Tavanı aşarsa tavan değerine kırpılır (tavan 0.4, model 0.95 ise 0.4 olur).
    """
    if not state or not state.get("input_data_present"):
        return 0.0
    ceiling = state.get("confidence_ceiling", 0.0)
    if ceiling <= 0.0:
        return 0.0

    score, valid = normalize_confidence(model_conf)
    if not valid:
        return 0.0

    return round(min(score, float(ceiling)), 2)
