"""Startup dependency classification for production health gates.

Required or explicitly enabled dependencies are imported, not merely located.
This distinguishes an absent package from a package that is installed but fails
while importing because of a broken transitive dependency or runtime error.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class DependencyRequirement:
    name: str
    module: str
    feature_flag: Optional[str] = None
    feature_value: str = "true"

    def enabled(self) -> bool:
        if self.feature_flag is None:
            return True
        if self.feature_flag.startswith("ENABLE_"):
            from agent_core.capabilities.state import flag_enabled
            return flag_enabled(self.feature_flag)
        return os.getenv(self.feature_flag, "").strip().lower() == self.feature_value


class StartupDependencyError(RuntimeError):
    """Machine-readable startup failure for a required dependency."""

    def __init__(self, code: str, dependency: str, cause: BaseException):
        self.error_code = code
        self.dependency = dependency
        self.cause_type = type(cause).__name__
        super().__init__(f"{code}: {dependency} ({self.cause_type})")

    def as_dict(self) -> dict:
        return {
            "status": "failed",
            "error_code": self.error_code,
            "dependency": self.dependency,
            "cause_type": self.cause_type,
        }


REQUIRED_DEPENDENCIES = (
    DependencyRequirement("pydantic", "pydantic"),
    DependencyRequirement("fastapi", "fastapi"),
    DependencyRequirement("httpx", "httpx"),
    DependencyRequirement("numpy", "numpy"),
    DependencyRequirement("opencv", "cv2"),
    DependencyRequirement("openai", "openai"),
    DependencyRequirement("playwright", "playwright.async_api"),
    DependencyRequirement("python-dotenv", "dotenv"),
    DependencyRequirement("PyYAML", "yaml"),
    DependencyRequirement("aiofiles", "aiofiles"),
    DependencyRequirement("task_executor", "agent_core.task_executor"),
    DependencyRequirement("canonical_memory", "agent_core.services.canonical_memory"),
)

# These packages must not be imported when their experimental/configured path
# is disabled. Once enabled, however, they are startup requirements and fail
# closed instead of silently changing product behavior.
CONFIGURED_DEPENDENCIES = (
    DependencyRequirement("sentence-transformers", "sentence_transformers", "PINEAL_MEMORY_ENGINE", "hindsight"),
    DependencyRequirement("open-interpreter", "interpreter", "ENABLE_INTERPRETER"),
    DependencyRequirement("maigret", "maigret", "ENABLE_MAIGRET"),
    DependencyRequirement("holehe", "holehe", "ENABLE_HOLEHE"),
    DependencyRequirement("crawl4ai", "crawl4ai", "ENABLE_CRAWL4AI"),
    DependencyRequirement("yt-dlp", "yt_dlp", "ENABLE_MEDIA_FORENSICS"),
)


def _classify_import_failure(requirement: DependencyRequirement, exc: BaseException) -> StartupDependencyError:
    if isinstance(exc, ModuleNotFoundError):
        code = "REQUIRED_DEPENDENCY_MISSING"
    else:
        code = "REQUIRED_DEPENDENCY_BROKEN"
    return StartupDependencyError(code, requirement.name, exc)


def check_startup_dependencies(
    *,
    importer: Callable[[str], object] = importlib.import_module,
    required: Iterable[DependencyRequirement] = REQUIRED_DEPENDENCIES,
    configured: Iterable[DependencyRequirement] = CONFIGURED_DEPENDENCIES,
) -> dict:
    """Import all active dependencies or raise a classified startup error."""
    statuses = []
    for requirement in (*tuple(required), *tuple(configured)):
        if not requirement.enabled():
            statuses.append({
                "dependency": requirement.name,
                "status": "disabled",
                "feature_flag": requirement.feature_flag,
            })
            continue
        try:
            importer(requirement.module)
        except Exception as exc:
            raise _classify_import_failure(requirement, exc) from exc
        statuses.append({
            "dependency": requirement.name,
            "status": "ready",
            "feature_flag": requirement.feature_flag,
        })
    return {"status": "ready", "error_code": None, "dependencies": statuses}
