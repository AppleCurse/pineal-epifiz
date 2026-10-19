"""OSINT adaptörleri için birleşik ve güvenli parser/normalizer.

Maigret, Holehe, Socid_extractor ve benzeri OSINT kütüphanelerinin sürümler
arasındaki dict / pydantic / obje / tuple uyuşmazlıklarını tek bir merkezde
güvenle karşılar. Asla AttributeError veya TypeError ile patlamaz.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


def safe_osint_get(record: Any, key: str, default: Any = None) -> Any:
    """Bir OSINT kaydından (dict, pydantic, dataclass veya rastgele obje) güvenle alan okur."""
    if record is None:
        return default
    if isinstance(record, Mapping):
        return record.get(key, default)
    # Pydantic v2 / v1
    if hasattr(record, "model_dump"):
        try:
            return record.model_dump().get(key, default)
        except Exception:
            pass
    if hasattr(record, "dict") and callable(record.dict):
        try:
            return record.dict().get(key, default)
        except Exception:
            pass
    # Standart Python objesi
    return getattr(record, key, default)


def osint_to_dict(record: Any) -> dict[str, Any]:
    """Herhangi bir OSINT kaydını güvenli bir sözlüğe dönüştürür."""
    if record is None:
        return {}
    if isinstance(record, dict):
        return record
    if isinstance(record, Mapping):
        return dict(record)
    if hasattr(record, "model_dump") and callable(record.model_dump):
        try:
            return dict(record.model_dump())
        except Exception:
            pass
    if hasattr(record, "dict") and callable(record.dict):
        try:
            return dict(record.dict())
        except Exception:
            pass
    if hasattr(record, "__dict__"):
        return {k: v for k, v in record.__dict__.items() if not k.startswith("_")}
    return {}
