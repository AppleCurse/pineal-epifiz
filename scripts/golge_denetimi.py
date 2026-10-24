#!/usr/bin/env python3
"""GÖLGE DENETİMİ — "hiçbir şey gölgede kalmasın" envanteri (tekrar çalıştırılabilir).

Bu betik, ürünün TAMAMI için tek soruyu ölçer: **bir şey var mı, ve varsa
kullanıcı ona hangi yoldan ulaşır?** Ölçüm tamamen statiktir (AST + dosya
okuma + yetenek defteri); hiçbir sayı elle yazılmaz, hiçbir yetenek
"muhtemelen bağlıdır" diye varsayılmaz.

Ölçülen boyutlar:

  1. ``yetenekler``   — defterdeki her yetenek + kapıları + gerçek durumu.
  2. ``zincir``       — yetenek → API ucu → MCP aracı → SKILL.md → arayüz.
                        Zincirin neresi kopuk, satır satır.
  3. ``ajanlar``      — diskteki ajan modülü → yürütücüye kayıt → rota →
                        Agent Rack slotu → arayüzde görünürlük.
  4. ``uclar``        — backend'deki her HTTP ucu + kapısı + arayüz referansı.
  5. ``kapilar``      — yönetilen env kapıları ↔ kodda okunan ↔ .env.example.
  6. ``erisim``       — giriş noktalarından AST ile ulaşılamayan modüller
                        (ölü kod / CLI-only araç / yanlışlıkla kopmuş hat).
  7. ``gomulu``       — depoda duran ama ürüne bağlanmayan varlıklar
                        (rust_core, android, worker.ts, functions/, release/...).
  8. ``cli_tools``    — PATH'teki CLI araçları (ffmpeg, theHarvester, piper,
                        ...) ve Python paketi olarak import edilebilirlik.
                        Denetim makinesine özeldir; Windows'ta farklı sonuç
                        çıkabilir.

Kullanım::

    python scripts/golge_denetimi.py [--json reports/golge_denetimi.json]
                                     [--md docs/reports/GOLGE_DENETIMI.md]

Çıktı deterministiktir (sıralı); aynı depo aynı raporu üretir.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

#: ``.env`` dosyası ``backend/api.py``'de yüklensin; bu denetim betiği de aynı
#: ortamı görsün ki ``ENABLE_*`` şalterleri gerçekten etkili olsun.
from dotenv import load_dotenv  # type: ignore

load_dotenv()

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    ".ruff_cache", "dist", "build", "target", ".mypy_cache", ".next",
}
ENTRYPOINTS = (
    "backend/api.py",
    "main.py",
    "run_lilith.py",
    "scraper.py",
    "live_llm_gate.py",
    "agent_core/mcp/server.py",
    "agent_core/mcp/__main__.py",
    #: CLI araçları: kimse IMPORT etmez, operatör `python -m ...` ile koşar.
    #: Bu liste BEYANDIR — yeni bir CLI eklenirse buraya da yazılmalıdır,
    #: yoksa betik onu "ölü kod" sanar (aşağıdaki not bunu açıkça söyler).
    "agent_core/scraper/run_scraper.py",
)
ENABLE_RE = re.compile(r"ENABLE_[A-Z0-9_]+")
#: Yalnız TIRNAK İÇİNDE geçen adlar gerçek okuma sayılır. Aksi hâlde
#: ``ENABLE_RE`` gibi değişken adları ve ``PINEAL_ENABLE_...`` gibi başka
#: bir ayarın parçası "kapı" sanılır (yanlış alarm, yanlış rapor).
QUOTED_ENABLE_RE = re.compile(r"""["'](ENABLE_[A-Z0-9_]+)["']""")


def rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def python_files(*roots: str) -> List[Path]:
    out: List[Path] = []
    for root in roots:
        base = REPO / root
        if base.is_file():
            out.append(base)
            continue
        for p in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            out.append(p)
    return out


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


# --------------------------------------------------------------- 1 · yetenekler
class _with_flags:
    """Geçici env bağlamı: kapıları açıp defteri yeniden kurar, sonra geri alır."""

    def __init__(self, values: Dict[str, str]):
        self.values = values
        self.old: Dict[str, str | None] = {}

    def __enter__(self):
        import os

        for k, v in self.values.items():
            self.old[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        import os

        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def capability_inventory() -> Dict[str, Any]:
    """Yetenek defterini GERÇEKTEN yükle; yüklenemezse dürüstçe bildir."""
    sys.path.insert(0, str(REPO))
    try:
        from agent_core.capabilities.policy import MANAGED_GATE_FLAGS
        from agent_core.capabilities.registry import bootstrap
    except Exception as exc:  # pragma: no cover - bağımlılık yoksa
        return {"error": f"{type(exc).__name__}: {exc}", "items": []}

    reg = bootstrap()
    managed = set(MANAGED_GATE_FLAGS)
    #: İKİNCİ SENARYO: bütün yönetilen kapılar "true" iken durum ne?
    #: Böylece "kapı kapalı" ile "kapı açık ama kütüphane/uç yok" ayrılır —
    #: kullanıcıya "şalteri aç, biter" demek yanlış olur.
    open_reasons: Dict[str, Any] = {}
    with _with_flags({flag: "true" for flag in managed}):
        reg_open = bootstrap()
        for cid in sorted(reg_open.ids()):
            open_reasons[cid] = reg_open.get(cid).availability()
    items = []
    for cid in sorted(reg.ids()):
        cap = reg.get(cid)
        av = cap.availability()
        av_open = open_reasons.get(cid) or av
        gates = sorted(getattr(cap, "gates", frozenset()) or [])
        env_gates = [g for g in gates if g in managed]
        items.append(
            {
                "id": cid,
                "kind": str(getattr(cap, "kind", "")),
                "license": getattr(cap, "license", None),
                "gates": gates,
                "env_gates": env_gates,
                "unmanaged_gates": [g for g in gates if g.startswith("ENABLE_") and g not in managed],
                "available": bool(av.available),
                "reason": av.reason,
                "available_gates_open": bool(av_open.available),
                "reason_gates_open": av_open.reason,
                "wake_class": (
                    "hazır" if av.available
                    else "sadece_kapi" if av_open.available
                    else "kurulum_gerekli"
                ),
            }
        )
    return {"error": None, "count": len(items), "items": items, "managed_gate_flags": sorted(managed)}


# ------------------------------------------------------------------ 2 · zincir
def _text_index() -> List[tuple[str, str]]:
    """(yol, içerik) listesi — yetenek kimliği / uç aramaları için tek geçiş."""
    rows: List[tuple[str, str]] = []
    for base in ("agent_core", "backend", "frontend/src", "scripts", "skills", "config"):
        root = REPO / base
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix not in {".py", ".ts", ".tsx", ".js", ".svelte", ".json", ".md", ".html", ".yaml", ".yml"}:
                continue
            rows.append((rel(p), read(p)))
    return rows


def _routes() -> List[Dict[str, Any]]:
    """Backend'deki her HTTP ucunu gövdesiyle birlikte çıkar (tek kaynak)."""
    routes: List[Dict[str, Any]] = []
    for path in python_files("backend"):
        lines = read(path).splitlines()
        for n, line in enumerate(lines):
            m = ROUTE_RE.search(line)
            if not m:
                continue
            body_lines: List[str] = []
            for offset, nxt in enumerate(lines[n: n + 150]):
                if offset and ROUTE_RE.search(nxt):
                    break
                #: Sıfır girintili yeni bir blok (yeni fonksiyon/assignment) gövdeyi bitirir:
                #: aksi hâlde üstteki dağıtıcı tablolar bir sonraki ucun gövdesine sızıyordu.
                if offset and nxt[:1] not in ("", " ", "\t", ")", "]", "}"):
                    break
                body_lines.append(nxt)
            routes.append(
                {
                    "file": rel(path),
                    "method": m.group(1).upper(),
                    "path": m.group(2),
                    "body": "\n".join(body_lines),
                }
            )
    return routes


def _frontend_text(index: List[tuple[str, str]]) -> str:
    return "\n".join(t for p, t in index if p.startswith("frontend/"))


def capability_wiring(
    caps: Iterable[Dict[str, Any]],
    routes: List[Dict[str, Any]],
    index: List[tuple[str, str]],
) -> List[Dict[str, Any]]:
    """Yetenek → kim çağırıyor? (HTTP ucu / hat kodu / MCP / arayüz)

    Eşleşme kuralları DAR tutulur; yanlış "bağlı" damgası, yanlış "kapalı"
    damgası kadar zararlıdır:
      * **uç**: yeteneğin tam kimliği uç gövdesinde geçiyor, ya da tam kimlik
        aynı DOSYADA geçiyor ve yeteneğin ara kademesi uç yolunda var
        (``analyzer.media.frames`` + ``/api/media/...`` gibi dağıtıcı tablolar).
      * **hat**: ``agent_core/`` altında (capabilities/ hariç) tam kimlik
        literal olarak geçiyor — servis katmanı yeteneği adıyla çağırıyor.
      * **MCP**: defter MCP araçlarını kendiliğinden üretir; defterdeki her
        yetenek MCP'de vardır (türetme, uydurma değil).
      * **arayüz**: yalnız uç varsa ve o uç arayüzde çağrılıyorsa "evet".
    """
    fe = _frontend_text(index)
    rows = []
    for cap in caps:
        cid = cap["id"]
        parts = cid.split(".")
        middle = parts[1] if len(parts) > 2 else None
        file_cache: Dict[str, str] = {}

        def file_text(path: str) -> str:
            if path not in file_cache:
                file_cache[path] = read(REPO / path)
            return file_cache[path]

        hit_routes = []
        for r in routes:
            segments = {seg for seg in r["path"].strip("/").split("/")}
            if cid in r["body"] or cid.split(".")[-1] in segments:
                hit_routes.append(r)
            elif middle and middle in segments and cid in file_text(r["file"]):
                hit_routes.append(r)
        paths = sorted({r["path"] for r in hit_routes})
        #: Arayüz "tetikliyor" sayılması için durum ucundan farklı bir uç çağrılmalı;
        #: yalnız /status göstermek tetikleme DEĞİLDİR.
        frontend = any(
            _route_in_frontend(path, fe)
            for path in paths
            if not path.rstrip("/").endswith("/status")
        )

        pipeline = sorted(
            p for p, t in index
            if p.startswith("agent_core/")
            and not p.startswith("agent_core/capabilities/")
            and p.endswith(".py")
            and cid in t
        )
        rows.append(
            {
                "id": cid,
                "routes": [f'{r["method"]} {r["path"]}' for r in hit_routes],
                "pipeline_refs": pipeline,
                "mcp_tool": True,
                "frontend_invokes": frontend,
                "skill_doc": (REPO / "skills" / cid.replace(".", "_") / "SKILL.md").exists(),
            }
        )
    return rows


def _route_in_frontend(path: str, frontend_text: str) -> bool:
    """Uç yolunun arayüzde geçip geçmediği (parametreli yollar önekiyle aranır)."""
    prefix = ROUTE_PARAM_RE.sub("", path).rstrip("/")
    return bool(prefix) and prefix in frontend_text


# ------------------------------------------------------------------- 3 · ajanlar
def agent_inventory(index: List[tuple[str, str]]) -> Dict[str, Any]:
    executor_src = read(REPO / "agent_core" / "task_executor.py")
    block = re.search(r"self\.agents\s*=\s*\{(.*?)\n        \}", executor_src, re.S)
    #: anahtar -> sınıf adı (``"resonance_calc": ResonanceCalculator(...)``)
    key_class: Dict[str, str] = {}
    if block:
        for m in re.finditer(r'"([a-z0-9_]+)"\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(', block.group(1)):
            key_class[m.group(1)] = m.group(2)
    wired = sorted(key_class)
    class_to_key = {v: k for k, v in key_class.items()}

    gated_wired: List[str] = []
    if block and 'ENABLE_INTERPRETER' in executor_src[block.end(): block.end() + 1500]:
        gated_wired = ["interpreter"]

    rack_map_src = re.search(r"_AGENT_RACK_MAP\s*=\s*\{(.*?)\n    \}", executor_src, re.S)
    rack_map = dict(re.findall(r'"([a-z0-9_]+)"\s*:\s*(?:"([a-z0-9_]+)"|None)', rack_map_src.group(1))) if rack_map_src else {}

    router_src = read(REPO / "agent_core" / "services" / "cognitive_router.py")
    test_src = " ".join(read(p) for p in python_files("tests"))
    frontend = " ".join(t for p, t in index if p.startswith("frontend/"))

    rows = []
    for path in sorted((REPO / "agent_core" / "agents").glob("*.py")):
        stem = path.stem
        if stem == "__init__":
            continue
        src = read(path)
        class_names = re.findall(r"^class\s+([A-Za-z0-9_]+)", src, re.M)
        key = next((class_to_key[c] for c in class_names if c in class_to_key), None)
        if key is None:
            key = next((k for k in key_class if k in stem or stem in k), None)
        rows.append(
            {
                "module": f"agent_core/agents/{stem}.py",
                "classes": class_names,
                "wired_in_executor": key is not None,
                "executor_key": key,
                "rack_slot": rack_map.get(key) if key else None,
                "gated": key is None and "ENABLE_" in src,
                "in_router": stem in router_src,
                "in_frontend": stem in frontend,
                "tested": any(name in test_src for name in [stem, *class_names] if len(name) > 4),
            }
        )
    return {
        "wired_count": len(wired),
        "wired": wired,
        "gated_wired": gated_wired,
        "rack_map": rack_map,
        "modules": rows,
        "unwired_modules": [r["module"] for r in rows if not r["wired_in_executor"]],
    }


# --------------------------------------------------------------------- 4 · uçlar
ROUTE_RE = re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')
ROUTE_PARAM_RE = re.compile(r"\{[^}]*\}")


def route_inventory(routes: List[Dict[str, Any]], index: List[tuple[str, str]]) -> Dict[str, Any]:
    fe = _frontend_text(index)
    rows = []
    for r in routes:
        gates = sorted(set(ENABLE_RE.findall(r["body"])))
        rows.append(
            {
                "file": r["file"],
                "method": r["method"],
                "path": r["path"],
                "gates": gates,
                "frontend_referenced": _route_in_frontend(r["path"], fe),
                "experimental": r["path"].startswith("/api/experimental"),
            }
        )
    rows.sort(key=lambda r: (r["path"], r["method"]))
    return {
        "count": len(rows),
        "frontend_unreferenced": [f'{r["method"]} {r["path"]}' for r in rows if not r["frontend_referenced"]],
        "gated_routes": [f'{r["method"]} {r["path"]} ({", ".join(r["gates"])})' for r in rows if r["gates"]],
        "experimental": [f'{r["method"]} {r["path"]}' for r in rows if r["experimental"]],
        "routes": rows,
    }


# ------------------------------------------------------------------- 5 · kapılar
def gate_inventory() -> Dict[str, Any]:
    sys.path.insert(0, str(REPO))
    try:
        from agent_core.capabilities.policy import MANAGED_GATE_FLAGS
    except Exception as exc:  # pragma: no cover
        return {"error": f"{type(exc).__name__}: {exc}"}
    managed = sorted(MANAGED_GATE_FLAGS)
    env_example = read(REPO / ".env.example")
    example_gates = sorted({m.group(1) for m in re.finditer(r"^(ENABLE_[A-Z0-9_]+)=", env_example, re.M)})

    code_gates: Set[str] = set()
    for path in python_files("agent_core", "backend", "scripts"):
        code_gates |= set(QUOTED_ENABLE_RE.findall(read(path)))

    return {
        "managed": managed,
        "managed_count": len(managed),
        "env_example_gates": example_gates,
        "code_gates": sorted(code_gates),
        "code_but_unmanaged": sorted(code_gates - set(managed)),
        "managed_but_missing_from_example": sorted(set(managed) - set(example_gates)),
        "example_but_unmanaged": sorted(set(example_gates) - set(managed)),
    }


# ------------------------------------------------------------------- 6 · erişim
def _module_name(path: Path) -> str:
    parts = list(path.relative_to(REPO).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path, module_name: str) -> Set[str]:
    """Bir modülün (göreli importlar dahil) hedeflediği modül adları."""
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return set()
    package = module_name.rsplit(".", 1)[0] if path.stem != "__init__" else module_name
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                drop = node.level - 1
                if drop:
                    parts = parts[:-drop] if drop <= len(parts) else []
                base = ".".join([*parts, base]) if base else ".".join(parts)
            if base:
                found.add(base)
            for a in node.names:  # `from x import y` → y bir alt modül olabilir
                found.add(f"{base}.{a.name}" if base else a.name)
    return {f for f in found if f}


def reachability() -> Dict[str, Any]:
    modules = {_module_name(p): p for p in python_files("agent_core", "backend")}
    graph = {
        name: {i for i in _imports(p, name) if i in modules or i.split(".")[0] in {"agent_core", "backend"}}
        for name, p in modules.items()
    }
    seen: Set[str] = set()
    queue: List[str] = []
    #: Giriş noktaları (backend/api.py, main.py, run_lilith.py, scraper.py, ...)
    #: kendileri agent_core/backend paketinde değilse bile IMPORTLARI sayılır;
    #: aksi hâlde "run_lilith → lilith_growth" bağı görülmez ve CLI aracı
    #: yanlışlıkla "ölü kod" damgası yerdi.
    for entry in ENTRYPOINTS:
        path = REPO / entry
        if not path.exists():
            continue
        name = _module_name(path)
        if name in modules:
            queue.append(name)
        for imported in _imports(path, name):
            if imported in modules:
                queue.append(imported)
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in graph.get(cur, ()):
            if nxt in modules and nxt not in seen:
                queue.append(nxt)
    #: Bir alt modül erişilebiliyorsa paketi de erişilebilir sayılır
    #: (``from agent_core.agents.passion_mapper import ...`` → ``agent_core.agents``).
    for name in list(seen):
        parts = name.split(".")
        for i in range(1, len(parts)):
            seen.add(".".join(parts[:i]))
    unreachable = sorted(m for m in modules if m not in seen)

    #: Ulaşılamayan modüllerin "gerçekten kullanılıyor mu" ikinci kanıtı:
    #: testlerde veya scripts/ içinde anılıyor mu?
    test_index = " ".join(read(p) for p in python_files("tests"))
    script_index = " ".join(read(p) for p in python_files("scripts"))
    rows = []
    for name in unreachable:
        rows.append(
            {
                "module": name,
                "file": rel(modules[name]),
                "tested": name in test_index or name.split(".")[-1] in test_index,
                "used_by_script": name in script_index or name.split(".")[-1] in script_index,
            }
        )
    return {
        "entrypoints": list(ENTRYPOINTS),
        "reachable_count": len([m for m in modules if m in seen]),
        "module_count": len(modules),
        "unreachable": rows,
    }


# ------------------------------------------------------------------ 7 · gömülü
def embedded_assets(index: List[tuple[str, str]]) -> List[Dict[str, Any]]:
    checks = [
        ("rust_core", "Rust çekirdeği (cargo)"),
        ("android", "Android kabuğu"),
        ("functions", "Cloudflare/Vercel edge fonksiyonları"),
        ("worker.ts", "Edge worker"),
        ("scraper.py", "Kök scraper"),
        ("live_llm_gate.py", "Canlı LLM kapısı"),
        ("release", "Sürüm kilit dosyaları"),
        ("skills", "SKILL.md araç defteri"),
        ("docs/envanter.html", "Envanter sayfası"),
        ("config/agent_tiers.json", "Ajan kademe planı"),
    ]
    #: "Ürün kodu anıyor mu?" — doküman ve test HARİÇ, yalnız çalışan kod sayılır
    #: (agent_core/, backend/, frontend/src, functions/, worker.ts). Böylece
    #: yalnız README'de geçen bir varlık "bağlı" sanılmaz.
    code_files = [
        (p, t) for p, t in index
        if p.endswith((".py", ".ts", ".svelte", ".json"))
        and p.startswith(("agent_core/", "backend/", "frontend/src/", "scripts/"))
    ]
    rows = []
    for path, desc in checks:
        p = REPO / path
        if not p.exists():
            rows.append({"path": path, "desc": desc, "exists": False, "code_refs": []})
            continue
        name = Path(path).stem if Path(path).suffix else Path(path).name
        refs = sorted({fp for fp, ft in code_files if name in ft and not fp.startswith(path)})
        rows.append({"path": path, "desc": desc, "exists": True, "code_refs": refs})
    return rows


# ---------------------------------------------------------- LLM motoru (API anahtarı + canlı çağrı bayrağı)
def llm_engine_inventory() -> Dict[str, Any]:
    """LLM motorunun çalışıp çalışmadığını kontrol eder.

    TargetPsycheProfiler (PassionMapper, FrictionDetector, CognitiveProfiler)
    ve diğer LLM-güvenli ajanlar (authenticity_auditor, depth_analyst,
    human_behavior, mirror_truth, resonance_synthesizer) şu iki koşulu birlikte
    karşılamalıdır:

      1. En az bir LLM API anahtarı tanımlı (OPENROUTER_API_KEY, GROQ_API_KEY,
         GEMINI_API_KEY, DEEPSEEK_API_KEY, NINEROUTER_API_KEY, vb.)
      2. Canlı çağrı bayrası açık (LIVE_LLM_E2E=1 veya PINEAL_ROUTER_LIVE=1)

    Yerel 9Router kullanılıyorsa NINEROUTER_BASE_URL da tanımlı olmalıdır.
    Herhangi biri eksikse motor `llm_unavailable` döner ve hedef kişi analizi
    (core_passions, sensitivities, vb.) boş döner.
    """
    api_keys = {
        "OPENROUTER_API_KEY": "OpenRouter (bulut)",
        "GROQ_API_KEY": "Groq (gpt-oss-120b)",
        "GEMINI_API_KEY": "Google Gemini",
        "DEEPSEEK_API_KEY": "DeepSeek",
        "NINEROUTER_API_KEY": "9Router yerel hub",
        "MISTRAL_API_KEY": "Mistral",
        "TOGETHER_API_KEY": "Together",
        "FIREWORKS_API_KEY": "Fireworks",
        "DASHSCOPE_API_KEY": "DashScope",
        "SAMBANOVA_API_KEY": "SambaNova",
        "NVIDIA_API_KEY": "NVIDIA NIM",
        "HUGGINGFACE_API_KEY": "HuggingFace",
        "DEEPINFRA_API_KEY": "DeepInfra",
        "PERPLEXITY_API_KEY": "Perplexity",
        "CEREBRAS_API_KEY": "Cerebras",
        "NOUS_API_KEY": "Nous Research",
    }
    found_keys = {name: bool(os.getenv(name, "").strip()) for name in api_keys}
    any_key = any(found_keys.values())
    live_e2e = os.getenv("LIVE_LLM_E2E", "0").strip() == "1"
    router_live = os.getenv("PINEAL_ROUTER_LIVE", "0").strip() == "1"
    any_live = live_e2e or router_live
    local_llm = os.getenv("USE_LOCAL_LLM", "false").strip().lower() == "true"
    ninerouter_base_url = os.getenv("NINEROUTER_BASE_URL", "").strip()
    ninerouter_configured = bool(found_keys.get("NINEROUTER_API_KEY") and ninerouter_base_url)

    engine_ok = any_key and any_live
    reason = None
    if not any_key:
        reason = "no_llm_api_key"
    elif not any_live:
        reason = "live_llm_disabled"

    return {
        "any_api_key": any_key,
        "api_keys": found_keys,
        "ninerouter_base_url": ninerouter_base_url,
        "ninerouter_configured": ninerouter_configured,
        "live_llm_e2e": live_e2e,
        "pineal_router_live": router_live,
        "any_live": any_live,
        "use_local_llm": local_llm,
        "engine_ok": engine_ok,
        "reason": reason,
    }


# ---------------------------------------------------------- CLI araçları (ffmpeg, theHarvester, ...)
def cli_tool_inventory() -> List[Dict[str, Any]]:
    """Yeteneklerin ihtiyaç duyduğu CLI araçlarının PATH'teki varlığı.

    Python paketleri `importlib.util.find_spec` ile, CLI araçları ise
    `shutil.which` ile kontrol edilir. Bu sayfa denetim makinesine özeldir;
    Windows'taki kullanıcı kendi ortamında farklı sonuç görebilir.
    """
    checks = [
        ("ffmpeg", "Video kodlama (renderer.report.video)"),
        ("theHarvester", "Kurum keşif CLI'ı (sensor.company.harvester)"),
        ("theharvester", "Kurum keşif CLI'ı (alternatif isim)"),
        ("piper", "Yerel TTS (voice.tts.local)"),
        ("node", "Edge worker / frontend build"),
        ("npm", "Edge worker / frontend build (agent-reach kurulumu)"),
        ("cargo", "Rust çekirdeği (rust_core)"),
    ]
    rows = []
    for name, desc in checks:
        found = shutil.which(name)
        #: Python paketi olarak da kontrol et (bazı CLI'lar hem modül hem komuttur).
        try:
            importable = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, AttributeError):
            importable = False
        rows.append(
            {
                "name": name,
                "desc": desc,
                "path": found,
                "importable": importable,
                "available": bool(found or importable),
            }
        )
    return rows


# ---------------------------------------------------------------------- rapor
def build() -> Dict[str, Any]:
    index = _text_index()
    caps = capability_inventory()
    gates = gate_inventory()
    agents = agent_inventory(index)
    route_rows = _routes()
    routes = route_inventory(route_rows, index)
    reach = reachability()
    assets = embedded_assets(index)
    wiring = capability_wiring(caps.get("items", []), route_rows, index) if caps.get("items") else []
    return {
        "sema_surumu": 1,
        "olcum": "scripts/golge_denetimi.py",
        "olcum_zamani": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "yetenecek_sayisi": caps.get("count", 0),
        "yetenekler": caps,
        "zincir": wiring,
        "ajanlar": agents,
        "uclar": routes,
        "kapilar": gates,
        "erisim": reach,
        "gomulu": assets,
        "cli_tools": cli_tool_inventory(),
        "llm_engine": llm_engine_inventory(),
    }


def markdown(data: Dict[str, Any]) -> str:
    L: List[str] = []
    a = L.append
    a("# GÖLGE DENETİMİ — hiçbir şey gölgede kalmasın")
    a("")
    a("> Bu dosya `scripts/golge_denetimi.py` tarafından ÜRETİLİR. Elle yazılmış sayı yoktur;")
    a("> yeniden çalıştırıldığında depo neyse rapor odur.")
    a("")
    a(f"- Ölçüm anı: {data.get('olcum_zamani', '—')} · Python {data.get('python', '—')} · "
      f"platform `{data.get('platform', '—')}`")
    a("- **Kritik uyarı:** `dependency_missing` / `no_engine` gibi sebepler ÖLÇÜLDÜĞÜ MAKİNEYE bağlıdır.")
    a("  Bu raporu kendi ortamınızda üretmek için: `python scripts/golge_denetimi.py`.")
    a("")
    caps = data["yetenekler"]
    a("## 1 · Yetenek defteri")
    a("")
    if caps.get("error"):
        a(f"Defter yüklenemedi: `{caps['error']}`")
    else:
        avail = [c for c in caps["items"] if c["available"]]
        a(f"- Defterde **{caps['count']}** yetenek var; bu ortamda **{len(avail)}** tanesi kullanılabilir.")
        a("")
        classes = {"hazır": 0, "sadece_kapi": 0, "kurulum_gerekli": 0}
        for c in caps["items"]:
            classes[c["wake_class"]] = classes.get(c["wake_class"], 0) + 1
        a(
            f"- Uyanma sınıfı: **{classes['hazır']}** hazır, "
            f"**{classes['sadece_kapi']}** yalnız kapı kapalı olduğu için duruyor, "
            f"**{classes['kurulum_gerekli']}** kapı açılsa da kurulum/hesap/uç istiyor."
        )
        a("")
        a("| Yetenek | Tür | Kapılar | Şimdi | Kapılar açıkken | Sebep (kapılar açıkken) |")
        a("| --- | --- | --- | --- | --- | --- |")
        for c in caps["items"]:
            gates = ", ".join(c["env_gates"]) or "—"
            state = "AÇIK" if c["available"] else "KAPALI"
            open_state = "AÇIK" if c["available_gates_open"] else "KAPALI"
            open_reason = c["reason_gates_open"] or "—"
            a(
                f"| `{c['id']}` | {c['kind'].replace('CapabilityKind.', '')} | {gates} | {state} | "
                f"{open_state} | {open_reason} |"
            )
    a("")
    a("## 2 · Zincir: yetenek → backend → SKILL → arayüz")
    a("")
    a("| Yetenek | HTTP ucu | Hatta çağıran | MCP aracı | SKILL.md | Arayüz tetikliyor |")
    a("| --- | --- | --- | --- | --- | --- |")
    for w in data["zincir"]:
        routes_txt = "<br>".join(f"`{r}`" for r in w["routes"]) if w["routes"] else "**uç yok**"
        pipe = f"{len(w['pipeline_refs'])} dosya" if w["pipeline_refs"] else "**yok**"
        a(
            f"| `{w['id']}` | {routes_txt} | {pipe} | {'var' if w['mcp_tool'] else 'yok'} | "
            f"{'var' if w['skill_doc'] else '**YOK**'} | {'evet' if w['frontend_invokes'] else '**hayır**'} |"
        )
    a("")
    ag = data["ajanlar"]
    a("## 3 · Ajanlar")
    a("")
    a(f"- Yürütücüye kayıtlı: **{ag['wired_count']}** — {', '.join(f'`{x}`' for x in ag['wired'])}")
    if ag["gated_wired"]:
        a(f"- Kapı arkasında kayıtlı: {', '.join(f'`{x}`' for x in ag['gated_wired'])}")
    a("")
    a("| Modül | Sınıf(lar) | Yürütücü anahtarı | Rack slotu | Router'da | Arayüzde | Test |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    for m in ag["modules"]:
        key = f"`{m['executor_key']}`" if m["executor_key"] else ("**bağlı değil**" + (" (kapı arkasında)" if m["gated"] else ""))
        a(
            f"| `{m['module']}` | {', '.join(m['classes']) or '—'} | {key} | {m['rack_slot'] or '—'} | "
            f"{'evet' if m['in_router'] else 'hayır'} | {'evet' if m['in_frontend'] else 'hayır'} | "
            f"{'evet' if m['tested'] else 'hayır'} |"
        )
    a("")
    u = data["uclar"]
    a("## 4 · HTTP uçları")
    a("")
    a(f"- Toplam **{u['count']}** uç; arayüzde referansı olmayan **{len(u['frontend_unreferenced'])}**, "
      f"deneysel **{len(u['experimental'])}**.")
    a("")
    a("### Arayüzden çağrılmayan uçlar")
    a("")
    for r in u["frontend_unreferenced"]:
        a(f"- `{r}`")
    a("")
    k = data["kapilar"]
    a("## 5 · Kapılar (env)")
    a("")
    if k.get("error"):
        a(f"Okunamadı: `{k['error']}`")
    else:
        a(f"- Yönetilen kapı: **{k['managed_count']}**")
        a(f"- Kodda okunan ama YÖNETİLMEYEN: {', '.join(f'`{g}`' for g in k['code_but_unmanaged']) or '—'}")
        a(f"- Yönetilen ama `.env.example`'da olmayan: {', '.join(f'`{g}`' for g in k['managed_but_missing_from_example']) or '—'}")
        a(f"- Örnekte olup yönetilmeyen: {', '.join(f'`{g}`' for g in k['example_but_unmanaged']) or '—'}")
    a("")
    e = data["erisim"]
    a("## 6 · Erişilemeyen modüller (giriş noktalarından AST ile)")
    a("")
    a(f"- {e['module_count']} modülden **{e['reachable_count']}** tanesi giriş noktalarından erişilebilir; "
      f"**{len(e['unreachable'])}** tanesi değil.")
    a("- Giriş noktası listesi `scripts/golge_denetimi.py` içinde BEYAN edilir "
      f"({len(e['entrypoints'])} adet). Yeni bir CLI eklenip buraya yazılmazsa "
      "betik onu ölü kod sanar — yani bu bölümün tek zayıf noktası, listeyi güncel tutmaktır.")
    a("")
    if e["unreachable"]:
        a("| Modül | Test | Script kullanıyor |")
        a("| --- | --- | --- |")
        for r in e["unreachable"]:
            a(f"| `{r['module']}` | {'evet' if r['tested'] else 'hayır'} | {'evet' if r['used_by_script'] else 'hayır'} |")
        a("")
    a("## 7 · Uyanma planı — sebebe göre ne gerekiyor")
    a("")
    plan: Dict[str, List[str]] = {}
    if not caps.get("error"):
        for c in caps["items"]:
            if c["available"]:
                continue
            if c["available_gates_open"]:
                head = "gate_disabled"  #: sadece şalter kapalı olduğu için duruyor
            else:
                head = (c["reason_gates_open"] or "bilinmeyen").split(":", 1)[0]
            plan.setdefault(head, []).append(c["id"])
    ACTION = {
        "gate_disabled": "yalnız şalter: `.env` içinde ilgili `ENABLE_*` = true",
        "dependency_missing": "Python/CLI bağımlılığı kurulu değil → `requirements-osint.txt` / `requirements-retina.txt` / `requirements-ml.txt` içindeki paket",
        "no_engine": "yerel motor yok → `PINEAL_TRANSLATE_CMD` / `PINEAL_STT_CMD` gibi bir CLI ya da yerel HTTP ucu tanımla",
        "no_local_endpoint": "yerel uç tanımlı değil → `PINEAL_TTS_URL` / `PINEAL_STT_URL` (yalnız 127.0.0.1)",
        "no_local_models": "yerel model yok → `ENABLE_LOCAL_JURY` için yerel LLM bitiş noktası",
        "config_missing": "eksik yapılandırma → ilgili env değeri (ör. `SEARXNG_BASE_URL`)",
    }
    a("| Sebep | Yetenek sayısı | Ne gerekiyor |")
    a("| --- | --- | --- |")
    for head in sorted(plan):
        a(f"| `{head}` | {len(plan[head])} | {ACTION.get(head, 'inceleme gerekli')} |")
    a("")
    for head in sorted(plan):
        a(f"- **{head}**: " + ", ".join(f"`{c}`" for c in plan[head]))
    a("")
    a("## 8 · Depoda duran gömülü varlıklar")
    a("")
    a("_Not: son sütun gevşek bir metin sayımıdır (ad, kod dosyalarında kaç yerde geçiyor);")
    a("'bağlı' kanıtı değil, 'anılıyor' göstergesidir._")
    a("")
    a("| Yol | Ne | Var | Ürün kodunda kaç dosya anıyor |")
    a("| --- | --- | --- | --- |")
    for r in data["gomulu"]:
        refs = r.get("code_refs") or []
        a(f"| `{r['path']}` | {r['desc']} | {'evet' if r['exists'] else 'hayır'} | "
          f"{len(refs) if refs else '**0**'} |")
    a("")
    a("## 9 · CLI araçları (PATH / import tespiti)")
    a("")
    a("_Bu bölüm denetim makinesine özeldir. Windows ortamında ffmpeg / theHarvester_")
    a("_gibi araçların PATH'te olması farklı sonuç verebilir. `shutil.which`_")
    a("_ile PATH, `importlib.util.find_spec` ile Python paketi olarak denetlenir._")
    a("| Araç | Ne için | PATH'te | Python paketi olarak | Durum |")
    a("| --- | --- | --- | --- | --- |")
    for t in data.get("cli_tools", []):
        durum = "✓ mevcut" if t["available"] else "✗ yok"
        a(
            f"| `{t['name']}` | {t['desc']} | "
            f"{'evet' if t['path'] else 'hayır'} | "
            f"{'evet' if t['importable'] else 'hayır'} | {durum} |"
        )
    a("")

    le = data.get("llm_engine", {})
    a("## 10 · LLM motoru (API anahtarı + canlı çağrı bayrağı)")
    a("")
    a("_Bu bölüm, TargetPsycheProfiler ve LLM-güvenli ajanların çalışıp çalışmadığını kontrol eder:_")
    a("_`PassionMapper`, `FrictionDetector`, `CognitiveProfiler`, `authenticity_auditor`,_")
    a("_`depth_analyst`, `human_behavior`, `mirror_truth`, `resonance_synthesizer`._")
    a("")
    if le.get("engine_ok"):
        a("- **Durum: ✓ ÇALIŞIYOR** — LLM API anahtarı tanımlı ve canlı çağrı bayrağı açık.")
    else:
        a("- **Durum: ✗ KAPALI** — LLM motoru çalışmıyor, hedef kişi analizi boş döner (`core_passions=[]`, `sensitivities=[]`).")
        if le.get("reason") == "no_llm_api_key":
            a("  - Neden: Hiçbir LLM API anahtarı tanımlı değil (`.env`'de tüm `*_API_KEY` değerleri boş).")
        elif le.get("reason") == "live_llm_disabled":
            a("  - Neden: API anahtarı tanımlı ama canlı LLM çağrıları kapalı (`LIVE_LLM_E2E=0`).")
        else:
            a("  - Neden: Bilinmeyen yapılandırma sorunu.")
    a("")
    a("| Ayar | Değer | Açıklama |")
    a("| --- | --- | --- | |")
    a(f"| Herhangi bir API anahtarı | {'evet' if le.get('any_api_key') else 'hayır'} | `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `NINEROUTER_API_KEY` vb. |")
    a(f"| `LIVE_LLM_E2E` | {'1' if le.get('live_llm_e2e') else '0'} | Canlı LLM çağrılarını açar (`.env`). |")
    a(f"| `PINEAL_ROUTER_LIVE` | {'1' if le.get('pineal_router_live') else '0'} | Router canlı moda geçişi (`.env`). |")
    a(f"| `NINEROUTER_BASE_URL` | {le.get('ninerouter_base_url') or 'boş'} | Yerel 9Router uç noktası (örn. `http://127.0.0.1:20128/v1`). |")
    a(f"| `USE_LOCAL_LLM` | {'true' if le.get('use_local_llm') else 'false'} | Yerel LLM (Ollama/LM Studio) kullanımı. |")
    a("")
    a("| Tanımlı API anahtarları | Değer |")
    a("| --- | --- | |")
    for name, desc in sorted(le.get("api_keys", {}).items()):
        val = le["api_keys"][name]
        a(f"| `{name}` | {'✓ tanımlı' if val else '✗ boş'} |")
    a("")
    a("**Açmak için:** `.env` dosyasına en az bir `*_API_KEY` (ör. `OPENROUTER_API_KEY=sk-...`")
    a("ya da `NINEROUTER_API_KEY` yerel 9Router için) yazın ve `LIVE_LLM_E2E=1` yapın,")
    a("sonra sunucuyu yeniden başlatın. Yerel 9Router için şu iki satır yeterlidir:")
    a("")
    a("    NINEROUTER_API_KEY=sk-...")
    a("    LIVE_LLM_E2E=1")
    a("")
    a("Yerel LLM için: `USE_LOCAL_LLM=true` + `LOCAL_LLM_URL=http://localhost:11434/v1`")
    a("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="reports/golge_denetimi.json")
    ap.add_argument("--md", default="docs/reports/GOLGE_DENETIMI.md")
    args = ap.parse_args()

    data = build()
    jpath = REPO / args.json
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    mpath = REPO / args.md
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(markdown(data), encoding="utf-8")

    print(f"yetenek: {data['yetenecek_sayisi']} | ajan: {data['ajanlar']['wired_count']} | "
          f"uç: {data['uclar']['count']} | erişilemeyen modül: {len(data['erisim']['unreachable'])}")
    print(f"yazıldı: {jpath} , {mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
