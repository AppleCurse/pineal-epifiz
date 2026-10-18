#!/usr/bin/env python3
"""ÖLÜ KOD / "ÇALIŞIR GİBİ YAPAN" DENETİMİ — kalıcı bekçi.

Kullanım:
    python scripts/dead_code_audit.py            # rapor + özet
    python scripts/dead_code_audit.py --json     # makine-okunur (CI için)

Bu betik **varsayım yapmaz**: her bulgu AST ile kanıtlanır. Dört denetim:

  C1  ÖLÜ MODÜL      — canlı kodda hiç import edilmemiş .py dosyası
  C2  ÖLÜ FONKSİYON  — canlı kodda hiç çağrılmamış (≥12 satır) fonksiyon
  C3  ÖLÜ AJAN       — executor'da KAYITLI ama hiç ÇAĞRILMAYAN ajan
  C4  ÖLÜ YETENEK    — kayıtlı (telemetride görünen) ama HİÇ DÜRÜLEMEYEN yetenek

Gürültü (false positive) sıfırlama kuralları:
  * giriş noktaları (CLI/CI/compose) izin listesinde
  * FastAPI rota handler'ları `app.get(...)(handler)` biçiminde kaydedildiği
    için "çağrılmamış" sayılmaz (fonksiyon referansı argüman olarak geçer)
  * `from x import y as z` takma adları çözümlenir
  * `scripts/archive/**` arşivlenmiş kod olarak ayrı sayılır
  * MCP sunucusu (`agent_core/mcp/server.py`) jenerik bir yüzeydir: kayıtlı
    her id'yi çalıştırabilir; C4 bunu bir istisna olarak belirtir.
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]

LIVE_DIRS = ("agent_core", "backend")
LIVE_FILES: list[pathlib.Path] = []
for _d in LIVE_DIRS:
    LIVE_FILES += sorted((ROOT / _d).rglob("*.py"))
LIVE_FILES += sorted(ROOT.glob("*.py"))
LIVE_FILES = [p for p in LIVE_FILES if "__pycache__" not in str(p)]
TEST_FILES = sorted((ROOT / "tests").rglob("*.py"))
ALL_FILES = LIVE_FILES + TEST_FILES


def refresh_scope() -> None:
    """Kapsamı yeniden hesapla (yeni/silinmiş dosya sonrası ölçüm için).

    Testler ve CLI, dosya eklenip silindikten sonra dedektörü taze kapsamla
    çalıştırabilsin diye; aksi hâlde liste ölçüm başında donmuş kalırdı.
    """
    global LIVE_FILES, TEST_FILES, ALL_FILES
    live: list[pathlib.Path] = []
    for _d in LIVE_DIRS:
        live += sorted((ROOT / _d).rglob("*.py"))
    live += sorted(ROOT.glob("*.py"))
    LIVE_FILES = [p for p in live if "__pycache__" not in str(p)]
    TEST_FILES = sorted((ROOT / "tests").rglob("*.py"))
    ALL_FILES = LIVE_FILES + TEST_FILES

ENTRYPOINTS = {
    "main.py",
    "scraper.py",
    "run_lilith.py",
    "live_llm_gate.py",
    "agent_core/mcp/__main__.py",
    "agent_core/scraper/run_scraper.py",
    "agent_core/workers/agent_worker.py",
}
ARCHIVE_PREFIX = "scripts/archive/"

RUNNER_NAMES = {"run_capability", "execute_capability", "run_capability_async"}


def rel(p: pathlib.Path) -> str:
    return p.relative_to(ROOT).as_posix()


def parse(p: pathlib.Path):
    try:
        return ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


# ── çağrı adları + takma ad çözümü ──────────────────────────────────────────
def call_references() -> tuple[set[str], dict[str, str]]:
    """(çağrılan adlar, takma ad→özgün ad haritası)."""
    called: set[str] = set()
    aliases: dict[str, str] = {}
    for p in ALL_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if nm:
                    called.add(nm)
                # fonksiyon referansı olarak geçen argümanlar (route kaydı vb.)
                for a in list(node.args) + [k.value for k in node.keywords]:
                    if isinstance(a, ast.Name):
                        called.add(a.id)
                    elif isinstance(a, ast.Attribute):
                        called.add(a.attr)
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.asname and a.asname != a.name:
                        aliases[a.asname] = a.name
    for local, orig in aliases.items():
        if local in called:
            called.add(orig)
    return called, aliases


# ── C1: ölü modül ────────────────────────────────────────────────────────────
def module_name_map() -> dict[str, pathlib.Path]:
    names: dict[str, pathlib.Path] = {}
    for p in ALL_FILES:
        parts = list(p.relative_to(ROOT).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names[".".join(parts)] = p
    return names


def dead_modules() -> tuple[list[dict], list[dict]]:
    """(hiç import edilmemiş modüller, YALNIZ testlerden import edilenler)."""
    names = module_name_map()
    imported: set[pathlib.Path] = set()
    imported_by_live: set[pathlib.Path] = set()
    for p in ALL_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            live_file = not str(p).startswith(str(ROOT / "tests"))
            if isinstance(node, ast.Import):
                for a in node.names:
                    tgt = names.get(a.name)
                    if tgt:
                        imported.add(tgt)
                        if live_file:
                            imported_by_live.add(tgt)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = p.parent
                    for _ in range(node.level - 1):
                        parent = parent.parent
                    base = ".".join(parent.relative_to(ROOT).parts)
                    if node.module:
                        base = f"{base}.{node.module}"
                for a in node.names:
                    tgt = names.get(f"{base}.{a.name}")
                    if tgt:
                        imported.add(tgt)
                        if live_file:
                            imported_by_live.add(tgt)
                tgt = names.get(base)
                if tgt:
                    imported.add(tgt)
                    if live_file:
                        imported_by_live.add(tgt)

    out = []
    test_only = []
    for p in LIVE_FILES:
        r = rel(p)
        if r in ENTRYPOINTS or p.name == "__init__.py" or r.startswith(ARCHIVE_PREFIX):
            continue
        if p not in imported:
            out.append({"path": r, "lines": len(p.read_text(encoding="utf-8", errors="replace").splitlines())})
        elif p not in imported_by_live:
            test_only.append({"path": r, "lines": len(p.read_text(encoding="utf-8", errors="replace").splitlines())})
    return out, test_only


# ── C2: ölü fonksiyon ────────────────────────────────────────────────────────
def reference_sites() -> dict[str, list[tuple[str, int]]]:
    """ad → [(dosya, satır)] — kodda "okunan" (Load) ad referansları."""
    sites: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for p in ALL_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                sites[node.id].append((rel(p), node.lineno))
            elif isinstance(node, ast.Attribute):
                sites[node.attr].append((rel(p), node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.asname and a.asname != a.name:
                        sites[a.name].append((rel(p), node.lineno))
    return sites


def dead_functions(min_lines: int = 12) -> list[dict]:
    """Fonksiyon adı, kendi gövdesi DIŞINDA hiç referans edilmiyorsa ölüdür.

    Özyineleme (kendi içinde kendini çağırmak) dış referans sayılmaz.
    """
    sites = reference_sites()
    out = []
    for p in LIVE_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("__") or node.name.startswith("test_"):
                continue
            # dekoratör bir çağrı ise → framework/adım kaydı var (FastAPI rota,
            # exception handler, middleware, cache) → çağrılmamış sayılmaz
            if any(isinstance(d, ast.Call) for d in node.decorator_list):
                continue
            start = node.lineno
            end = node.end_lineno or node.lineno
            external = [
                (f, ln)
                for f, ln in sites.get(node.name, ())
                if f != rel(p) or ln < start or ln > end
            ]
            if external:
                continue
            span = end - start
            if span < min_lines:
                continue
            out.append({"path": rel(p), "line": node.lineno, "name": node.name, "lines": span})
    return out


# ── C3: kayıtlı ama çağrılmayan ajan ────────────────────────────────────────
def dead_agents() -> list[dict]:
    exec_path = ROOT / "agent_core/task_executor.py"
    tree = parse(exec_path)
    if tree is None:
        return []
    registered: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            tgt_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            tgt_attrs = [t.attr for t in node.targets if isinstance(t, ast.Attribute)]
            if ("agents" in tgt_names or "agents" in tgt_attrs) and isinstance(node.value, ast.Dict):
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        registered.append(k.value)

    # doğrudan çağrı: self.agents["x"] / self.agents.get("x")
    direct: set[str] = set()
    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if unparse(node.value).startswith("self.agents"):
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    direct.add(sl.value)
                else:
                    dynamic = True
        if isinstance(node, ast.Call):
            txt = unparse(node.func)
            if txt.startswith("self.agents"):
                if "[" in txt:  # dinamik: self.agents[agent_name]
                    dynamic = True
                for a in list(node.args) + [k.value for k in node.keywords]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        direct.add(a.value)

    # router'ın seçebildiği ajanlar (dinamik çağrının kaynağı)
    selectable: set[str] = set()
    router = parse(ROOT / "agent_core/services/cognitive_router.py")
    if router is not None:
        for node in ast.walk(router):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in registered:
                    selectable.add(node.value)

    out = []
    for agent in registered:
        if agent in direct:
            continue
        if dynamic and agent in selectable:
            continue
        out.append({"agent": agent})
    return out


# ── C4: kayıtlı ama düşürülemeyen yetenek ───────────────────────────────────
def registered_capability_ids() -> tuple[list[str], str]:
    """Kayıt defterinden GERÇEK yetenek id listesi (varsayım yok).

    Birincil kaynak: çalışan kayıt defteri (`bootstrap()`), çünkü "hangi
    yetenek kayıtlı" sorusunun ikinci bir cevabı olamaz (registry.py kuralı).
    Yedek kaynak: adaptör sınıflarındaki `id = "..."` tanımları.
    """
    try:
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from agent_core.capabilities.registry import bootstrap

        reg = bootstrap()
        ids = sorted(getattr(reg, "_caps", {}).keys())
        if ids:
            return ids, "kayıt defteri (bootstrap)"
    except Exception as exc:  # pragma: no cover
        fallback_reason = f"kayıt defteri okunamadı: {type(exc).__name__}: {exc}"
    else:
        fallback_reason = ""
    ids = []
    for p in LIVE_FILES:
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'^\s{4}id\s*=\s*"([a-z0-9]+(?:\.[a-z0-9_]+){1,4})"', text, re.M):
            ids.append(m.group(1))
    return sorted(set(ids)), fallback_reason or "statik (id = ...)"


def _callgraph() -> dict[str, list[tuple[str, set[str], bool]]]:
    """fonksiyon adı → [(dosya, çağırdığı fonksiyonlar, runner çağırıyor mu)]"""
    info: dict[str, list[tuple[str, set[str], bool]]] = defaultdict(list)
    for p in LIVE_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls: set[str] = set()
            has_runner = False
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    txt = unparse(c.func)
                    nm = txt.rsplit(".", 1)[-1]
                    calls.add(nm)
                    if nm in RUNNER_NAMES or txt.endswith(".run"):
                        has_runner = True
            info[node.name].append((rel(p), calls, has_runner))
    return info


def _enclosing_function(tree, lineno: int) -> str | None:
    best = None
    best_span = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or node.lineno
            if start <= lineno <= end:
                span = end - start
                if best_span is None or span < best_span:
                    best, best_span = node.name, span
    return best


def _reaches_runner(fn: str | None, graph: dict, depth: int = 2) -> bool:
    """fn (veya çağırdığı fonksiyonlar) runner çağrısına ulaşıyor mu?"""
    if not fn:
        return False
    if depth < 0:
        return False
    for _file, calls, has_runner in graph.get(fn, []):
        if has_runner:
            return True
        for c in calls:
            if _reaches_runner(c, graph, depth - 1):
                return True
    return False


def _module_constants(p: pathlib.Path) -> dict[str, set[str]]:
    """Modül düzeyi sabitler: NAME → içindeki metin sabitleri."""
    consts: dict[str, set[str]] = defaultdict(set)
    tree = parse(p)
    if tree is None:
        return consts
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        raw = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in raw if isinstance(t, ast.Name)]
        if not names:
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                consts[names[0]].add(sub.value)
    return consts


def _const_load_functions(p: pathlib.Path) -> dict[str, set[str]]:
    """sabit adı → o sabiti kullanan fonksiyon adları (dosya içi)."""
    uses: dict[str, set[str]] = defaultdict(set)
    tree = parse(p)
    if tree is None:
        return uses
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    uses[sub.id].add(node.name)
    return uses


def _runner_call_args(p: pathlib.Path) -> list[tuple[int, str]]:
    """(satır, runner çağrısının argüman ifadesi metni)."""
    res: list[tuple[int, str]] = []
    tree = parse(p)
    if tree is None:
        return res
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            txt = unparse(node.func)
            nm = txt.rsplit(".", 1)[-1]
            if nm in RUNNER_NAMES or txt.endswith(".run"):
                for a in list(node.args) + [k.value for k in node.keywords]:
                    res.append((node.lineno, unparse(a)))
    return res


def dead_capabilities() -> tuple[list[dict], str]:
    ids, source = registered_capability_ids()
    graph = _callgraph()

    names = module_name_map()
    importers: dict[pathlib.Path, set[pathlib.Path]] = defaultdict(set)
    for p in ALL_FILES:
        tree = parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = p.parent
                    for _ in range(node.level - 1):
                        parent = parent.parent
                    base = ".".join(parent.relative_to(ROOT).parts)
                    if node.module:
                        base = f"{base}.{node.module}"
                for a in node.names:
                    tgt = names.get(f"{base}.{a.name}")
                    if tgt:
                        importers[tgt].add(p)
                tgt = names.get(base)
                if tgt:
                    importers[tgt].add(p)

    trees = {p: parse(p) for p in LIVE_FILES}
    out = []
    for cid in ids:
        holders = [p for p in LIVE_FILES if f'"{cid}"' in p.read_text(encoding="utf-8", errors="replace")]
        dispatch = None
        for p in holders:
            tree = trees.get(p)
            if tree is None:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            consts = _module_constants(p)
            const_uses = _const_load_functions(p)
            runner_args = _runner_call_args(p)
            for i, line in enumerate(text.splitlines(), 1):
                if f'"{cid}"' not in line:
                    continue
                # (0) doğrudan: runner çağrısının argümanı
                for lineno, arg in runner_args:
                    if f'"{cid}"' in arg:
                        dispatch = f"{rel(p)}:{lineno}"
                        break
                if dispatch:
                    break
                # (1) fonksiyon içinde (yerel sözlük/tablo)
                fn = _enclosing_function(tree, i)
                if fn and _reaches_runner(fn, graph):
                    dispatch = f"{rel(p)}:{i} ({fn})"
                    break
                # (2) modül düzeyi sabit: sabitin adı runner çağrısında geçiyor mu?
                for cname, vals in consts.items():
                    if cid not in vals:
                        continue
                    for _lineno, arg in runner_args:
                        if arg == cname:
                            dispatch = f"{rel(p)}:{i} (sabit {cname})"
                            break
                    if dispatch:
                        break
                    # sabiti kullanan fonksiyon runner'a ulaşıyor mu?
                    for fname in const_uses.get(cname, ()):
                        if _reaches_runner(fname, graph):
                            dispatch = f"{rel(p)}:{i} (sabit {cname} → {fname})"
                            break
                    if dispatch:
                        break
                if dispatch:
                    break
                # (3) modül düzeyi sabit: bu dosyayı import eden dosyada runner var
                if fn is None:
                    for imp in importers.get(p, ()):
                        if _file_has_runner(imp):
                            dispatch = f"{rel(p)}:{i} → {rel(imp)} (sabit aktarımı)"
                            break
                if dispatch:
                    break
            if dispatch:
                break
        if not dispatch:
            out.append({"capability": cid, "holders": sorted({rel(p) for p in holders})})
    return out, source


def _file_has_runner(p: pathlib.Path) -> bool:
    tree = parse(p)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    txt = unparse(c.func)
                    nm = txt.rsplit(".", 1)[-1]
                    if nm in RUNNER_NAMES or txt.endswith(".run"):
                        return True
    return False



# ── C5: ölü frontend bileşeni (giriş noktalarından ULAŞILAMAZ) ─────────────
FRONTEND_SRC = ROOT / "frontend/src"
FRONTEND_ENTRIES = ("main.ts", "App.svelte")
#: Vite/TS tip bildirimi — import edilmez, tsconfig'dan gelir (ölü kod DEĞİL)
FRONTEND_DECLARATIONS = ("vite-env.d.ts", "app.d.ts")


def _frontend_imports(f: pathlib.Path) -> list[pathlib.Path]:
    """Bir frontend dosyasının çözülmüş yerel import hedefleri."""
    text = f.read_text(encoding="utf-8", errors="replace")
    specs = re.findall(r"""from\s+['"]([^'"]+)['"]""", text)
    specs += re.findall(r"""import\s+['"]([^'"]+)['"]""", text)
    out: list[pathlib.Path] = []
    for spec in specs:
        if not spec.startswith("."):
            continue
        base = (f.parent / spec).resolve()
        for cand in (
            base,
            base.with_suffix(".svelte"),
            pathlib.Path(str(base) + ".svelte"),
            base / "index.ts",
            base.with_suffix(".ts"),
            pathlib.Path(str(base) + ".ts"),
            pathlib.Path(str(base) + ".js"),
        ):
            if cand.exists() and cand.is_file():
                out.append(cand)
                break
    return out


def dead_frontend() -> list[dict]:
    """Giriş noktalarından (main.ts → App.svelte) ULAŞILAMAYAN frontend dosyası.

    Ulaşılabilirlik sabit nokta (fixpoint) ile hesaplanır: yalnız başka ÖLÜ
    dosyaların import ettiği dosyalar da ölüdür. Dinamik import
    (`import(...)`) veya `<svelte:component this={...}>` varsa ölçüm
    güvenilmezdir → o durumda raporlanmaz (yanlış suçlama olmaz).
    """
    if not FRONTEND_SRC.exists():
        return []
    files = [
        f
        for f in FRONTEND_SRC.rglob("*")
        if f.suffix in {".svelte", ".ts", ".js"} and "node_modules" not in str(f)
    ]
    dynamic = False
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        # dinamik import yalnız YEREL yola işaret ediyorsa ölçüm güvenilmezdir
        # (npm paketi dinamik import'u erişilebilirliği bozmaz)
        if "<svelte:component" in text:
            dynamic = True
            break
        for spec in re.findall(r"""import\s*\(\s*['"]([^'"]+)['"]""", text):
            if spec.startswith("."):
                dynamic = True
                break
        if dynamic:
            break
    if dynamic:
        return []

    graph = {f: _frontend_imports(f) for f in files}
    entries = [f for f in files if f.name in FRONTEND_ENTRIES]
    reachable: set[pathlib.Path] = set()
    stack = list(entries)
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for nxt in graph.get(cur, ()):
            if nxt not in reachable:
                stack.append(nxt)

    dead = []
    for f in files:
        if f in reachable or f.name in FRONTEND_DECLARATIONS:
            continue
        dead.append(
            {
                "path": rel(f),
                "lines": len(f.read_text(encoding="utf-8", errors="replace").splitlines()),
            }
        )
    return dead


# ── rapor ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    modules, test_only_modules = dead_modules()
    functions = dead_functions()
    agents = dead_agents()
    capabilities, cap_source = dead_capabilities()
    frontend = dead_frontend()

    payload = {
        "dead_modules": modules,
        "test_only_modules": test_only_modules,
        "dead_functions": functions,
        "dead_agents": agents,
        "dead_capabilities": capabilities,
        "dead_frontend": frontend,
        "capability_source": cap_source,
        "totals": {
            "modules": len(modules),
            "test_only_modules": len(test_only_modules),
            "functions": len(functions),
            "agents": len(agents),
            "capabilities": len(capabilities),
            "frontend": len(frontend),
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not any(payload["totals"].values()) else 1

    print("=" * 96)
    print("ÖLÜ KOD DENETİMİ")
    print("=" * 96)
    print(f"\nC1 ÖLÜ MODÜL ({len(modules)})")
    for m in modules:
        print(f"   {m['path']:<58} {m['lines']:>5} satır")
    print(f"\nC1b YALNIZ TESTLERDEN İMPORT EDİLEN MODÜL ({len(test_only_modules)})")
    for m in test_only_modules:
        print(f"   {m['path']:<58} {m['lines']:>5} satır")
    print(f"\nC2 ÖLÜ FONKSİYON ({len(functions)})")
    for f in sorted(functions, key=lambda r: -r["lines"]):
        print(f"   {f['path']}:{f['line']} :: {f['name']} ({f['lines']} satır)")
    print(f"\nC3 KAYITLI AMA ÇAĞRILMAYAN AJAN ({len(agents)})")
    for a in agents:
        print(f"   {a['agent']}")
    print(f"\nC4 KAYITLI AMA DÜŞÜRÜLEMEYEN YETENEK ({len(capabilities)}) — kaynak: {cap_source}")
    for c in capabilities:
        print(f"   {c['capability']:<40} {c['holders'][:2]}")
    print(f"\nC5 ÖLÜ FRONTEND BİLEŞENİ ({len(frontend)})")
    for m in frontend:
        print(f"   {m['path']:<58} {m['lines']:>5} satır")
    print()
    print(
        f"TOPLAM: modül={len(modules)} test-only={len(test_only_modules)} fonksiyon={len(functions)} "
        f"ajan={len(agents)} yetenek={len(capabilities)} frontend={len(frontend)}"
    )
    return 0 if not any(payload["totals"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
