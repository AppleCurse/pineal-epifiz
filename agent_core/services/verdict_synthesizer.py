"""Deterministik Hüküm Belgesi (verdict digest) — [FIX #4]

Aspasia'nin "sorun ne?" / "bu görevde ne buldun?" soruları, ham telemetri
satırlarıyla değil, KANIT'TAN derlenmiş yapılandırılmış bir özetle
cevaplanmalıdır. Bu modül HERHANGİ BİR LLM ÇAĞRISI YAPMAZ:

- room_state['active_tasks'] içindeki EN SON snapshot'ın
  evidence_chain + agent_runs'ını okur;
- her madde: ajan + kanıt tipi + bulgu çekirdeği (<=280 karakter);
- toplam bütçe: 2000 karakter (deterministik tavan);
- kanıt yoksa dürüst "(kanıt kaydı yok)" satırı — uydurma HÜKÜM ÜRETİLMEZ.

Çıktı Aspasia persona'sına "HÜKÜM BELGESİ" bloğu olarak verilir; persona
onu doğal dile çevirir, tıbbi/hukuki yoruma dönüştürmesi prompt'ta yasaklıdır.
"""
from __future__ import annotations

from typing import Any, List

_CLAIM_LIMIT = 280
_TOTAL_BUDGET = 2000
_MAX_LINES = 12


def _core(result: Any) -> str:
    """Kanıt nesnesinden deterministik metin çekirdeği (uydurma özet yok)."""
    if not isinstance(result, dict):
        return ""
    parts = [
        str(v).strip()
        for v in result.values()
        if isinstance(v, str) and len(str(v).strip()) >= 12
    ]
    return (" | ".join(parts))[:_CLAIM_LIMIT]


def _blocked_channels(snap: Any) -> List[dict[str, Any]]:
    """Snapshot'taki koşmayan/başarısız kanalları döndürür (deterministik)."""
    rows = getattr(snap, "channel_status", None)
    if not isinstance(rows, list):
        return []
    out: List[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status in ("not_run", "failed"):
            out.append(row)
    return out


def build_verdict_digest(room_state: Any) -> str:
    """Oda durumundan son görevin hüküm belgesini derler (deterministik)."""
    if not isinstance(room_state, dict):
        return ""
    active = room_state.get("active_tasks")
    if not isinstance(active, dict) or not active:
        return ""
    # Son güncellenen görev: snapshot'lar broadcast'le dict'e yazılır;
    # insert-order'da en sonda en taze kayıt vardır.
    task_id, snap = next(reversed(list(active.items())))
    status = getattr(snap, "status", None)
    status_value = getattr(status, "value", status)

    lines: List[str] = []
    evidence = getattr(snap, "evidence_chain", None) or []
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        agent = str(entry.get("agent", "?"))[:40]
        etype = str(entry.get("evidence_type", "agent_output"))[:24]
        core = _core(entry.get("result"))
        line = f"- [{agent}/{etype}]"
        if core:
            line += ": " + core
        lines.append(line)
        if len(lines) >= _MAX_LINES:
            break

    header = f"GÖREV {task_id} — DURUM: {status_value}"
    body = "\n".join(lines) if lines else "- (kanıt kaydı yok — hiçbir ajan kanıt üretmedi)"

    # [P0 · DENETİM 2026-10-16] Hüküm belgesi KOŞMAYAN kanalları da listeler.
    # Aksi hâlde "kanıt yok" ile "kanal hiç çalışmadı" ayrımı belgede kaybolur
    # ve hüküm, eksik veriyi varmış gibi okunur.
    blocked = _blocked_channels(snap)
    if blocked:
        body += "\nKOŞMAYAN KANALLAR:"
        for row in blocked:
            body += (
                f"\n- [{row.get('channel', '?')}] {row.get('status', 'not_run')}"
                f" · {row.get('reason') or 'sebep yok'}"
            )

    digest = header + "\n" + body
    return digest[:_TOTAL_BUDGET]
