#!/usr/bin/env python3
"""Kapasite ve kullanım açığı denetimi — TEKRAR ÇALIŞTIRILABİLİR sonda.

Bu betik, `docs/reports/KAPASITE_ACIGI_RAPORU.md` raporundaki her sayıyı
KAYNAKTAN yeniden ölçer. Rapor elle yazılmış hiçbir sayı taşımaz; burada
üretilen JSON kanıt dosyası raporun tek dayanağıdır.

Ölçülenler (hepsi gerçek çalıştırma / gerçek dosya okuma):
  1. KAPI ENVANTERİ  — omurga kapıları (policy.MANAGED_GATE_FLAGS), koddan
                        okunan `ENABLE_*` değişkenleri, `.env.example` ile
                        çift yönlü fark (ölü ayar / belgesiz ayar).
  2. YETENEK TABLOSU — kayıtlı her yetenek için iki senaryo:
                        (a) VARSAYILAN: `.env.example` kapıları kapalı,
                        (b) TÜM KAPILAR AÇIK: kapı env'i ``true`` iken
                        hangi bağımlılık sınıfı hâlâ engelliyor.
  3. STEALTH MATRİSİ — STEALTH_PROVIDER = playwright_stealth/invisible/cloak/
                        none/geçersiz seçimlerinin gerçek çözümlemesi.
  4. SAĞLAYICI/YOL   — final_routing_policy.ROUTES tablosu sağlayıcı bazında;
                        hangi sağlayıcı bir yola bağlı, hangisi yalnız ölçüm.
  5. UÇ NOKTALAR     — canlı FastAPI uygulamasından gerçek uç envanteri
                        (yöntem bazında), dokümanlı/dokümansız ayrımı.
  6. ANA AKIŞ BAĞI   — yetenekleri çağıran modüller (AST taraması) ve
                        CognitiveRouter ↔ CapabilityRegistry çapraz referansı.
  7. BAYRAK OKUMA    — `ENABLE_INTERPRETER` gibi ayarların OKUNDUĞU satırlar.

Çıktı: ``reports/kapasite_denetimi.json`` (üzerine yazar, deterministik sıralar).
Kullanım::

    python scripts/kapasite_denetimi_probe.py [--out reports/kapasite_denetimi.json]
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ENV_EXAMPLE = REPO / ".env.example"
ENABLE_RE = re.compile(r"^ENABLE_[A-Z0-9_]+$")


# --------------------------------------------------------------------- 1 · kapılar
def gate_inventory() -> dict:
    from agent_core.capabilities.policy import MANAGED_GATE_FLAGS, PolicyKernel
    from agent_core.capabilities import state as state_mod

    KNOWN_GATE_FLAGS = PolicyKernel.KNOWN_GATE_FLAGS

    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    #: Yorum ve değer kısmını at; yalnız `ENABLE_X=` ile başlayan satırlar.
    example = sorted(
        {m.group(1) for line in env_text.splitlines() if (m := re.match(r"^(ENABLE_[A-Z0-9_]+)=", line.strip()))}
    )
    #: Koddan okunan `ENABLE_*` değişkenleri — ÜRETİM ve TEST ayrı sayılır;
    #: testlerdeki uydurma adlar (yazım hatası senaryoları) üretim sanılmasın.
    read_in_code: set[str] = set()
    test_only: set[str] = set()
    for path in REPO.rglob("*.py"):
        if any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = set(re.findall(r"""["'](ENABLE_[A-Z0-9_]+)["']""", text))
        if path.relative_to(REPO).parts[0] == "tests":
            test_only |= found
        else:
            read_in_code |= found
    test_only -= read_in_code
    return {
        "managed_gate_flags": list(MANAGED_GATE_FLAGS),
        "managed_count": len(MANAGED_GATE_FLAGS),
        "known_gate_flags": sorted(KNOWN_GATE_FLAGS),
        "state_reexports_same_object": (tuple(state_mod.MANAGED_GATE_FLAGS) == tuple(MANAGED_GATE_FLAGS)),
        "env_example_gates": example,
        "env_example_gate_count": len(example),
        "read_in_code": sorted(read_in_code),
        "code_read_count": len(read_in_code),
        "read_in_tests_only": sorted(test_only),
        #: Omurgada yönetilen ama örnekte hiç geçmeyen kapı → operatör göremez.
        "managed_missing_from_example": [g for g in MANAGED_GATE_FLAGS if g not in example],
        #: Örnekte var, omurgada yönetilmiyor → omurga dışı (ikinci geçit).
        "example_gates_not_managed": [g for g in example if g not in MANAGED_GATE_FLAGS],
        #: Kod okur ama örnekte yok → belgesiz ayar.
        "read_but_undocumented": [g for g in sorted(read_in_code) if g not in example],
    }


def interpreter_read_points() -> dict:
    """`ENABLE_INTERPRETER` gerçekten NEREDE okunuyor (satır numaralı)."""
    rows = []
    for path in sorted(REPO.rglob("*.py")):
        if any(part in {".git", "__pycache__", ".venv", "tests"} for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            if "ENABLE_INTERPRETER" in line:
                rows.append(
                    {
                        "file": str(path.relative_to(REPO)),
                        "line": n,
                        "text": line.strip()[:110],
                    }
                )
    return {"read_points": rows, "count": len(rows)}


# --------------------------------------------------------------- 2 · yetenekler
def _gate_env(keys, value: str | None):  # noqa: A002 — bağlam yöneticisi fabrikası
    """Kapı env'ini geçici olarak ayarlayan küçük bağlam yöneticisi."""

    class _Ctx:
        def __init__(self, keys, val):
            self.keys, self.val, self.old = keys, val, {}

        def __enter__(self):
            for k in self.keys:
                self.old[k] = os.environ.get(k)
                if self.val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = self.val
            return self

        def __exit__(self, *exc):
            for k, v in self.old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            return False

    return _Ctx(keys, value)


def capability_table() -> dict:
    from agent_core.capabilities.registry import bootstrap, default_registry
    from agent_core.capabilities.policy import MANAGED_GATE_FLAGS

    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    #: (a) VARSAYILAN senaryo: örnek dosyadaki kapı değerleri birebir uygulanır.
    defaults = dict(re.findall(r"^(ENABLE_[A-Z0-9_]+)=(\S+)", env_text, re.M))
    rows: dict[str, dict] = {"varsayilan": {}, "tum_kapilar_acik": {}}

    keys = list(MANAGED_GATE_FLAGS)
    for label, gate_value in (("varsayilan", None), ("tum_kapilar_acik", "true")):
        with _gate_env(keys, gate_value):
            if gate_value is None:
                for k, v in defaults.items():
                    if k in keys:
                        os.environ[k] = v
            registry = bootstrap(registry=default_registry)
            rows[label] = {
                "registered": len(registry),
                "open": [],
                "closed": [],
            }
            for row in registry.status():
                item = {
                    "id": row["id"],
                    "kind": row["kind"],
                    "license": row["license"],
                    "available": row["available"],
                    "reason": row["reason"],
                    "gates": row["gates"],
                }
                bucket = "open" if row["available"] else "closed"
                rows[label][bucket].append(item)
            rows[label]["open_count"] = len(rows[label]["open"])
            rows[label]["closed_count"] = len(rows[label]["closed"])
    #: Kapalılık SEBEBİ sınıfları (all-gates-open senaryosundan).
    reasons = Counter((r["reason"] or "?").split(":")[0] for r in rows["tum_kapilar_acik"]["closed"])
    rows["kapali_sebep_siniflari"] = dict(sorted(reasons.items()))
    rows["kapali_detay"] = [{"id": r["id"], "reason": r["reason"]} for r in rows["tum_kapilar_acik"]["closed"]]
    return rows


# ------------------------------------------------------------------ 3 · stealth
def stealth_matrix() -> dict:
    from agent_core.services.stealth_provider import resolve_stealth

    out = {}
    for value in [None, "", "playwright_stealth", "invisible", "cloak", "none", "SELENIUM?!"]:
        old = os.environ.get("STEALTH_PROVIDER")
        try:
            if value is None:
                os.environ.pop("STEALTH_PROVIDER", None)
            else:
                os.environ["STEALTH_PROVIDER"] = value
            sel = resolve_stealth()
            out[str(value)] = {
                "selected": sel.provider,
                "available": sel.available,
                "reason": sel.reason,
            }
        except Exception as exc:  # sonda dürüst: patlarsa yazar
            out[str(value)] = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            if old is None:
                os.environ.pop("STEALTH_PROVIDER", None)
            else:
                os.environ["STEALTH_PROVIDER"] = old
    return out


# -------------------------------------------------------------- 4 · sağlayıcılar
def provider_routes() -> dict:
    from agent_core.services import final_routing_policy as pol

    per_provider = Counter(spec.provider for spec in pol.ROUTES.values())
    free = Counter(spec.provider for spec in pol.ROUTES.values() if getattr(spec, "tier", "") == "free")
    return {
        "route_count": len(pol.ROUTES),
        "per_provider": dict(sorted(per_provider.items())),
        "free_per_provider": dict(sorted(free.items())),
        "keys": sorted(pol.ROUTES),
    }


def provider_catalog_gap() -> dict:
    """ROTA taşıyan sağlayıcı ↔ yalnız-tanı sağlayıcı ↔ anahtar bekleyen katalog.

    Üç ayrı gerçek kaynaktan okur (tahmin yok):
      * ``final_routing_policy.ROUTES``  → fiilen yol taşıyan sağlayıcılar,
      * ``_DIAGNOSTIC_ONLY_PROVIDERS``   → taşıyıcısı yok, yalnız tanı ekranında,
      * ``_AGENT_DIRECT_PROVIDER_KEYS``  → anahtarı olsa da rota DOĞMAYAN
        sağlayıcılar (``PINEAL_PROVIDER_MODELS_*`` beyanı beklerler).
    """
    from agent_core.services import final_routing_policy as pol
    from agent_core.services import llm_gateway as gw

    routed = {spec.provider for spec in pol.ROUTES.values()}
    diagnostic = {pid for pid, _ in gw._DIAGNOSTIC_ONLY_PROVIDERS}
    direct = {pid for pid, _ in gw._AGENT_DIRECT_PROVIDER_KEYS}
    return {
        "routed_providers": sorted(routed),
        "diagnostic_only_providers": sorted(diagnostic),
        "direct_catalog_providers": sorted(direct),
        "direct_without_routes": sorted(direct - routed),
        "diagnostic_with_routes": sorted(diagnostic & routed),
        "expected_env_name_rule": "PINEAL_PROVIDER_MODELS_<SAĞLAYICI>",
    }


def gateway_routes_live() -> dict:
    """Canlı ağ geçidi anlık görüntüsü — hangi sağlayıcı HAKİKATEN yolda."""
    from agent_core.services.llm_gateway import LLMGateway

    gw = LLMGateway() if not inspect.signature(LLMGateway).parameters else LLMGateway()
    snap = gw.effective_routing_snapshot()
    return {
        "route_keys": sorted(snap.get("routes") or {}),
        "tier_violations": snap.get("tier_violations"),
        "agents": len(snap.get("agents") or {}),
    }


# -------------------------------------------------------------------- 5 · uçlar
def endpoint_inventory() -> dict:
    from backend import api

    rows = []
    for route in api.app.routes:
        methods = sorted(getattr(route, "methods", []) or [])
        rows.append(
            {
                "path": getattr(route, "path", ""),
                "methods": methods,
                "documented": bool(getattr(route, "include_in_schema", False)),
                "name": getattr(route, "name", ""),
            }
        )
    rows.sort(key=lambda r: (r["path"], ",".join(r["methods"])))
    api_rows = [r for r in rows if r["path"].startswith("/api/")]
    return {
        "total": len(rows),
        "api_total": len(api_rows),
        "documented": sum(1 for r in rows if r["documented"]),
        "undocumented": [r["path"] for r in rows if not r["documented"]][:40],
        "paths": [r["path"] for r in api_rows],
    }


# ------------------------------------------------------------- 6 · ana akış bağı
def call_sites() -> dict:
    """Yetenek sınıflarını çağıran PRODUCTION modülleri (AST, gövdeye iner)."""
    from agent_core.capabilities.registry import bootstrap, default_registry

    registry = bootstrap(registry=default_registry)
    ids = list(registry.ids())
    prod: list[str] = []
    for path in REPO.rglob("*.py"):
        if any(part in {".git", "__pycache__", ".venv", "tests"} for part in path.parts):
            continue
        prod.append(str(path.relative_to(REPO)))
    texts = {}
    for rel in prod:
        try:
            texts[rel] = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    #: Yetenek kimliği metni geçen dosyalar (kayıt yerleri hariç tutulur).
    hits: dict[str, list[str]] = {}
    for cap_id in ids:
        found = [
            rel for rel, text in texts.items() if cap_id in text and not rel.startswith("agent_core/capabilities/")
        ]
        hits[cap_id] = sorted(found)
    return {"capability_ids": ids, "id_to_modules": hits}


def spine_router_link() -> dict:
    """CognitiveRouter ↔ CapabilityRegistry çapraz referans sayısı."""

    def count(needle: str, *, in_dirs: tuple[str, ...]) -> int:
        total = 0
        for path in REPO.rglob("*.py"):
            if any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
                continue
            rel = str(path.relative_to(REPO))
            if in_dirs and not rel.startswith(in_dirs):
                continue
            try:
                total += path.read_text(encoding="utf-8").count(needle)
            except (UnicodeDecodeError, OSError):
                continue
        return total

    return {
        "router_mentions_registry": count("capabilities", in_dirs=("agent_core/capabilities",)),
        "registry_mentions_router": count("CognitiveRouter", in_dirs=("agent_core/capabilities",)),
        "router_files": [
            str(p.relative_to(REPO))
            for p in REPO.rglob("*.py")
            if "CognitiveRouter" in p.read_text(encoding="utf-8", errors="ignore")
        ],
    }


# ------------------------------------------------------------------ 7 · varlık
def repo_stats() -> dict:
    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    py = [p for p in tracked if p.endswith(".py")]
    tests = [p for p in py if p.startswith("tests/") and Path(p).name.startswith("test_")]
    return {
        "tracked_files": len(tracked),
        "py_files": len(py),
        "test_modules": len(tests),
        "head": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="reports/kapasite_denetimi.json")
    args = ap.parse_args()

    evidence = {
        "sema_surumu": 1,
        "olcum": "scripts/kapasite_denetimi_probe.py",
        "python": sys.version.split()[0],
    }
    steps = [
        ("kapilar", gate_inventory),
        ("interpreter_okuma_noktalari", interpreter_read_points),
        ("yetenekler", capability_table),
        ("stealth", stealth_matrix),
        ("saglayicilar", provider_routes),
        ("saglayici_katalog_acigi", provider_catalog_gap),
        ("ag_gecidi", gateway_routes_live),
        ("uclar", endpoint_inventory),
        ("cagri_yerleri", call_sites),
        ("omurga_router_bagi", spine_router_link),
        ("depo", repo_stats),
    ]
    for name, fn in steps:
        try:
            evidence[name] = fn()
            status = "OK"
        except Exception as exc:  # tek adım patlarsa rapor yalan söylemesin
            evidence[name] = {"error": f"{type(exc).__name__}: {exc}"}
            status = f"HATA: {type(exc).__name__}"
        print(f"[{status:>12}] {name}")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"yazıldı: {out} ({out.stat().st_size} bayt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
