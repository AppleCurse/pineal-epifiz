import sys
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from agent_core.services.dependency_health import (
    DependencyRequirement,
    StartupDependencyError,
    check_startup_dependencies,
)
from agent_core.services.hindsight_memory import HindsightMemory
from backend.api import app


def test_required_missing_dependency_has_machine_readable_startup_failure():
    requirement = DependencyRequirement("required-example", "required_example")

    def missing(_module):
        raise ModuleNotFoundError("not installed", name="required_example")

    with pytest.raises(StartupDependencyError) as raised:
        check_startup_dependencies(importer=missing, required=(requirement,), configured=())

    assert raised.value.as_dict() == {
        "status": "failed",
        "error_code": "REQUIRED_DEPENDENCY_MISSING",
        "dependency": "required-example",
        "cause_type": "ModuleNotFoundError",
    }


@pytest.mark.parametrize("failure", [ImportError("binary ABI mismatch"), RuntimeError("module init exploded")])
def test_installed_but_broken_dependency_is_not_classified_as_missing(failure):
    requirement = DependencyRequirement("required-example", "required_example")

    def broken(_module):
        raise failure

    with pytest.raises(StartupDependencyError) as raised:
        check_startup_dependencies(importer=broken, required=(requirement,), configured=())

    assert raised.value.error_code == "REQUIRED_DEPENDENCY_BROKEN"
    assert raised.value.dependency == "required-example"
    assert raised.value.cause_type == type(failure).__name__


def test_disabled_experimental_dependency_is_not_imported(monkeypatch):
    monkeypatch.delenv("ENABLE_EXAMPLE", raising=False)
    optional = DependencyRequirement(
        "experimental-example",
        "experimental_example",
        "ENABLE_EXAMPLE",
    )
    imported = []

    result = check_startup_dependencies(
        importer=lambda module: imported.append(module),
        required=(),
        configured=(optional,),
    )

    assert imported == []
    assert result["dependencies"] == [{
        "dependency": "experimental-example",
        "status": "disabled",
        "feature_flag": "ENABLE_EXAMPLE",
    }]


def test_enabled_experimental_dependency_becomes_startup_requirement(monkeypatch):
    monkeypatch.setenv("ENABLE_EXAMPLE", "true")
    optional = DependencyRequirement(
        "experimental-example",
        "experimental_example",
        "ENABLE_EXAMPLE",
    )

    def broken(_module):
        raise ImportError("installed package is broken")

    with pytest.raises(StartupDependencyError) as raised:
        check_startup_dependencies(importer=broken, required=(), configured=(optional,))

    assert raised.value.error_code == "REQUIRED_DEPENDENCY_BROKEN"


def test_lifespan_fails_closed_and_retains_machine_failure(monkeypatch):
    failure = StartupDependencyError(
        "REQUIRED_DEPENDENCY_BROKEN",
        "required-example",
        RuntimeError("module init exploded"),
    )

    def fail_health_check():
        raise failure

    monkeypatch.setattr("backend.api.check_startup_dependencies", fail_health_check)

    with pytest.raises(StartupDependencyError) as raised:
        with TestClient(app):
            pass

    assert raised.value is failure
    assert app.state.startup_health == failure.as_dict()


def test_public_health_endpoint_reports_successful_startup(monkeypatch):
    for flag in ("ENABLE_INTERPRETER", "ENABLE_MAIGRET", "ENABLE_HOLEHE", "ENABLE_CRAWL4AI"):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.delenv("PINEAL_MEMORY_ENGINE", raising=False)

    # [2026-11-11] Tarayıcı ikilisi yokken /health artık DÜRÜSTÇE `degraded`
    # der (browser_binary_missing). Bu testin konusu BAĞIMLILIK sağlığı;
    # tarayıcı ölçümü sabitlenir, ayrı testte gerçek ölçümle sınanır:
    # tests/unit/test_browser_infrastructure_gate.py.
    import backend.api as api_module
    from backend.services.browser_capability import BrowserBinaryStatus

    monkeypatch.setattr(
        api_module,
        "browser_binary_status",
        lambda: BrowserBinaryStatus(
            available=True, source="test", path="/usr/bin/chromium", reason=None
        ),
    )

    with TestClient(app) as client:
        response = client.get("/api/health/detail")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["error_code"] is None
    assert any(
        dependency["dependency"] == "task_executor" and dependency["status"] == "ready"
        for dependency in response.json()["dependencies"]
    )


def test_hindsight_missing_library_is_explicit(monkeypatch, tmp_path):
    memory = HindsightMemory(str(tmp_path), db_path=str(tmp_path / "h.db"))
    monkeypatch.setattr("agent_core.services.hindsight_memory.ST_AVAILABLE", False)

    assert memory._get_embedder() is None
    assert memory._embedder_error == {
        "error_code": "OPTIONAL_DEPENDENCY_MISSING",
        "dependency": "sentence-transformers",
    }


def test_hindsight_installed_library_import_crash_propagates(monkeypatch, tmp_path):
    memory = HindsightMemory(str(tmp_path), db_path=str(tmp_path / "h.db"))
    monkeypatch.setattr("agent_core.services.hindsight_memory.ST_AVAILABLE", True)
    broken_module = ModuleType("sentence_transformers")

    def missing_attribute(_name):
        raise ImportError("installed sentence-transformers is broken")

    broken_module.__getattr__ = missing_attribute
    monkeypatch.setitem(sys.modules, "sentence_transformers", broken_module)

    with pytest.raises(ImportError, match="is broken"):
        memory._get_embedder()


def test_hindsight_model_load_failure_has_distinct_reason(monkeypatch, tmp_path):
    memory = HindsightMemory(str(tmp_path), db_path=str(tmp_path / "h.db"))
    monkeypatch.setattr("agent_core.services.hindsight_memory.ST_AVAILABLE", True)
    module = ModuleType("sentence_transformers")

    class BrokenModel:
        def __init__(self, _name):
            raise RuntimeError("model files are corrupt")

    module.SentenceTransformer = BrokenModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    assert memory._get_embedder() is None
    assert memory._embedder_error == {
        "error_code": "EMBEDDING_MODEL_LOAD_FAILED",
        "dependency": "sentence-transformers",
        "cause_type": "RuntimeError",
    }
