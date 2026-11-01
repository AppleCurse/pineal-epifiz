#!/usr/bin/env python3
"""Synthetic LOCAL smoke: report PDF/diagram/video, frame analysis, language detect.

No network, no target data, no credentials. Output is diagnostic evidence only;
it does not open ENABLE_* gates or prove live external capability execution.
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.runtime_env import load_repo_env  # noqa: E402
from agent_core.services import media_forensics as mf  # noqa: E402
from agent_core.services import report_factory as rf  # noqa: E402
from agent_core.services.language import detect_language  # noqa: E402


def main() -> int:
    load_repo_env()
    out = Path(tempfile.mkdtemp(prefix="pineal-local-smoke-", dir=ROOT / "reports/gate_audit"))
    evidence = [{
        "evidence_id": "ev_" + "a" * 20,
        "epistemic_type": "observation",
        "source_engine": "local_smoke_fixture",
        "content": "Sentetik yerel duman testi; canlı hedef verisi değildir.",
        "provenance_refs": ["fixture://local-smoke"],
        "observed_at": "2026-11-01T00:00:00Z",
    }]
    pkg = rf.build_report(evidence, title="Yerel duman testi", formats=("pdf", "diagram", "video"), out_dir=out / "report")
    artifacts = {a.name: {"available": a.available, "reason": a.reason, "path": a.path,
                          "bytes": Path(a.path).stat().st_size if a.path and Path(a.path).exists() else None}
                 for a in pkg.artifacts}
    print("REPORT", json.dumps(artifacts, ensure_ascii=False))
    video = pkg.artifact("video").path
    frames = mf.analyze_frames(video) if video else None
    print("FRAMES", json.dumps(asdict(frames) if frames else None, ensure_ascii=False))
    lang = detect_language("Merhaba dünya, bu yerel bir duman testidir.")
    print("LANGUAGE", lang)
    ok = all(artifacts[name]["available"] for name in ("markdown", "pdf", "diagram", "video"))
    ok = ok and bool(frames and frames.available) and lang.language == "tr"
    result = {"scope": "local_synthetic_smoke_no_network", "decision": "GEÇTİ" if ok else "KALDI",
              "report_dir": str((out / "report").relative_to(ROOT)), "artifacts": artifacts,
              "frames": asdict(frames) if frames else None, "language": lang.model_dump() if hasattr(lang, "model_dump") else asdict(lang)}
    target = ROOT / "reports/gate_audit/local_smoke.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT", json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
