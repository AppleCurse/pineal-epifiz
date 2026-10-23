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
  2. README yetenek sayısı kayıt defteriyle aynı olmalı (27)
  3. README dalga motoru sayısı kodla aynı olmalı (7)
  4. README API ucu sayısı uygulamayla aynı olmalı (69)
  5. README envanter dosya sayısı haritanın kendi ölçümüyle aynı olmalı
  6. README sistemin haritasına (docs/envanter.html) bağlanmalı
  7. README her ajanı ve her yeteneği ADIYLA anmalı

[2026-10-23 · BULUNAN KUSUR] Bu betikteki "eski metin" değerleri ELLE
yazılmıştı (`**26 yetenek**`, `... (68 HTTP ucu ...`, `739 dosya ...`). README
sayıları değişince betik sessizce çürüdü: 3/8 adım "hedef metin bulunamadı"
diyerek FAIL oldu — yani "revert-doğrulama çalışıyor" iddiası yanlıştı.
Artık sayılar README'den OKUNUR ve 1 eksiltilir; betik sayı değişimine
kendiliğinden uyum sağlar, bir daha çürüyemez. Çürüme testi
`tests/unit/test_revert_verification_contract.py` içindedir.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_VENV_PY = ROOT / ".venv" / "bin" / "python"
# .venv depoda (gitignore) ama her ortamda aynı yerde olmayabilir; yoksa
# betiği koşturan yorumlayıcı kullanılır (sessiz "dosya yok" hatası olmaz).
PY = str(_VENV_PY) if _VENV_PY.exists() else sys.executable


def run_tests(selector: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", selector, "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, (proc.stdout or "")[-1500:]

def _dirty(rel_path: str) -> str:
    """Dosya HEAD'e göre kirli mi? (revert-doğrulama kirli ağaçta KOŞMAZ)"""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", rel_path],
        cwd=ROOT, capture_output=True, text=True,
    )
    return (proc.stdout or "").strip()


def revert_step(
    name: str, rel_path: str, current: str, reverted: str, target: str
) -> bool:
    """Düzeltmeyi geri al → test KIRMIZI olmalı → geri yükle → test YEŞİL olmalı."""
    path = ROOT / rel_path
    dirty = _dirty(rel_path)
    if dirty:
        print(f"!! {name}: {rel_path} commit'lenmemiş değişiklik taşıyor — "
              f"revert-doğrulama kirli dosyada koşmaz ({dirty.splitlines()[0]})")
        return False
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


#: (ad, README'deki sayı kalıbı, hedef test düğümü) — `main()` bunları koşar,
#: `tests/unit/test_revert_verification_contract.py` kalıpların README'de hâlâ
#: eşleştiğini doğrular (betik sessizce çürüyemez).
NUMERIC_STEPS: tuple[tuple[str, str, str], ...] = (
    (
        "P9-1 README ajan sayısı koddan koptu",
        r"\*\*(\d+)\s+görev ajanı\*\*",
        "tests/unit/test_readme_claims.py::test_readme_agent_count_matches_the_executor",
    ),
    (
        "P9-2 README yetenek sayısı koddan koptu",
        r"\*\*(\d+)\s+yetenek\*\*",
        "tests/unit/test_readme_claims.py::test_readme_capability_count_matches_the_registry",
    ),
    (
        "P9-3 README dalga motoru sayısı koddan koptu",
        r"\*\*(\d+)\s+dalga motoru\*\*",
        "tests/unit/test_readme_claims.py::test_readme_engine_count_matches_the_code",
    ),
    (
        "P9-4 README API ucu sayısı uygulamadan koptu",
        r"## 11 · API yüzeyi \((\d+)\s+HTTP ucu",
        "tests/unit/test_readme_claims.py::test_readme_endpoint_count_matches_the_app",
    ),
    (
        "P9-5 README envanter sayısı haritadan koptu",
        r"(\d+)\s+dosya,\s+klasör klasör",
        "tests/unit/test_readme_claims.py::test_readme_inventory_count_matches_the_map",
    ),
)

#: Yapısal adımlar: (ad, README'de aranan metin, yerine yazılan, hedef test).
STRUCTURAL_STEPS: tuple[tuple[str, str, str, str], ...] = (
    (
        "P9-6 README sistemin haritasına bağlanmıyor",
        "**Tam ve aranabilir harita:** **[docs/envanter.html](docs/envanter.html)**",
        "**Tam ve aranabilir harita:** (bağlantı kaldırıldı) REVERT",
        "tests/unit/test_readme_claims.py::test_readme_points_to_the_map",
    ),
    (
        "P9-7 README bir ajanı anmıyor",
        "| `depth_analyst` | 7 sütunlu derinlik çıktısının adli analizi |",
        "| (ajan satırı kaldırıldı) | REVERT |",
        "tests/unit/test_readme_claims.py::test_readme_lists_every_registered_agent",
    ),
    (
        "P9-8 README bir yeteneği anmıyor",
        "`verifier.jury.local` (yerel jüri)",
        "(yetenek satırı kaldırıldı) REVERT",
        "tests/unit/test_readme_claims.py::test_readme_lists_every_capability_id",
    ),
)


def numeric_revert_step(name: str, pattern: str, target: str) -> bool:
    """README'deki sayıyı BUL, 1 eksilt, testin kırmızıya döndüğünü gör.

    `pattern` tek yakalama grubu taşır (sayı). Böylece "eski metin" elle
    yazılmaz; README sayısı değişse de betik çürümez.
    """
    path = ROOT / "README.md"
    dirty = _dirty("README.md")
    if dirty:
        print(f"!! {name}: README.md commit'lenmemiş değişiklik taşıyor — "
              f"revert-doğrulama kirli dosyada koşmaz ({dirty.splitlines()[0]})")
        return False
    backup = Path(tempfile.mkdtemp()) / path.name
    shutil.copy2(path, backup)
    try:
        text = path.read_text(encoding="utf-8")
        match = re.search(pattern, text)
        if not match:
            print(f"!! {name}: README'de sayı kalıbı bulunamadı ({pattern})")
            return False
        value = int(match.group(1))
        if value <= 0:
            print(f"!! {name}: sayı {value} — eksiltilemez")
            return False
        broken = text[: match.start(1)] + str(value - 1) + text[match.end(1):]
        path.write_text(broken, encoding="utf-8")
        code, out = run_tests(target)
        red = code != 0
        shutil.copy2(backup, path)
        code2, _ = run_tests(target)
        green = code2 == 0
        ok = red and green
        print(f"{'PASS' if ok else 'FAIL'} · {name}")
        print(f"      sayı {value} → {value - 1} · test: {target}")
        print(f"      revert sonrası pytest exit: {code} (beklenen: !=0) · "
              f"geri yükleme sonrası: {code2} (beklenen: 0)")
        if not red:
            print("      !! sayı bozulunca test YEŞİL kaldı — kilit eksik!")
            print(out)
        elif not green:
            print("      !! geri yükleme sonrası test KIRMIZI — dosya bozuldu!")
        return ok
    finally:
        shutil.copy2(backup, path)
        backup.unlink(missing_ok=True)


def main() -> int:
    results: list[bool] = []

    # Sayısal adımlar: "eski metin" README'den okunur (elle yazılmaz).
    for name, pattern, target in NUMERIC_STEPS:
        results.append(numeric_revert_step(name, pattern, target))
    # Yapısal adımlar: metin sabit (README'de birebir geçmek zorunda).
    for name, current, reverted, target in STRUCTURAL_STEPS:
        results.append(revert_step(name, "README.md", current, reverted, target))

    passed = sum(1 for r in results if r)
    print("-" * 72)
    print(f"SONUÇ: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
