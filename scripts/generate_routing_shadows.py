#!/usr/bin/env python3
"""generate_routing_shadows.py — routing gölgelerini snapshot'tan üretir.

Kaynak: LLMGateway.effective_routing_snapshot() (tek gerçek ağız).
Üretilenler:
  (a) frontend/src/components/UnifiedCompactPanel.svelte — agentList satırlarındaki
      primaryModel/backupModel/via (isim/renk/glyph/capability ELLE KALIR).
  (b) RUNBOOK.md — precedence sözleşmesi + ajan tablosu + tier ihlalleri.

Determinizm sözleşmesi (kilitli: tests/unit/test_routing_shadows.py):
- Override ENV scrub'lanır (OPENROUTER_AGENT_CHAIN_*, *_PATH): üretilen her zaman
  COMMIT'li dosyaları yansıtır, operatör ortamını değil.
- Timestamp YOK, sıralama sabit (sorted), aynı girdi → bayt-bayt aynı çıktı.
- `via` = "openrouter": anahtarsız baz durumda HER modelin varyantı [None]
  (OpenRouter transport) — runtime prob ile kanıtlı. Canlı `run.via` UI'da
  zaten önceliklidir (svelte:473), statik değer yalnızca baz-fallback'tur.
- Bilinmeyen satırlar (örn. resonance_calc) ve snapshot-dışı ajanlar
  byte-identical korunur: script satır EKLEMEZ/SİLMEZ (v1 kuralı).

Kullanım:
  python scripts/generate_routing_shadows.py          # üret (idempotent)
  python scripts/generate_routing_shadows.py --check  # yazmadan tazelik denetle (exit 3 = bayat)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"[UYARI] UTF-8 stdout ayarlanamadı: {type(exc).__name__}", file=sys.stderr)

SVELTE = ROOT / "frontend/src/components/UnifiedCompactPanel.svelte"
RUNBOOK = ROOT / "RUNBOOK.md"

SVELTE_START = "// <ROUTING-GENERATED-START do-not-edit>"
SVELTE_END = "// <ROUTING-GENERATED-END>"
RUNBOOK_START = "<!-- ROUTING-GENERATED-START do-not-edit -->"
RUNBOOK_END = "<!-- ROUTING-GENERATED-END -->"

SCRUB_PREFIXES = ("OPENROUTER_AGENT_CHAIN_",)
SCRUB_VARS = ("PINEAL_TASK_ROUTING_PATH", "PINEAL_AGENT_TIERS_PATH")

LAYER_DOCS = [
    ("env_override", "`OPENROUTER_AGENT_CHAIN_<AJAN>` — açık operasyon/acil override; verildiği an o ajan için her şeyi geçersiz kılar."),
    ("task_routing", "`config/task_routing.json` — config delta (fail-closed; bozuk girdi matrix'e düşer)."),
    ("agent_matrix", "`LLMGateway.AGENT_CHAINS` — varsayılan tablo."),
    ("task_chain", "`CHAINS[task]` — kayıtlı olmayan isimler için görev fallback'i."),
]


def _scrub_env() -> None:
    for key in list(os.environ):
        if key.startswith(SCRUB_PREFIXES):
            del os.environ[key]
    for key in SCRUB_VARS:
        os.environ.pop(key, None)


def _short(model_id: str) -> str:
    return model_id.split("/")[-1]


def _replace_between(text: str, start: str, end: str, new_body: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"marker hatasi: {start[:30]}... x{text.count(start)} / end x{text.count(end)} (beklenen 1/1)")
    pre, _, rest = text.partition(start)
    _, _, post = rest.partition(end)
    return f"{pre}{start}\n{new_body}\n{end}{post}"


def _jury_label() -> tuple[str, str, str]:
    """[BOSS-4] Jüri etiketi KODDAN türetilir — elle yazılmaz.

    Kaynak: `LLMGateway.JURY_PANEL_AGENTS`. Panel büyürse/koltuğu değişirse UI
    etiketi kendiliğinden değişir; test kurguyu değil kodun kendisini kilitler.
    """
    from agent_core.services.llm_gateway import LLMGateway

    seats = [seat.replace("pineal_juror_", "") for seat in LLMGateway.JURY_PANEL_AGENTS]
    return ("pineal-verifier-panel", f"({len(seats)} jüri: {'+'.join(seats)})", "9router")


ROUTER_9_CANONICAL_MAP = {
    "mirror_truth": ("pineal-deep-reasoning", "(combo)", "9router"),
    "autonomous_verifier": _jury_label(),
    "human_behavior": ("pineal-general-reasoning", "(combo)", "9router"),
    "passion_mapper": ("pineal-fast-extract", "(combo)", "9router"),
    "friction_detector": ("pineal-general-reasoning", "(combo)", "9router"),
    "cognitive_profiler": ("pineal-general-reasoning", "(combo)", "9router"),
    "resonance_calc": ("local-numpy", "—", "local"),
    "pattern_interrupt": ("pineal-fast-extract", "(combo)", "9router"),
    "resonance_synthesizer": ("pineal-deep-reasoning", "(combo)", "9router"),
    "vision_analyzer": ("pineal-vision", "(combo)", "9router"),
    "osint_investigator": ("pineal-osint-pipeline", "(pipeline)", "9router"),
    "authenticity_auditor": ("pineal-vision", "(forensic)", "9router"),
    "depth_analyst": ("pineal-deep-reasoning", "(combo)", "9router"),
}


def render_svelte_block(snapshot: dict) -> list[str]:
    """Mevcut satırları koruyarak model alanlarını 9Router kanonik rotalarından yazar."""
    current = SVELTE.read_text(encoding="utf-8")
    if current.count(SVELTE_START) != 1 or current.count(SVELTE_END) != 1:
        raise SystemExit("svelte marker hatasi: START/END 1'er kez olmali")
    body = current.split(SVELTE_START)[1].split(SVELTE_END)[0]
    agents = snapshot["agents"]
    out_lines = []
    for raw_line in body.strip("\n").split("\n"):
        m = re.match(r'^(\s*\{\s*id:\s*"([^"]+)")(.*)\}\s*,?\s*$', raw_line)
        if not m:
            out_lines.append(raw_line)  # boşluk/yorum satırı aynen
            continue
        head, agent_id, middle = m.group(1), m.group(2), m.group(3)
        if agent_id in ROUTER_9_CANONICAL_MAP:
            primary, backup, via = ROUTER_9_CANONICAL_MAP[agent_id]
        elif agent_id in agents:
            chain = agents[agent_id]["chain"]
            primary = _short(chain[0]) if chain else "—"
            backup = _short(chain[1]) if len(chain) > 1 else "—"
            via = "9router"
        else:
            out_lines.append(raw_line)  # snapshot-dışı aynen
            continue
        if 'primaryModel:' not in middle or 'backupModel:' not in middle or 'via:' not in middle:
            raise SystemExit(f"svelte satir sablonu bozulmus: {agent_id} (primaryModel/backupModel/via gerekli)")
        middle = re.sub(r'primaryModel:\s*"[^"]*"', f'primaryModel: "{primary}"', middle)
        middle = re.sub(r'backupModel:\s*"[^"]*"', f'backupModel: "{backup}"', middle)
        middle = re.sub(r'via:\s*"[^"]*"', f'via: "{via}"', middle)
        out_lines.append(f"{head}{middle}}},")
    return out_lines


def render_runbook_block(snapshot: dict) -> str:
    agents = snapshot["agents"]
    tiers = snapshot.get("tiers", {})
    lines = [
        "**BU BÖLÜM OTOMATİK ÜRETİLİR — ELLE DÜZENLEMEYİN.** Kaynak: `LLMGateway.effective_routing_snapshot()` + `scripts/generate_routing_shadows.py`.",
        "",
        "**Sıra sözleşmesi (precedence):**",
        "",
    ]
    for i, (source, doc) in enumerate(LAYER_DOCS, 1):
        lines.append(f"{i}. `{source}` — {doc}")
    lines += [
        "",
        f"**Ajan↔zincir (çözünmüş, {len(agents)} ajan, override'sız baz):**",
        "",
        "| agent | tier | chain | source |",
        "|---|---|---|---|",
    ]
    for agent in sorted(agents):
        tier = tiers.get(agent, {}).get("tier", "?")
        chain = " → ".join(_short(m) for m in agents[agent]["chain"])
        lines.append(f"| {agent} | {tier} | {chain} | {agents[agent]['source']} |")
    lines += ["", "**Tier ihlalleri (bilgilendirme, v1 — CI kırmaz, düzeltme turu bekler):**", ""]
    violations = snapshot.get("tier_violations", [])
    if not violations:
        lines.append("- yok ✅")
    for v in sorted(violations, key=lambda d: (d["rule"], d["agent"])):
        lines.append(f"- ⚠️ `{v['agent']}` [{v['rule']}] {v['detail']}")
    return "\n".join(lines)


def generate(check_only: bool = False) -> bool:
    """Üret (ya da --check ile tazelik denetle). Dönüş: değişim gerekli mi?"""
    _scrub_env()
    from agent_core.services.llm_gateway import LLMGateway

    snapshot = LLMGateway().effective_routing_snapshot()
    svelte_new = _replace_between(
        SVELTE.read_text(encoding="utf-8"), SVELTE_START, SVELTE_END, "\n".join(render_svelte_block(snapshot))
    )
    runbook_new = _replace_between(
        RUNBOOK.read_text(encoding="utf-8"), RUNBOOK_START, RUNBOOK_END, render_runbook_block(snapshot)
    )
    dirty = (svelte_new != SVELTE.read_text(encoding="utf-8")) or (runbook_new != RUNBOOK.read_text(encoding="utf-8"))
    if not check_only and dirty:
        SVELTE.write_text(svelte_new, encoding="utf-8")
        RUNBOOK.write_text(runbook_new, encoding="utf-8")
    return dirty


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    try:
        dirty = generate(check_only=check_only)
    except SystemExit as exc:
        print(f"generate_routing_shadows: {exc}", file=sys.stderr)
        return 2
    if check_only and dirty:
        print("generate_routing_shadows: gölgeler BAYAT — script'i çalıştırıp commit'leyin", file=sys.stderr)
        return 3
    print(f"generate_routing_shadows: {'güncellendi' if dirty and not check_only else 'taze ✅'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
