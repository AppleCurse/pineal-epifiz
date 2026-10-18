#!/usr/bin/env python3
"""Revert-doğrulama (P2): her P2 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p2.py

Her adım: dosya yedeği al → düzeltmeyi geri al → hedef testi koş → KIRMIZI
olduğunu doğrula → dosyayı GERİ YÜKLE. Böylece çalışma ağacı değişmez.

P2 düzeltmeleri (Faz 2 · çapraz profilleme):
  1. Alt dize eşleşmesi kapatıldı (URL'nin KENDİSİ eşleşir)
  2. socid kimlik alanı kullanıcı adı gibi eşleşmiyor (false positive yok)
  3. Skor "kapsam" etiketli — kanıtın `confidence` alanı boş kalıyor
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
    """`current` (düzeltilmiş hâl) → `reverted` (düzeltme geri alınmış hâl).

    Dosya yedeği alır, değişimi uygular, hedef testi koşar ve KIRMIZI olduğunu
    doğruladıktan sonra dosyayı GERİ YÜKLER.
    """
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


def main() -> int:
    results: list[bool] = []

    # 1) Alt dize eşleşmesi: "x.com/alice" ⊂ "x.com/alicexyz" → yanlış eşleşme
    results.append(revert_step(
        "P2-1 alt dize: biyografideki benzer adres yanlış eşleşme üretiyor",
        "tests/unit/test_p2_cross_profiling.py::test_substring_url_in_bio_is_not_a_match",
        "agent_core/services/cross_profiler.py",
        current='''                norm = _normalize_url(acc.get("url") or "")
                if norm and norm in bio_links:''',
        reverted='''                norm = _normalize_url(acc.get("url") or "")
                if norm and any(norm in link for link in bio_links):''',
    ))

    # 2) socid kimlik alanı kullanıcı adı gibi eşleşmemeli
    results.append(revert_step(
        "P2-2 socid id: kimlik alanı rastgele bir kullanıcı adıyla eşleşiyor",
        "tests/unit/test_p2_cross_profiling.py::test_socid_id_does_not_match_an_unrelated_handle",
        "agent_core/services/cross_profiler.py",
        current='''    # socid kimlik iddiaları (kullanıcı adı DEĞİL — yalnız kimlik sinyali)
    claims = _id_claims(tp.get("socid_identities"))''',
        reverted='''    # socid kimlik iddiaları (kullanıcı adı DEĞİL — yalnız kimlik sinyali)
    claims = _id_claims(tp.get("socid_identities"))
    for _sid in tp.get("socid_identities") or []:
        if isinstance(_sid, dict):
            _fields = _sid.get("fields") or {}
            _url = _sid.get("url") or ""
            _p, _, _ = _detect_platform_and_handle(_url)
            for _k in ("username", "user_id", "login", "screen_name", "account"):
                _v = _fields.get(_k)
                if isinstance(_v, str) and _v.strip():
                    _register(_p, _v.strip(), _url, "socid_identity")''',
    ))

    # 3) Skor "kapsam" etiketli olmalı; kanıtın `confidence` alanı boş kalmalı
    results.append(revert_step(
        "P2-3 kapsam etiketi: skor kanıtın confidence alanına geri döndü (olasılık gibi)",
        "tests/unit/test_p2_cross_profiling.py::test_coverage_is_a_scope_score_not_a_probability",
        "agent_core/services/cross_profiler.py",
        current='''            confidence=None,
            source_metrics={
                "coverage": m.coverage,''',
        reverted='''            confidence=m.coverage,
            source_metrics={
                "coverage": m.coverage,''',
    ))

    print()
    passed = sum(1 for r in results if r)
    print(
        f"REVERT-DOĞRULAMA (P2): {passed}/{len(results)} düzeltme geri alınınca "
        "KIRMIZIya döndü"
    )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
