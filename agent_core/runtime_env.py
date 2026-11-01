"""Explicit, repository-root .env loading shared by process entry points.

Never overrides an explicitly supplied environment variable and never copies
.env.example over an operator's configuration. Importing this module has no
filesystem or environment side effects.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_repo_env() -> bool:
    from dotenv import load_dotenv

    return bool(load_dotenv(ROOT / ".env", override=False))
