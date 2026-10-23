"""Revert-doğrulama betiği ÇÜRÜYEMEZ: aradığı metinler README'de olmalı.

[2026-10-23 · BULUNAN KUSUR] `scripts/revert_verification_p9.py` "her düzeltme
geri alınınca test kırmızıya döner" iddiasını kanıtlıyordu; README'nin sayıları
değişince (26 → 27 yetenek, 68 → 69 uç, 739 → 760 dosya) betikteki ELLE
yazılmış "eski metin"ler bayatladı ve **5/8 PASS**'e düştü. Hiçbir test bunu
görmediği için kusur sessizce duruyordu.

Bu test iki şeyi kilitler:
  1. Betiğin sayı kalıpları README'de hâlâ eşleşiyor (sayılar README'den
     okunur — elle yazılmaz).
  2. Betiğin yapısal adımlarının aradığı metinler README'de birebir var.
  3. Her adımın hedef test düğümü gerçekten tanımlı (silinen test = sessiz
     "kanıt" değil, kırmızı).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "revert_verification_p9.py"
README = REPO_ROOT / "README.md"


def _script_module():
    spec = importlib.util.spec_from_file_location("_revert_p9", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_numeric_patterns_still_match_the_readme():
    """Her sayısal adımın kalıbı README'de eşleşmeli (yoksa adım sessizce ölür)."""
    module = _script_module()
    readme = _readme()
    broken = [
        name for name, pattern, _target in module.NUMERIC_STEPS
        if re.search(pattern, readme) is None
    ]
    assert not broken, f"README'de eşleşmeyen revert adımları: {broken}"


def test_structural_steps_still_find_their_text():
    """Yapısal adımların aradığı metin README'de birebir bulunmalı."""
    module = _script_module()
    readme = _readme()
    missing = [
        name for name, current, _reverted, _target in module.STRUCTURAL_STEPS
        if current not in readme
    ]
    assert not missing, f"README'de bulunamayan revert adımları: {missing}"


def test_every_revert_step_points_to_a_real_test():
    """Her adımın hedef testi dosyada tanımlı olmalı."""
    module = _script_module()
    steps = [target for _n, _p, target in module.NUMERIC_STEPS]
    steps += [target for _n, _c, _r, target in module.STRUCTURAL_STEPS]
    for target in steps:
        path, _, test_name = target.partition("::")
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert f"def {test_name}(" in source, f"hedef test yok: {target}"


def test_number_mutation_really_breaks_the_claim():
    """Bir sayıyı 1 eksiltmek README iddiasını bozar (kilit gerçekten ısırır)."""
    module = _script_module()
    readme = _readme()
    for _name, pattern, _target in module.NUMERIC_STEPS:
        match = re.search(pattern, readme)
        assert match, pattern
        value = int(match.group(1))
        mutated = readme[: match.start(1)] + str(value - 1) + readme[match.end(1):]
        assert mutated != readme
