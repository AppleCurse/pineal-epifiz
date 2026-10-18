#!/usr/bin/env python3
"""Revert-doğrulama (P9 · doküman yenileme): README'nin iddiaları koda bağlı.

Kullanım: python scripts/revert_verification_p9.py

P9'de README "herkesin anlayabileceği bir dilde" baştan yazıldı. Düz dil, yalan
demek değildir: README'deki SAYILAR (ajan, yetenek, dalga motoru, API ucu,
envanter dosyası) canlı koddan ölçülür ve `tests/unit/test_readme_claims.py`
ile kilitlenir. Bu betik, o kilidin geri alınınca testin KIRMIZIYA döndüğünü
gösterir.

P9 düzeltmeleri:
  1. README ajan sayısı yürütücüyle aynı olmalı (13)
  2. README yetenek sayısı kayıt defteriyle aynı olmalı (26)
  3. README dalga motoru sayısı kodla aynı olmalı (7)
  4. README API ucu sayısı uygulamayla aynı olmalı (68)
  5. README envanter dosya sayısı haritanın kendi ölçümüyle aynı olmalı
  6. README sistemin haritasına (docs/envanter.html) bağlanmalı
  7. README her ajanı ve her yeteneği ADIYLA anmalı
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
            print("      !! düzeltme geri alınınca test YEŞİL kaldı — kilit eksik!")
            print(out)
        elif not green:
            print("      !! geri yükleme sonrası test KIRMIZI — dosya bozuldu!")
        return ok
    finally:
        shutil.copy2(backup, path)
        backup.unlink(missing_ok=True)


def main() -> int:
    readme = "README.md"
    claims = "tests/unit/test_readme_claims.py"
    results: list[bool] = []

    results.append(revert_step(
        "P9-1 README ajan sayısı koddan koptu",
        readme, "**13 görev ajanı**", "**12 görev ajanı**",
        f"{claims}::test_readme_agent_count_matches_the_executor",
    ))
    results.append(revert_step(
        "P9-2 README yetenek sayısı koddan koptu",
        readme, "**26 yetenek**", "**25 yetenek**",
        f"{claims}::test_readme_capability_count_matches_the_registry",
    ))
    results.append(revert_step(
        "P9-3 README dalga motoru sayısı koddan koptu",
        readme, "**7 dalga motoru**", "**6 dalga motoru**",
        f"{claims}::test_readme_engine_count_matches_the_code",
    ))
    results.append(revert_step(
        "P9-4 README API ucu sayısı uygulamadan koptu",
        readme, "## 11 · API yüzeyi (68 HTTP ucu + 1 WebSocket)",
        "## 11 · API yüzeyi (62 HTTP ucu + 1 WebSocket)",
        f"{claims}::test_readme_endpoint_count_matches_the_app",
    ))
    results.append(revert_step(
        "P9-5 README envanter sayısı haritadan koptu",
        readme, "745 dosya, klasör klasör", "742 dosya, klasör klasör",
        f"{claims}::test_readme_inventory_count_matches_the_map",
    ))
    results.append(revert_step(
        "P9-6 README sistemin haritasına bağlanmıyor",
        readme, "**Tam ve aranabilir harita:** **[docs/envanter.html](docs/envanter.html)**",
        "**Tam ve aranabilir harita:** (bağlantı kaldırıldı) REVERT",
        f"{claims}::test_readme_points_to_the_map",
    ))
    results.append(revert_step(
        "P9-7 README bir ajanı anmıyor",
        readme, "| `depth_analyst` | 7 sütunlu derinlik çıktısının adli analizi |",
        "| (ajan satırı kaldırıldı) | REVERT |",
        f"{claims}::test_readme_lists_every_registered_agent",
    ))
    results.append(revert_step(
        "P9-8 README bir yeteneği anmıyor",
        readme, "`verifier.jury.local` (yerel jüri)", "(yetenek satırı kaldırıldı) REVERT",
        f"{claims}::test_readme_lists_every_capability_id",
    ))

    passed = sum(1 for r in results if r)
    print("-" * 72)
    print(f"SONUÇ: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
