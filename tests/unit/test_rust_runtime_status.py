"""Phase 9 decision B: Rust is CI-validated, not product-integrated."""

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from agent_core.services.runtime_status import rust_core_status
from backend.api import app


ROOT = Path(__file__).resolve().parents[2]


def test_rust_status_is_unambiguous_and_defensively_copied():
    expected = {
        "classification": "experimental_optional",
        "product_runtime_integrated": False,
        "product_decision_effect": False,
        "packaged_in_python_runtime": False,
        "activation_flag": None,
        "validation": "ci_cargo_check_and_test",
    }
    first = rust_core_status()
    assert first == expected
    first["product_runtime_integrated"] = True
    assert rust_core_status() == expected


def test_health_and_telemetry_expose_non_integrated_status():
    with TestClient(app) as client:
        health = client.get("/health")
        telemetry = client.get("/api/telemetry", params={"client_id": "rust_status"})

    assert health.status_code == 200
    assert health.json()["components"]["rust_core"] == rust_core_status()
    assert telemetry.status_code == 200
    assert telemetry.json()["rust_core"] == rust_core_status()


def test_python_product_path_has_no_rust_import_or_invocation():
    product_sources = [
        *ROOT.joinpath("agent_core").rglob("*.py"),
        *ROOT.joinpath("backend").rglob("*.py"),
        *ROOT.joinpath("scripts").rglob("*.py"),
        ROOT / "main.py",
        ROOT / "scraper.py",
    ]
    allowed_status_surfaces = {
        ROOT / "agent_core/services/runtime_status.py",
        ROOT / "backend/api.py",
        # [API-BÖLME 3 · 2026-10-16] `/api/telemetry` ucu ayrı modüle
        # taşındı (`backend/routes/telemetry.py`); uç yanıtı `rust_core`
        # durumunu AYNEN aktarır. Bu bir "durum yüzeyi"dir, çağrı değil:
        # modül rust çekirdeğini İÇE AKTARMAZ, çağırmaz — değer
        # `backend/api.py`'den ENJEKTE edilir. AST kapıları (import/invoke
        # yasağı) bu dosya için DEĞİŞMEDEN çalışır.
        ROOT / "backend/routes/telemetry.py",
        # [DENETİM] Gölge denetim betiği depodaki gömülü varlıkları (rust_core vb.) sayar.
        ROOT / "scripts/golge_denetimi.py",
    }

    for path in product_sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
                assert not any(
                    name == "rust_core" or name.startswith("rust_core.")
                    for name in imported
                ), path
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not (
                    module == "rust_core" or module.startswith("rust_core.")
                ), path
        if path not in allowed_status_surfaces:
            assert "rust_core" not in path.read_text(encoding="utf-8"), path


def test_rust_is_not_packaged_in_python_container_or_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.glob("requirements*.txt")
    ).lower()

    assert "copy rust_core" not in dockerfile.lower()
    assert "maturin" not in requirements
    assert "pyo3" not in requirements


def test_rust_compile_and_test_remain_ci_gates():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "cargo check" in workflow
    assert "cargo test" in workflow
    assert "continue-on-error" not in workflow
