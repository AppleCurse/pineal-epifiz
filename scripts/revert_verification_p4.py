#!/usr/bin/env python3
"""Revert-doğrulama (P4): her P4 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p4.py

P4 düzeltmeleri (Faz 2 · dokümantasyon = kod):
  1. Reddedilen holehe taraması da mühürlü kayda bağlanıyor (maigret simetrisi)
  2. README'de "ölçülen ↔ DOĞRULANMADI" durum tablosu var
  3. README_TECHNICAL'de holehe'nin **ölçülmüş** durumu yazılı
  4. RUNBOOK'da 9Router kipinde `dialogue_manager` boşluğu (M-1) yazılı
  5. RUNBOOK'da 9Router kasa anahtarının `sk-pineal` önek şartı (M-3) yazılı
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")


def run_tests(selector: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", selector, "-q", "-p", "no:cacheprovider", "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout or "")[-2500:]


def revert_step(name: str, target: str, rel_path: str, current: str, reverted: str) -> bool:
    """`current` (düzeltilmiş hâl) → `reverted` (düzeltme geri alınmış hâl)."""
    path = ROOT / rel_path
    backup = Path(tempfile.mkdtemp()) / path.name
    shutil.copy2(path, backup)
    text = path.read_text(encoding="utf-8")
    if current not in text:
        print(f"!! {name}: hedef metin bulunamadı ({rel_path})")
        shutil.copy2(backup, path)
        return False
    path.write_text(text.replace(current, reverted, 1), encoding="utf-8")
    code, out = run_tests(target)
    shutil.copy2(backup, path)
    ok = code != 0
    print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"      test: {target}")
    print(f"      revert sonrası pytest exit: {code} (beklenen: !=0)")
    if not ok:
        print(out)
    return ok


def revert_block_step(
    name: str, target: str, rel_path: str, start_marker: str, end_marker: str
) -> bool:
    """`start_marker`..`end_marker` arasındaki bloğu siler (doküman düzeltmesi geri alınır)."""
    path = ROOT / rel_path
    backup = Path(tempfile.mkdtemp()) / path.name
    shutil.copy2(path, backup)
    text = path.read_text(encoding="utf-8")
    if start_marker not in text or end_marker not in text:
        print(f"!! {name}: işaretçi bulunamadı ({rel_path})")
        shutil.copy2(backup, path)
        return False
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    path.write_text(text[:start] + text[end:], encoding="utf-8")
    code, out = run_tests(target)
    shutil.copy2(backup, path)
    ok = code != 0
    print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"      test: {target}")
    print(f"      revert sonrası pytest exit: {code} (beklenen: !=0)")
    if not ok:
        print(out)
    return ok


def main() -> int:
    results: list[bool] = []

    # 1) Reddedilen holehe taraması da mühürlü kayda bağlanmalı
    results.append(revert_step(
        "P4-1 kanıt: reddedilen holehe taraması zincirde görünmüyor",
        "tests/unit/test_holehe_scanner.py::TestAgentMerge::test_refused_scan_is_sealed_as_evidence",
        "agent_core/agents/osint_investigator.py",
        current='''        # [P4 · 2026-10-16] Kapı/kasa reddi de MÜHÜRLÜ kanıt olarak korunur
        # (maigret ile simetri): reddedilen tarama da zincirde görünür.
        return profile.model_copy(update={"email_scan": scan.model_dump(), **sealed})''',
        reverted='''        return profile.model_copy(update={"email_scan": scan.model_dump()})''',
    ))

    # 2) README durum tablosu
    results.append(revert_block_step(
        "P4-2 doküman: README'de ölçülen ↔ DOĞRULANMADI tablosu yok",
        "tests/unit/test_p4_documentation.py::test_readme_has_the_measured_vs_unverified_table",
        "README.md",
        start_marker="## 13 · Durum tablosu: ölçülen çalışma ↔ DOĞRULANMADI",
        end_marker="| `ENABLE_*` bayraklarının tamamı açık hâli | Kapılar kapalı tutuldu (görev talimatı) |",
    ))

    # 3) README_TECHNICAL holehe notu
    results.append(revert_block_step(
        "P4-3 doküman: README_TECHNICAL holehe'nin ölçülmüş durumunu yazmıyor",
        "tests/unit/test_p4_documentation.py::test_readme_technical_states_the_measured_holehe_state",
        "README_TECHNICAL.md",
        start_marker="7. **Hangi kapılara tabi?** **[P4 · 2026-10-16]**",
        end_marker="**Canlı holehe taraması DOĞRULANMADI** (sandbox egress'i kapalı).",
    ))

    # 4) RUNBOOK M-1
    results.append(revert_step(
        "P4-4 doküman: RUNBOOK 9Router dialogue_manager boşluğunu yazmıyor",
        "tests/unit/test_p4_documentation.py::test_runbook_documents_the_dialogue_manager_gap",
        "RUNBOOK.md",
        current='''- `dialogue_manager`: **9Router kanonik zinciri YOK (M-1)**''',
        reverted='''- `dialogue_manager`: (not kaldırıldı)''',
    ))

    # 5) RUNBOOK M-3
    results.append(revert_step(
        "P4-5 doküman: RUNBOOK 9Router 'sk-pineal' önek şartını yazmıyor",
        "tests/unit/test_p4_documentation.py::test_runbook_documents_the_sk_pineal_requirement",
        "RUNBOOK.md",
        current='''- **9Router kipinde kasa anahtarı — `sk-pineal` önek şartı (M-3):**''',
        reverted='''- (9Router kasa anahtarı notu kaldırıldı)''',
    ))

    print()
    passed = sum(1 for r in results if r)
    print(
        f"REVERT-DOĞRULAMA (P4): {passed}/{len(results)} düzeltme geri alınınca "
        "KIRMIZIya döndü"
    )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
