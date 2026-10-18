"""[P3 · DENETİM 2026-10-16] Lilith — CLI-only kararı ve ana hat kapıları.

Denetim maddesi 12: Lilith'in "kopuk ada" olup olmadığı ve README_TECHNICAL.md'deki
"ham profil metni prompt'a eklenmez" ifadesinin koda uyup uymadığı.

Bu dosya üç şeyi kilitler:
    1. **Karar:** Lilith CLI-only'dir — ana görev hattından çağrılmaz.
    2. **Kapılar:** Lilith CLI, ana hattın `LLMGateway`'ini kullanır
       (NINEROUTER_*/canlı kapı/bütçe sayacı) — M-2 düzeltmesi.
    3. **Doküman = kod:** README_TECHNICAL.md'nin Lilith maddesi kodla çelişmez.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────────────
# 1. KARAR: CLI-ONLY
# ─────────────────────────────────────────────────────────────────────────────
def test_lilith_cli_is_not_called_from_the_main_line():
    """Ana hat Lilith'i çağırmaz (CLI-only kararının kod karşılığı).

    Tarama **AST** ile yapılır: yalnız gerçek `import run_lilith` /
    `from run_lilith import ...` ifadeleri sayılır. Yorumlarda geçen metin
    (ör. "`run_lilith.py` bu adaptörleri seçer") çağrı DEĞİLDİR.
    """
    import ast

    offenders: list[str] = []
    for folder in ("agent_core", "backend", "scripts"):
        for path in (REPO_ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] == "run_lilith":
                            offenders.append(str(path.relative_to(REPO_ROOT)))
                elif isinstance(node, ast.ImportFrom):
                    module = (node.module or "").split(".")[0]
                    if module == "run_lilith":
                        offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"ana hattan Lilith çağrısı var: {offenders}"


def test_lilith_agent_is_not_in_the_executor_chain():
    """Görev yürütücüsü Lilith ajanını çalıştırmaz."""
    source = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    assert "lilith_growth" not in source
    assert "LilithGrowthAgent" not in source


def test_readme_states_the_cli_only_decision():
    """README kararı AÇIKÇA yazar (P3 teslim şartı)."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "CLI-only" in readme
    assert "run_lilith.py" in readme
    # Yanlış yol (dosya depo kökündedir, scripts/ altında DEĞİL) yazılmamalı.
    assert "scripts/run_lilith.py" not in readme


# ─────────────────────────────────────────────────────────────────────────────
# 2. KAPILAR: ana hattın gateway'i (M-2)
# ─────────────────────────────────────────────────────────────────────────────
def test_cli_uses_the_main_line_gateway_when_a_key_exists():
    """Anahtar varsa Lilith, ana hattın LLMGateway'ini kullanır."""
    from agent_core.agents.lilith_growth import LilithGrowthAgent
    from agent_core.services.llm_gateway import LLMGateway

    agent = LilithGrowthAgent.from_cli_credentials(
        api_key="sk-test", base_url=None, model="gpt-4o"
    )
    assert isinstance(agent.llm_gateway, LLMGateway)


def test_cli_without_a_key_uses_the_free_gateway():
    """Anahtar yoksa canlı ücretli çağrı YAPILMAZ (sıfır-maliyet gateway)."""
    from agent_core.agents.lilith_growth import FreeTextGateway, LilithGrowthAgent

    agent = LilithGrowthAgent.from_cli_credentials(
        api_key=None, base_url=None, model="gpt-4o"
    )
    assert isinstance(agent.llm_gateway, FreeTextGateway)


def test_legacy_direct_httpx_gateway_is_not_the_default():
    """Eski doğrudan `httpx` adaptörü varsayılan DEĞİLDİR (bütçe bypass'ı)."""
    from agent_core.agents.lilith_growth import LilithGrowthAgent
    from agent_core.services.llm_gateway import LLMGateway

    agent = LilithGrowthAgent.from_cli_credentials(
        api_key="sk-test", base_url=None, model="gpt-4o"
    )
    assert not isinstance(agent.llm_gateway, type(None))
    assert isinstance(agent.llm_gateway, LLMGateway)


def test_vault_key_fallback_does_not_override_the_main_line_transport():
    """Ana hattın taşıma sırası bozulmaz.

    `NINEROUTER_*`/`PINEAL_LLM_*`/`OPENROUTER_*` ortamda tanımlıysa kasa
    anahtarı ortama **eklenmez** (taşıma operatörün seçimini ezer).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_lilith_module", REPO_ROOT / "run_lilith.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    import os

    os.environ["NINEROUTER_API_KEY"] = "sk-ninerouter"
    try:
        assert module.inject_vault_key_fallback() is None
        assert os.environ.get("OPENROUTER_API_KEY") in (None, "")
    finally:
        os.environ.pop("NINEROUTER_API_KEY", None)


def test_the_live_gate_blocks_the_cli_instead_of_failing_silently(monkeypatch, capsys):
    """Ana hattın kapısı CLI için de geçerli: hüküm dürüstçe yazılır.

    Ana hattın `LLMGateway`'i canlı çağrıyı `REAL_LLM_CALL_NOT_EXECUTED`
    ile reddeder; CLI bunu "başarılı" diye sunmaz, hata koduyla çıkar.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_lilith_module2", REPO_ROOT / "run_lilith.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class _Boom:
        async def execute(self, _payload):
            raise RuntimeError(
                "REAL_LLM_CALL_NOT_EXECUTED: Canlı LLM çağrıları kapalı."
            )

    monkeypatch.setattr(
        module.LilithGrowthAgent,
        "from_cli_credentials",
        classmethod(lambda cls, **_kw: _Boom()),
    )
    monkeypatch.setattr(module.sys, "argv", ["run_lilith.py", "--topic", "t"])

    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ÇALIŞMADI" in err
    assert "REAL_LLM_CALL_NOT_EXECUTED" in err


# ─────────────────────────────────────────────────────────────────────────────
# 3. DOKÜMAN = KOD
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_technical_claim_matches_the_code():
    """README_TECHNICAL.md'nin "ham profil metni eklenmez" iddiası koda uymalı.

    Kod (`agent_core/agents/lilith_growth.py`) biyografi ve gönderileri
    prompt bağlamına "sağlanan metin" olarak **ekliyor**; README de bunu
    söylemelidir. Söylemiyorsa iddia ile kod çelişir (denetim bulgusu 6a).
    """
    readme = (REPO_ROOT / "README_TECHNICAL.md").read_text(encoding="utf-8")
    lilith_section = readme.split("`LilithGrowthAgent`", 1)[1][:4000]
    assert "prompt bağlamına doğrudan eklenmez" not in lilith_section, (
        "README hâlâ 'ham profil metni eklenmez' diyor; kod ekliyor "
        "(lilith_growth.py:568-583)"
    )
    assert "sağlanan metin" in lilith_section

    source = (REPO_ROOT / "agent_core" / "agents" / "lilith_growth.py").read_text(
        encoding="utf-8"
    )
    assert "Hedef Profili (sağlanan metin)" in source, (
        "README 'sağlanan metin' diyor ama prompt etiketi değişmiş"
    )


def test_readme_technical_states_the_gate_rules():
    """README_TECHNICAL.md, Lilith için ana hat kapılarını yazar."""
    readme = (REPO_ROOT / "README_TECHNICAL.md").read_text(encoding="utf-8")
    lilith_section = readme.split("`LilithGrowthAgent`", 1)[1][:4000]
    for needle in ("NINEROUTER", "LIVE_LLM_E2E", "spend"):
        assert needle in lilith_section, f"Lilith bölümünde {needle} yok"
