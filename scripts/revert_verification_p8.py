#!/usr/bin/env python3
"""Revert-doğrulama (P8): her P8 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p8.py

Kural (depo sözleşmesi): "her düzeltmenin testi olur ve revert-doğrulama
kırmızıya döner". Bu betik P8'deki 10 düzeltmeyi tek tek geri alır, ilgili
testi çalıştırır ve KIRMIZI olduğunu görür; sonra dosyayı geri yükleyip
testin YEŞİLE döndüğünü de doğrular (dosya bozulmadı mı?).

P8 düzeltmeleri:
  1. `/api/aspasia/state` çağrı izi penceresini sayfalıyor (offset/limit)
  2. `TelemetryReader.window` ofseti dikkate alıyor (geçmişe kayabiliyor)
  3. `CallBinder` günlük/sayfa kopukluğunu AYRI ayırıyor
  4. Panel ajan çıktısını (output_summary) satır satır gösteriyor
  5. Panel kanıt zincirini ajan→kanıt GRUPLUYOR
  6. Panel metin + durum filtresi uyguluyor
  7. Panel çağrı izi sayfalama ofsetini durum ucuna gönderiyor
  8. Doğrulama betiği erişilemeyen API'de `rc=2` dönüyor (dürüst hata yolu)
  9. `api.py` state gövdesini modülden alıyor (gövde kopyalanmıyor)
 10. `api.py` satır tavanı (5760) aşılmıyor
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")

#: (ad, hedef dosya, mevcut metin, geri alınmış metin, test)
CASES: list[tuple[str, str, str, str, str]] = [
    (
        "P8-1 state ucu sayfalamayı yok sayıyor",
        "backend/api.py",
        '    room = get_room(client_id)\n    executor = room.get("executor")',
        '    offset = 0  # REVERT: sayfalama yok sayılıyor\n'
        '    room = get_room(client_id)\n    executor = room.get("executor")',
        "tests/unit/test_live_control_panel.py::test_state_endpoint_paginates_call_trace",
    ),
    (
        "P8-2 TelemetryReader.window ofseti yok sayıyor",
        "agent_core/aspasia/interface.py",
        "        off = max(0, int(offset))",
        "        off = 0  # REVERT: ofset yok sayılıyor",
        "tests/unit/test_live_control_panel.py::test_telemetry_window_returns_older_records",
    ),
    (
        "P8-3 CallBinder sayfa/günlük ayrımını yapmıyor",
        "agent_core/aspasia/interface.py",
        '            "page_missing_call_ids": sorted((run_call_ids & in_log) - in_page),',
        '            "page_missing_call_ids": [],  # REVERT: ayrım yok',
        "tests/unit/test_live_control_panel.py::"
        "test_call_binder_separates_log_missing_from_page_missing",
    ),
    (
        "P8-4 panel output_summary satırlarını basmıyor",
        "frontend/src/components/LiveControlPanel.svelte",
        "<h4>ÇIKTI (output_summary)</h4>",
        "<h4>ÇIKTI</h4>  <!-- REVERT -->",
        "tests/unit/test_live_control_panel.py::test_panel_renders_output_summary_line_by_line",
    ),
    (
        "P8-5 panel kanıt zincirini gruplamıyor",
        "frontend/src/components/LiveControlPanel.svelte",
        "{#each Object.keys(evidenceByAgent) as agentName (agentName)}",
        "{#each evidenceChain as row, i (i)}  <!-- REVERT -->",
        "tests/unit/test_live_control_panel.py::"
        "test_panel_renders_evidence_chain_grouped_by_agent",
    ),
    (
        "P8-6 panel filtresi kaldırılmış",
        "frontend/src/components/LiveControlPanel.svelte",
        "$: filteredLane = agentLane.filter((run) => {",
        "$: filteredLane = agentLane;  // REVERT: filtre yok",
        "tests/unit/test_live_control_panel.py::test_panel_has_agent_filter",
    ),
    (
        "P8-7 panel çağrı izi sayfalaması kaldırılmış",
        "frontend/src/components/LiveControlPanel.svelte",
        "+ `&offset=${callOffset}&limit=${CALL_PAGE}`;",
        "+ `&limit=${CALL_PAGE}`;  // REVERT: ofset yok",
        "tests/unit/test_live_control_panel.py::test_panel_paginates_call_trace",
    ),
    (
        "P8-8 doğrulama betiği erişilemeyen API'de de 'başarılı' diyor",
        "scripts/verify_command_loop.py",
        "        return 2",
        "        return 0  # REVERT: erişilemezken de başarılı",
        "tests/unit/test_live_control_panel.py::"
        "test_verify_command_loop_script_reports_unreachable_api",
    ),
    (
        "P8-9 api.py state modülünü içe aktarmıyor",
        "backend/api.py",
        "from backend.services.aspasia_state import build_state_payload",
        "from backend.services.aspasia_state import build_state_payload as _reverted  "
        "# REVERT: satır bozuldu",
        "tests/unit/test_api_monolith_ratchet.py::"
        "test_aspasia_state_body_lives_in_its_own_module",
    ),
    (
        "P8-10 api.py tavanı aşıyor (6 satır eklenmiş)",
        "backend/api.py",
        "from backend.services.aspasia_state import build_state_payload",
        "from backend.services.aspasia_state import build_state_payload\n"
        "# REVERT: tavanı aşmak için 5 satır eklendi\n"
        "# 1\n# 2\n# 3\n# 4\n# 5",
        "tests/unit/test_api_monolith_ratchet.py::"
        "test_api_module_is_within_the_size_ceiling",
    ),
]


def run_tests(selector: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", selector, "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, (proc.stdout or "")[-1500:]


def revert_step(
    name: str, rel_path: str, current: str, reverted: str, target: str
) -> bool:
    """Düzeltmeyi geri al → test KIRMIZI olmalı → geri yükle → test YEŞİL olmalı."""
    path = ROOT / rel_path
    backup = Path(tempfile.mkdtemp()) / path.name
    shutil.copy2(path, backup)
    try:
        text = path.read_text(encoding="utf-8")
        if current not in text:
            print(f"!! {name}: hedef metin bulunamadı ({rel_path})")
            return False
        path.write_text(text.replace(current, reverted, 1), encoding="utf-8")
        code, out = run_tests(target)
        red = code != 0
        shutil.copy2(backup, path)
        code2, _ = run_tests(target)
        green = code2 == 0
        ok = red and green
        print(f"{'PASS' if ok else 'FAIL'} · {name}")
        print(f"      test: {target}")
        print(f"      revert sonrası pytest exit: {code} (beklenen: !=0) · "
              f"geri yükleme sonrası: {code2} (beklenen: 0)")
        if not red:
            print("      !! düzeltme geri alınınca test YEŞİL kaldı — test eksik!")
            print(out)
        elif not green:
            print("      !! geri yükleme sonrası test KIRMIZI — dosya bozuldu!")
        return ok
    finally:
        shutil.copy2(backup, path)
        backup.unlink(missing_ok=True)


def main() -> int:
    results: list[bool] = []
    for name, rel_path, current, reverted, target in CASES:
        results.append(revert_step(name, rel_path, current, reverted, target))
    passed = sum(1 for r in results if r)
    print("-" * 72)
    print(f"SONUÇ: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
