#!/usr/bin/env python3
"""export_skills.py — yetenek defterinden Agent Skills paketi üretir.

Kaynak: ``CapabilityRegistry`` (tek gerçek ağız). Her yetenek için
``skills/<araç_adı>/SKILL.md`` üretilir; dosya, MCP üzerinden NASIL
çağrılacağını ve çağrının dürüstlük sözleşmesini anlatır.

Dürüstlük sözleşmesi (üretici için):
    * Uydurma yok: açıklama yeteneğin kendi ``description`` alanıdır, kapılar
      kendi ``gates`` kümesidir, şema ``mcp.tools`` ile AYNI fonksiyondan gelir.
    * Determinizm: zaman damgası YOK, sıralama kimliğe göre sabit; aynı girdi →
      bayt-bayt aynı çıktı (test: ``tests/unit/test_export_skills.py``).
    * Bayat paket sessiz kalamaz: ``--check`` üretilenle diskteki ayrışırsa
      exit 3 verir (CI bu adımı koşar).

Kullanım:
    python scripts/export_skills.py            # üret (idempotent)
    python scripts/export_skills.py --check    # yazmadan tazelik denetle
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - akış yönlendirilmişse
        logger.warning(
            "[<modül>] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
        )

from agent_core.capabilities import bootstrap  # noqa: E402
from agent_core.mcp import tools as mcp_tools  # noqa: E402

DEFAULT_OUT = ROOT / "skills"


def _skill_markdown(cap, tool: dict) -> str:
    """Tek yeteneğin SKILL.md gövdesi (tamamı defterden türetilir)."""
    description = (tool["description"] or "").split("\n\n")[0].strip()
    gates = sorted(getattr(cap, "gates", frozenset()))
    gates_text = ", ".join(gates) if gates else "yok (kapısız yetenek yoktur; boşsa hata)"
    schema = json.dumps(tool["inputSchema"], ensure_ascii=False, indent=2, sort_keys=True)
    call_example = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool["name"],
                "arguments": {"subject": "<hedef>"},
                "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"# {tool['name']}\n\n"
        f"{description}\n\n"
        f"- **Yetenek kimliği:** `{cap.id}`\n"
        f"- **Tür:** `{getattr(cap, 'kind').value}`\n"
        f"- **Lisans:** {getattr(cap, 'license', 'unknown')}\n"
        f"- **Kapılar:** {gates_text}\n\n"
        "## Girdi şeması\n\n"
        f"```json\n{schema}\n```\n\n"
        "## MCP ile çağrı\n\n"
        f"```json\n{call_example}\n```\n\n"
        "## Dürüstlük sözleşmesi\n\n"
        "- Kapılar kapalıysa (kasa kilitli, `ENABLE_*` kapalı, hız sınırı dolu) "
        "yetenek **koşmaz**; çağrı `isError: true` ve makine-okunur sebeple döner.\n"
        "- Kanıt üretilmediyse sonuç başarı sayılmaz: `structuredContent.ok` yalnız "
        "kanıt varsa `true` olur.\n"
        "- Bu dosya `scripts/export_skills.py` tarafından defterden üretilir; "
        "elle düzenlenmez (bayat paket CI'da yakalanır).\n"
    )


def build_skill_files(registry=None) -> dict[str, str]:
    """{göreli yol: içerik} — defterden türetilmiş TAM paket."""
    registry = registry if registry is not None else bootstrap()
    index = mcp_tools.build_tool_index(registry)
    tools = {tool["name"]: tool for tool in mcp_tools.build_tools(registry)}
    files: dict[str, str] = {}
    for tool_name in sorted(tools):
        cap = registry.get(index[tool_name])
        front_matter = (
            "---\n"
            f"name: {tool_name}\n"
            f"description: {(tools[tool_name]['description'] or '').splitlines()[0][:200]}\n"
            "---\n\n"
        )
        content = front_matter + _skill_markdown(cap, tools[tool_name])
        files[f"{tool_name}/SKILL.md"] = content
    return files


def write_skills(out_dir: Path) -> list[str]:
    """Paketi diske yazar; yazılan göreli yolları döndürür (tazelenen dosyalar)."""
    files = build_skill_files()
    changed: list[str] = []
    for rel_path, content in sorted(files.items()):
        target = out_dir / rel_path
        previous = target.read_text(encoding="utf-8") if target.exists() else None
        if previous != content:
            changed.append(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return changed


def find_stale(out_dir: Path) -> list[str]:
    """Diskteki paketle üretilen paket ayrışan dosyaları döndürür."""
    files = build_skill_files()
    stale: list[str] = []
    for rel_path, content in sorted(files.items()):
        target = out_dir / rel_path
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            stale.append(rel_path)
    for existing in sorted(out_dir.rglob("SKILL.md")):
        rel = existing.relative_to(out_dir).as_posix()
        if rel not in files:
            stale.append(rel)  # defterde olmayan yeteneğin dosyası: silinmeli
    return stale


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    out_dir = Path(args[0]) if args else DEFAULT_OUT
    check = "--check" in argv

    if check:
        stale = find_stale(out_dir)
        if stale:
            print(f"BAYAT: {len(stale)} dosya defterle uyuşmuyor:")
            for rel in stale:
                print(f"  - {rel}")
            print("Çözüm: python scripts/export_skills.py")
            return 3
        print(f"Skills paketi taze: {len(build_skill_files())} dosya")
        return 0

    changed = write_skills(out_dir)
    total = len(build_skill_files())
    print(f"Skills paketi yazıldı: {total} dosya ({len(changed)} güncellendi) → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
