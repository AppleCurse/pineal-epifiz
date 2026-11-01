"""Koşu kaydı (AgentRun) serileştirici — tek SoT.

[API-BÖLME 5 · 2026-10-18] `backend/api.py` tek-modül tavanı
(`tests/unit/test_api_monolith_ratchet.py`; kural: satır eklemek yerine MODÜL
ÇIKAR — `docs/reports/API_MONOLITH_SPLIT_PLAN.md` §4) gereği bu iki saf
dönüştürücü ayrı modüle taşındı. Dış sözleşme BOZULMADI: `backend.api` içinden
`_run_display_fields` / `_serialize_run_entry` adlarıyla **yeniden ihraç**
edilir (`tests/unit/test_run_display_contract.py` bu adresleri kullanıyor).

Bağımlılık yalnız `agent_core.utils.security.redact_structure` (gizli kalabalık
temizliği) — uygulama durumuna (`app.state`) dokunulmaz; iki broadcast noktası
(WS snapshot + görev sonucu) aynı fonksiyonu çağırmaya devam eder → **tek SoT**.

[P6 · CANLI PANEL] Serileştirilen alanlar: `input_summary` (girdi özeti:
hangi ajan nereyi kazıyor), `evidence_ids` (toplanan bilgi), `responsibility`
(muhakeme: attempted/blockers/next_action), `decision_grade` (karar var mı),
`warnings`, `error_code`, `call_ids` (çağrı kimlikleri) + `output_summary`/
`provenance` ve canlı model/sağlayıcı türetimi.
"""

from __future__ import annotations

from typing import Any

from agent_core.utils.security import redact_structure

__all__ = ["run_display_fields", "serialize_run_entry"]


def run_display_fields(run: Any) -> dict:
    """(Şeffaflık düzeltmesi, F2) AgentRun'dan CANLI model/provider gösterimi türetir.

    Backend ``AgentRun`` şeması ``model``/``via`` ÜRETMEZ; bir ajanın gerçekten
    çağırdığı model/provider, o ajanın ``output_summary._provenance`` kaydında
    yaşar (kaynak: yakalanan çağrı kayıtlarının son başarılısı). UI "ACTIVE
    MODEL/VIA" çubuğu bu alanlardan beslenir; provenance yoksa/fallback/
    deterministik ise değerler açıkça söyler — statik fallback'e sessiz düşme
    yerine (üretici yorumuyla birebir).
    """
    prov = (getattr(run, "output_summary", None) or {}).get("_provenance") or {}
    source = prov.get("source")
    model = prov.get("model")
    provider = prov.get("provider")
    if source in ("llm", "llm_cache"):
        return {"model": model, "via": provider or "openrouter", "run_source": source}
    if source == "llm_error":
        return {
            "model": model,
            "via": (provider or "llm") + " (hata)",
            "run_source": source,
        }
    if source == "deterministic":
        return {"model": None, "via": "deterministik-motor", "run_source": source}
    if source == "fallback":
        reason = prov.get("fallback_reason")
        suffix = f":{reason}" if reason else ""
        return {"model": None, "via": "fallback" + suffix, "run_source": source}
    return {"model": None, "via": None, "run_source": source or None}


def serialize_run_entry(run: Any, *, with_timestamps: bool) -> dict:
    """AgentRun serileştirmesi — tek SoT (iki broadcast noktası da bunu çağırır).

    [P6 · CANLI PANEL] Eksik alanlar eklendi. Önceden ``input_summary``
    (War Room'un INPUT sekmesi okuyordu ama backend HİÇ göndermiyordu →
    ekran hep yedek metni gösteriyordu = "çalışır gibi yapan" UI),
    ``evidence_ids`` (toplanan bilgi), ``responsibility`` (muhakeme:
    attempted/blockers/next_action) ve ``decision_grade`` (karar var mı)
    serileştirilmiyordu. Hepsi aynı SoT'tan (``AgentRun``) türetilir.
    """
    entry = {
        "status": getattr(run, "status", None),
        "confidence": getattr(run, "confidence", None),
        "error_message": getattr(run, "error_message", None),
        "error_code": getattr(run, "error_code", None),
        "call_ids": list(getattr(run, "call_ids", []) or []),
        # Girdi özeti: ajan NEYİ işliyor (URL listesi + sayılar). Profil
        # İÇERİĞİ (bio/gönderi metni) burada taşınmaz.
        "input_summary": redact_structure(
            getattr(run, "input_summary", None) or {}
        ),
        "evidence_ids": list(getattr(run, "evidence_ids", []) or []),
        "decision_grade": bool(getattr(run, "decision_grade", True)),
        "responsibility": redact_structure(
            getattr(run, "responsibility", None) or {}
        ),
        "warnings": list(getattr(run, "warnings", []) or []),
        "output_summary": redact_structure(
            getattr(run, "output_summary", None) or {}
        ),
        "provenance": redact_structure(
            (getattr(run, "output_summary", None) or {}).get("_provenance")
        ),
    }
    if with_timestamps:
        entry["started_at"] = (
            run.started_at.isoformat() if getattr(run, "started_at", None) else None
        )
        entry["completed_at"] = (
            run.completed_at.isoformat() if getattr(run, "completed_at", None) else None
        )
    entry.update(run_display_fields(run))
    return entry
