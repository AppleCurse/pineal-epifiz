#!/usr/bin/env python3
"""Evidence-separated audit of all 17 managed gates. No credentials are printed.

Default: local package/CLI/configuration/policy/preflight checks only.
--run-tests: execute mapped repository tests (fixtures are NOT live evidence).
--probe-services: explicitly GET configured local service endpoints (no target scan).
No target scan, account creation, credential synthesis or paid live call occurs.
Exit 0 means the audit ran, NOT that every gate is operational.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.runtime_env import load_repo_env  # noqa: E402
from agent_core.capabilities.policy import MANAGED_GATE_FLAGS  # noqa: E402

# Gate -> registered capability IDs. Interpreter is an agent, not a registry cap.
CAPABILITIES = {
    "ENABLE_MAIGRET": ["sensor.identity.maigret"],
    "ENABLE_CROSS_PLATFORM": ["sensor.identity.handle_probe"],
    "ENABLE_HOLEHE": ["sensor.identity.holehe"],
    "ENABLE_CRAWL4AI": ["extractor.web.crawl4ai"],
    "ENABLE_SCRAPLING": ["extractor.web.scrapling"],
    "ENABLE_X_SENSOR": ["sensor.x.twscrape"],
    "ENABLE_IG_SECONDARY": ["sensor.ig.instagrapi"],
    "ENABLE_AGENT_REACH": ["sensor.web.agent_reach"],
    "ENABLE_SEARXNG": ["sensor.search.searxng"],
    "ENABLE_LOCAL_TRANSLATE": ["extractor.text.translate_local"],
    "ENABLE_LOCAL_JURY": ["verifier.jury.local"],
    "ENABLE_COMPANY_TARGETING": ["sensor.company.harvester", "sensor.company.seo", "sensor.company.people"],
    "ENABLE_REPORT_FACTORY": ["renderer.report.pdf", "renderer.report.diagram", "renderer.report.video"],
    "ENABLE_INTERPRETER": [],
    "ENABLE_MEDIA_FORENSICS": ["sensor.media.fetch", "analyzer.media.frames", "extractor.media.transcript", "analyzer.media.similarity"],
    "ENABLE_LOCAL_TTS": ["voice.tts.local"],
    "ENABLE_LOCAL_STT": ["voice.stt.local"],
}
PACKAGES = {
    "ENABLE_MAIGRET": [("maigret", "maigret")],
    "ENABLE_HOLEHE": [("holehe", "holehe")],
    "ENABLE_CRAWL4AI": [("crawl4ai", "crawl4ai")],
    "ENABLE_SCRAPLING": [("scrapling", "scrapling"), ("browserforge", "browserforge")],
    "ENABLE_X_SENSOR": [("twscrape", "twscrape")],
    "ENABLE_IG_SECONDARY": [("instagrapi", "instagrapi")],
    "ENABLE_REPORT_FACTORY": [("reportlab", "reportlab"), ("PIL", "Pillow")],
    "ENABLE_MEDIA_FORENSICS": [("cv2", "opencv-python-headless"), ("yt_dlp", "yt-dlp")],
    "ENABLE_INTERPRETER": [("interpreter", "open-interpreter")],
}
COMMANDS = {
    "ENABLE_AGENT_REACH": ("PINEAL_AGENT_REACH_CMD", "agent-reach"),
    "ENABLE_LOCAL_TRANSLATE": ("PINEAL_TRANSLATE_CMD", "trans"),
    "ENABLE_COMPANY_TARGETING": ("PINEAL_HARVESTER_CMD", "theHarvester"),
    "ENABLE_LOCAL_TTS": ("", "piper"),
    "ENABLE_LOCAL_STT": ("PINEAL_STT_CMD", "whisper"),
    "ENABLE_REPORT_FACTORY": ("", "ffmpeg"),
    "ENABLE_MEDIA_FORENSICS": ("", "ffmpeg"),
}
IDENTITY_ENV = {
    "ENABLE_LOCAL_TTS": ("PINEAL_PIPER_MODEL",),
    "ENABLE_LOCAL_JURY": ("PINEAL_JURY_LOCAL_MODELS", "LOCAL_LLM_MODEL"),
    "ENABLE_IG_SECONDARY": ("IG_USERNAME", "IG_PASSWORD", "IG_SESSIONID"),
}
TESTS = {
    "ENABLE_MAIGRET": ["test_capability_spine_faz0.py"],
    "ENABLE_CROSS_PLATFORM": ["test_consent_gate_wiring.py"],
    "ENABLE_HOLEHE": ["test_capability_spine_faz0.py"],
    "ENABLE_CRAWL4AI": ["test_retina_faz_a.py"],
    "ENABLE_SCRAPLING": ["test_retina_faz_a.py"],
    "ENABLE_X_SENSOR": ["test_p0_honest_status.py", "test_capability_preflight.py"],
    "ENABLE_IG_SECONDARY": ["test_consent_gate_wiring.py"],
    "ENABLE_AGENT_REACH": ["test_retina_faz_a.py"],
    "ENABLE_SEARXNG": ["test_retina_faz_a.py"],
    "ENABLE_LOCAL_TRANSLATE": ["test_language_capabilities.py"],
    "ENABLE_LOCAL_JURY": ["test_local_jury_capability.py"],
    "ENABLE_COMPANY_TARGETING": ["test_company_capabilities.py"],
    "ENABLE_REPORT_FACTORY": ["test_report_factory.py"],
    "ENABLE_INTERPRETER": ["test_p1_6_interpreter_registry.py"],
    "ENABLE_MEDIA_FORENSICS": ["test_media_forensics.py"],
    "ENABLE_LOCAL_TTS": ["test_speech_report_faz_c.py"],
    "ENABLE_LOCAL_STT": ["test_speech_report_faz_c.py"],
}


def execute(command: list[str], log: Path) -> dict:
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(output, encoding="utf-8")
        print(f"$ {shlex.join(command)}\n{output}exit=124", flush=True)
        return {"command": command, "exit_code": 124, "status": "YAPILAMADI", "decision": "YAPILAMADI",
                "output_log": str(log.relative_to(ROOT)), "output": output}
    output = proc.stdout + proc.stderr
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(output, encoding="utf-8")
    print(f"$ {shlex.join(command)}\n{output}exit={proc.returncode}", flush=True)
    return {"command": command, "exit_code": proc.returncode, "status": "GEÇTİ" if proc.returncode == 0 else "KALDI",
            "decision": "GEÇTİ" if proc.returncode == 0 else "KALDI",
            "output_log": str(log.relative_to(ROOT)), "output": output}


def package_probe(module: str, distribution: str, log: Path) -> dict:
    code = ("import importlib,importlib.metadata,json; "
            f"m=importlib.import_module({module!r}); "
            f"print(json.dumps({{'module':m.__name__,'file':getattr(m,'__file__',None),"
            f"'distribution':{distribution!r},'version':importlib.metadata.version({distribution!r})}}))")
    result = execute([sys.executable, "-c", code], log)
    if result["exit_code"] == 0:
        result["measurement"] = json.loads(result["output"].strip().splitlines()[-1])
    return result


SERVICE_ENV = {
    "ENABLE_SEARXNG": ("SEARXNG_BASE_URL", "/healthz"),
    "ENABLE_LOCAL_TRANSLATE": ("PINEAL_TRANSLATE_URL", ""),
    "ENABLE_LOCAL_TTS": ("PINEAL_TTS_URL", ""),
    "ENABLE_LOCAL_STT": ("PINEAL_STT_URL", ""),
    "ENABLE_MEDIA_FORENSICS": ("PINEAL_TRANSCRIBE_URL", ""),
}


async def service_probe(name: str) -> dict:
    """GET a configured local endpoint; this is NOT a capability execution."""
    from agent_core.capabilities.egress import open_client

    if name == "ENABLE_LOCAL_JURY":
        from agent_core.services.local_jury import local_endpoint
        base, reason = local_endpoint()
        if not base:
            return {"status": "YAPILAMADI", "reason": reason or "service_not_configured", "live_execution_verified": False}
        url = base.rstrip("/") + "/models"
    else:
        env_name, path = SERVICE_ENV[name]
        base = os.getenv(env_name, "").strip().rstrip("/")
        if not base:
            return {"status": "YAPILAMADI", "reason": "service_not_configured", "live_execution_verified": False}
        url = base + path
    try:
        async with open_client(purpose="probe", target=url, timeout=5, trust_env=False, follow_redirects=False) as client:
            response = await client.get(url)
        # A 405/404 still proves only that something answered, not that the
        # capability works. Keep the HTTP status visible and never call this
        # live execution verification.
        if response.status_code == 200:
            status, reason = "GEÇTİ", ""
        elif response.status_code in {404, 405}:
            status, reason = "YAPILAMADI", f"endpoint_answered_http_{response.status_code}_contract_not_verified"
        else:
            status, reason = "KALDI", f"http_status:{response.status_code}"
        return {"status": status, "reason": reason,
                "http_status": response.status_code, "method": "GET",
                "scope": "service_endpoint_get_only", "live_execution_verified": False}
    except Exception as exc:
        return {"status": "YAPILAMADI", "reason": type(exc).__name__, "live_execution_verified": False}


async def tool_probes(gate: str) -> dict:
    if gate == "ENABLE_MEDIA_FORENSICS":
        from agent_core.services import media_forensics as mf
        from agent_core.utils.optional_deps import module_available
        ytdlp = await mf.probe_ytdlp()
        ffmpeg = mf.ffmpeg_command()
        return {
            "yt-dlp": ytdlp,
            "ffmpeg": {"available": bool(ffmpeg), "command": ffmpeg, "reason": "" if ffmpeg else "dependency_missing:ffmpeg"},
            "opencv": {"available": module_available("cv2"), "reason": "" if module_available("cv2") else "dependency_missing:opencv"},
            "transcribe_engine": mf.resolve_engine(),
        }
    return {}


async def audit(args) -> dict:
    from agent_core.capabilities import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.capabilities.state import enabled_flags, policy_state
    from backend.api import _check_vault_interlock

    load_repo_env()
    registry = bootstrap()
    vault_open = _check_vault_interlock(args.client_id)
    state = policy_state(vault_locked=not vault_open, rate_ok=None)
    runner = CapabilityRunner(registry=registry)
    flags = enabled_flags()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / args.output / stamp
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    test_cache: dict[tuple[str, ...], dict] = {}
    for gate in MANAGED_GATE_FLAGS:
        row = {"gate": gate, "flag": flags[gate], "capabilities": CAPABILITIES[gate],
               "vault_open": vault_open, "rate_ok": None,
               "packages": [], "cli": {"status": "NOT_REQUIRED"},
               "identity": {key: bool(os.getenv(key, "").strip()) for key in IDENTITY_ENV.get(gate, ())},
               "service": {"status": "YAPILAMADI", "reason": "not_probed"},
               "preflight": [], "local_diagnostics": [], "repository_test": {"status": "YAPILAMADI", "reason": "not_requested"},
               "live_execution_verified": False}
        for module, distribution in PACKAGES.get(gate, ()):
            row["packages"].append(package_probe(module, distribution, output / f"{gate}-{distribution}.log"))
        endpoint_alternative = {
            "ENABLE_LOCAL_TRANSLATE": "PINEAL_TRANSLATE_URL",
            "ENABLE_LOCAL_TTS": "PINEAL_TTS_URL",
            "ENABLE_LOCAL_STT": "PINEAL_STT_URL",
        }.get(gate)
        if gate in COMMANDS and endpoint_alternative and os.getenv(endpoint_alternative, "").strip():
            row["cli"] = {"status": "NOT_REQUIRED", "reason": f"local_endpoint_configured:{endpoint_alternative}"}
        elif gate in COMMANDS:
            env_name, default = COMMANDS[gate]
            configured = os.getenv(env_name, "").strip() if env_name else ""
            executable = shlex.split(configured)[0] if configured else shutil.which(default)
            if not executable and default == "ffmpeg":
                from agent_core.services.media_forensics import ffmpeg_command
                executable = ffmpeg_command()
            if not executable or not shutil.which(executable):
                row["cli"] = {"status": "KALDI", "reason": f"command_not_found:{default}", "configured": bool(configured)}
            else:
                row["cli"] = execute([executable, "-version" if default == "ffmpeg" else "--version"], output / f"{gate}-cli.log")
        for cap_id in row["capabilities"]:
            result = await runner.preflight(cap_id, state=state)
            row["preflight"].append(result.to_dict())
        # Read-only local diagnostics are reported even when policy denies
        # execution. They never call run() and never authorize an external scan.
        for cap_id in row["capabilities"]:
            cap = registry.get(cap_id)
            local = cap.availability()
            diagnostic = {"capability_id": cap_id, "local_available": local.available, "local_reason": local.reason}
            if getattr(cap, "requires_preflight", False):
                try:
                    session = await asyncio.wait_for(cap.preflight(), timeout=10.0)
                    diagnostic["local_preflight"] = {"available": session.available, "reason": session.reason}
                    if not session.available and session.reason not in {None, "", f"gate_disabled:{gate}"}:
                        diagnostic["blocker"] = session.reason or "preflight_failed"
                except asyncio.TimeoutError:
                    diagnostic["local_preflight"] = {"available": False, "reason": "preflight_timeout"}
                    diagnostic["blocker"] = "preflight_timeout"
                except Exception as exc:
                    diagnostic["local_preflight"] = {"available": False, "reason": f"preflight_error:{type(exc).__name__}"}
                    diagnostic["blocker"] = f"preflight_error:{type(exc).__name__}"
            row["local_diagnostics"].append(diagnostic)
        blockers: list[str] = []
        row["tools"] = await tool_probes(gate)
        for tool_name, probe in row["tools"].items():
            if isinstance(probe, dict) and probe.get("available") is False:
                blockers.append(probe.get("reason") or f"tool_unavailable:{tool_name}")
        if args.probe_services and (gate in SERVICE_ENV or gate == "ENABLE_LOCAL_JURY"):
            row["service"] = await service_probe(gate)
        elif gate in SERVICE_ENV or gate == "ENABLE_LOCAL_JURY":
            row["service"] = {"status": "YAPILAMADI", "reason": "not_requested", "live_execution_verified": False}
        else:
            row["service"] = {"status": "YAPILAMADI", "reason": "live_target_not_probed", "live_execution_verified": False}
        if args.run_tests:
            files = tuple(TESTS[gate])
            missing = [name for name in files if not (ROOT / "tests/unit" / name).is_file()]
            if missing:
                row["repository_test"] = {"status": "YAPILAMADI", "reason": f"test_file_missing:{missing}"}
            else:
                if files not in test_cache:
                    test_cache[files] = execute([sys.executable, "-m", "pytest", *[f"tests/unit/{name}" for name in files],
                                                 "-q", "--timeout=60", "-p", "no:cacheprovider"], output / f"{gate}-tests.log")
                row["repository_test"] = {**test_cache[files], "scope": "repository_tests_may_use_fixtures"}
        blockers.extend(d["blocker"] for d in row["local_diagnostics"] if "blocker" in d)
        if not row["flag"]: blockers.append("gate_disabled")
        if not vault_open: blockers.append("vault_locked")
        if not row["capabilities"]: blockers.append("no_registered_capability")
        blockers.extend(p.get("unavailable_reason") or "preflight_failed" for p in row["preflight"] if not p["available"])
        blockers.extend("package:" + p["measurement"]["distribution"] if "measurement" in p else "package_probe_failed" for p in row["packages"] if p["exit_code"] != 0)
        if row["cli"]["status"] == "KALDI": blockers.append(row["cli"].get("reason") or f"cli_exit:{row['cli'].get('exit_code')}")
        identity_values = dict(row["identity"])
        if gate == "ENABLE_LOCAL_TTS" and os.getenv("PINEAL_TTS_URL", "").strip():
            identity_values.pop("PINEAL_PIPER_MODEL", None)
        if gate == "ENABLE_IG_SECONDARY":
            has_session = identity_values.pop("IG_SESSIONID", False)
            has_creds = identity_values.get("IG_USERNAME") and identity_values.get("IG_PASSWORD")
            if not (has_session or has_creds): blockers.append("identity_or_model_config_missing")
        elif gate == "ENABLE_LOCAL_JURY":
            if not any(identity_values.values()): blockers.append("identity_or_model_config_missing")
        elif any(not value for value in identity_values.values()): blockers.append("identity_or_model_config_missing")
        row["blockers"] = list(dict.fromkeys(blockers))
        verification = []
        if row["repository_test"].get("status", row["repository_test"].get("decision")) != "GEÇTİ":
            verification.append("repository_test_not_passed")
        if (gate in SERVICE_ENV or gate == "ENABLE_LOCAL_JURY") and row["service"]["status"] != "GEÇTİ":
            verification.append("service_endpoint_not_verified")
        if gate not in SERVICE_ENV and gate not in {"ENABLE_LOCAL_JURY", "ENABLE_REPORT_FACTORY", "ENABLE_INTERPRETER"}:
            verification.append("live_target_not_verified")
        if gate == "ENABLE_MEDIA_FORENSICS":
            verification.append("live_platform_download_not_verified")
        row["verification_gaps"] = verification
        row["decision"] = "YAPILAMADI" if blockers or verification else "GEÇTİ (yerel ön koşullar; canlı hedef testi değil)"
        rows.append(row)
    report = {"schema": 1, "created_at": stamp, "python": sys.executable,
              "gate_count": len(rows), "scope": "local_prerequisites_and_repository_tests",
              "live_execution_verified": False, "gates": rows,
              "summary": {"blocked_or_unverified": sum(bool(row["blockers"] or row["verification_gaps"]) for row in rows),
                          "local_prerequisites_passed": sum(not row["blockers"] and not row["verification_gaps"] for row in rows)}}
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 17 kapı denetimi", "", f"Python: `{sys.executable}`", "",
             "Bayrak/paket/import/preflight/test/canlı yürütme ayrı kanıtlardır. Kasa ve oran sınırı aşılmadı.",
             "Bilinmeyen oran sınırı `null` olarak kalır; sıfır veya uygun kabul edilmez.", "",
             "| Kapı | Bayrak | Paket | CLI | Servis | Kimlik | Depo testi | Karar | Engel / doğrulama boşluğu |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        pkg = "GEÇTİ" if row["packages"] and all(p["exit_code"] == 0 for p in row["packages"]) else ("KALDI" if row["packages"] else "—")
        cli = row["cli"].get("status", "—")
        service = row["service"].get("status", "—")
        if row["gate"] == "ENABLE_IG_SECONDARY":
            ident = row["identity"]
            identity_ok = ident.get("IG_SESSIONID") or (ident.get("IG_USERNAME") and ident.get("IG_PASSWORD"))
        elif row["gate"] == "ENABLE_LOCAL_JURY":
            identity_ok = any(row["identity"].values())
        elif row["gate"] == "ENABLE_LOCAL_TTS" and os.getenv("PINEAL_TTS_URL", "").strip():
            identity_ok = True
        else:
            identity_ok = all(row["identity"].values())
        identity = "GEÇTİ" if row["identity"] and identity_ok else ("KALDI" if row["identity"] else "—")
        test = row["repository_test"].get("status", row["repository_test"].get("decision", "—"))
        gaps = ", ".join(row["blockers"] + row["verification_gaps"]) or "—"
        lines.append(f"| {row['gate']} | {row['flag']} | {pkg} | {cli} | {service} | {identity} | {test} | {row['decision']} | {gaps} |")
    lines += ["", "Ham komutlar, çıkış kodları ve tam çıktılar `audit.json` ve yanındaki log dosyalarındadır.",
              "Depo testleri fixture içerebilir; canlı servis/hedef başarısı kanıtlamaz."]
    (output / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)
    print(f"Report: {output / 'audit.md'}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--probe-services", action="store_true")
    parser.add_argument("--client-id", default="default")
    parser.add_argument("--output", default="reports/gate_audit")
    args = parser.parse_args()
    if Path(args.output).is_absolute() or ".." in Path(args.output).parts:
        parser.error("--output must be a relative directory inside the repository")
    result = asyncio.run(audit(args))
    return 0 if result["gate_count"] == 17 else 1


if __name__ == "__main__":
    raise SystemExit(main())
