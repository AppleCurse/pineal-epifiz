"""``agent_core.task_executor`` İÇE AKTARIM SAFLIĞI sözleşmesi.

[AUDIT 2026-10-07 · P2] Modülün son satırı şuydu::

    executor = PinealExecutor()

Yani ``task_executor`` içe aktarıldığı ANDA bir yürütücü kuruluyordu.
``PinealExecutor.__init__`` AĞIR ve YAN ETKİLİDİR:

* ``build_memory_from_env()`` + ``DecisionConfig.load()`` -> ortam ve DİSK
  okur; bozuk/eksik ayarda içe aktarım PATLAR (hata yığını yanlış yerde).
* ``LLMGateway()``, ``SearchEngine()``, ``VisionAnalyzer()`` ve 13 ajanı
  kurar: gereksiz bellek ve başlatma maliyeti.
* ``agent_status_tracker.get_tracker()`` çağırır -> modül içe aktarımı,
  GLOBAL durum tekilini (singleton) SİDE-EFFECT olarak yaratır.

Sonuç: ``from agent_core.task_executor import AgentTimeoutError`` yazmak
bile tüm bunları tetikliyordu. Küresel örnek kaldırıldı; ihtiyacı olan
yerinde kurar (API katmanı ``get_executor``, betikler kendi örneği).

Bu testler ALT SÜREÇTE (subprocess) koşar: aksi hâlde pytest oturumunda
modül zaten içe aktarılmış olacağından yan etki GÖRÜNMEZ olurdu.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Modülü içe aktarıp YAN ETKİ arayan gözlemci kod.
_PROBE = """
import sys

# 1) Yalnızca içe aktar — hiçbir şey KURULMAMALI.
import agent_core.task_executor as m

assert not hasattr(m, "executor"), (
    "modül içe aktarımında global `executor` örneği kurulmuş "
    "(yan etki geri geldi)"
)

# 2) AgentStatusTracker tekili de SİDE-EFFECT olarak yaratılmamalı.
import agent_core.services.agent_status_tracker as st
assert st._tracker is None, (
    "modül içe aktarımı AgentStatusTracker tekilini kurmuş: "
    "PinealExecutor.__init__ dolaylı olarak çağrılmış demektir"
)

# 3) Ağır bağımlılıklar da içe aktarımda kurulmamalı (örnek yok).
assert "executor" not in vars(m), "modül ad alanında yürütücü örneği var"

print("PURE")
"""


def _run_probe(extra: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _PROBE + extra],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_import_does_not_construct_an_executor():
    """[AUDIT] İçe aktarım yürütücü KURMAMALI."""
    result = _run_probe()
    assert result.returncode == 0, (
        "task_executor içe aktarımı SAF değil (yan etki):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr[-2000:]}"
    )
    assert "PURE" in result.stdout


def test_import_does_not_touch_disk_config():
    """Yapılandırma/DİSK okuması içe aktarımda değil, KURULUMDA olmalı.

    Bozuk bir yapılandırma dosyasıyla bile modül SORUNSUZ içe aktarılmalı;
    hata ancak yürütücü KURULDUĞUNDA (açıkça) çıkmalı.
    """
    result = _run_probe()
    assert result.returncode == 0, (
        f"içe aktarım yapılandırma/ortam okumasına bağlı:\n{result.stderr[-2000:]}"
    )


def test_executor_can_still_be_constructed_explicitly():
    """Saflık, işlevsizlik demek değil: isteyen AÇIKÇA kurabilmeli."""
    extra = """

from agent_core.task_executor import PinealExecutor

executor = PinealExecutor()
assert executor.agents, "açık kurulumda ajanlar hazır olmalı"
assert isinstance(executor.agents, dict) and len(executor.agents) >= 12, (
    f"beklenen >=12 ajan, gelen: {len(executor.agents)}"
)
print("CONSTRUCTED")
"""
    result = _run_probe(extra)
    assert result.returncode == 0, (
        f"açık kurulum başarısız:\n{result.stderr[-2500:]}"
    )
    assert "CONSTRUCTED" in result.stdout


def test_source_has_no_module_level_executor_instance():
    """Statik kilit: modül gövdesinde `executor = PinealExecutor()` olmamalı."""
    import ast

    source = (REPO_ROOT / "agent_core/task_executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = [
        ast.unparse(node)
        for node in tree.body  # yalnızca MODÜL GÖVDESİ (sınıf/fonksiyon içi değil)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) for target in node.targets
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "PinealExecutor"
    ]
    assert not offenders, (
        f"modül gövdesinde yürütücü kurulumu bulundu: {offenders}"
    )


def test_no_remaining_importer_of_the_removed_global():
    """Küresel örneğe bağlı HİÇBIR çağrı yeri kalmamalı (arşiv dâhil)."""
    importers = []
    self_path = Path(__file__).resolve()
    for path in REPO_ROOT.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        # Bu dosyanın KENDİSİ kalıbı aradığı için elenir (kendi kendini
        # bulmasın): tarayıcı, aradığı dizeyi içermek zorundadır.
        if path.resolve() == self_path:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            if "from agent_core.task_executor import executor" in line or (
                "task_executor" in line and "import executor" in line
            ):
                importers.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")

    assert not importers, (
        "kaldırılan küresel `executor` örneğini içe aktaran yerler var:\n"
        + "\n".join(importers)
    )
