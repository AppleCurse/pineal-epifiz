"""Production container security and runtime-content contract."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _dockerfile_lines():
    assert DOCKERFILE.exists(), f"Dockerfile bulunamadi: {DOCKERFILE}"
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def test_dockerfile_copies_config_directory():
    lines = _dockerfile_lines()
    assert "COPY config/ ./config/" in [line.strip() for line in lines]


def test_dockerfile_defaults_to_fail_closed_production_profile():
    content = "\n".join(_dockerfile_lines())
    assert "PINEAL_ENV=production" in content


def test_dockerfile_healthcheck_uses_public_startup_health_only():
    content = " ".join(line.strip() for line in _dockerfile_lines())
    assert "http://127.0.0.1:8000/health" in content
    assert "/api/telemetry" not in content
    assert "PINEAL_TOKEN" not in next(
        line for line in _dockerfile_lines() if "CMD python -c" in line
    )


# [2026-11-21] İmaj non-root (app, uid 10001) koşar; tarayıcılar dünyaya
# okunur /ms-playwright altındadır. Eskiden kök kullanıcıyla koşuyordu.
def test_dockerfile_runs_as_non_root_user():
    lines = [line.strip() for line in _dockerfile_lines()]
    user_lines = [i for i, line in enumerate(lines) if line == "USER app"]
    assert user_lines, "USER app yönergesi yok — imaj root koşar"
    cmd_idx = next(i for i, line in enumerate(lines) if line.startswith("CMD "))
    assert user_lines[-1] < cmd_idx, "USER app, CMD'den sonra — etkisiz"


def test_dockerfile_browsers_in_shared_path_for_non_root():
    content = "\n".join(_dockerfile_lines())
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in content


def test_dockerfile_has_no_adhoc_websockets_install():
    # websockets artık requirements.lock içinde; ayrı pip satırı iki ağaç
    # yaratırdı (2026-11-21 · #2 düzeltmesi).
    lines = [line.strip() for line in _dockerfile_lines()]
    assert not any(line.startswith("RUN pip install") and "websockets==" in line for line in lines)

