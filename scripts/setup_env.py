#!/usr/bin/env python3
"""Create/replay the isolated runtime; never use --user or mutate system Python.

    python scripts/setup_env.py [--dev] [--browser]

Core lock first, then retina lock (its newer transitive pins intentionally win),
then dev lock. Browser binaries are explicit because they are a large download.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    print("$ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    env = ROOT / ".venv"
    if not (env / "bin/python").exists():
        venv.EnvBuilder(with_pip=True).create(env)
    python = str(env / "bin/python")
    run([python, "-m", "pip", "install", "-r", "requirements.lock"])
    run([python, "-m", "pip", "install", "-r", "requirements-retina.lock"])
    if args.dev:
        run([python, "-m", "pip", "install", "-r", "requirements-dev.lock"])
    run([python, "-m", "pip", "check"])
    if args.browser:
        run([python, "-m", "playwright", "install", "chromium"])
    print(f"GEÇTİ: izole ortam {env}; sistem Python değiştirilmedi.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"KALDI: exit={exc.returncode}; komut={exc.cmd}", file=sys.stderr)
        raise SystemExit(exc.returncode)
