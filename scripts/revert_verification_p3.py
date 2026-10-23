#!/usr/bin/env python3
"""Revert-doğrulama (P3): her P3 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p3.py

Her adım: dosya yedeği al → düzeltmeyi geri al → hedef testi koş → KIRMIZI
olduğunu doğrula → dosyayı GERİ YÜKLE. Böylece çalışma ağacı değişmez.

P3 düzeltmeleri (Faz 2 · Lilith):
  1. M-2: Lilith CLI ana hattın LLMGateway'ini kullanıyor (bütçe/kapı bypass'ı yok)
  2. README_TECHNICAL.md'nin "ham profil metni prompt'a eklenmez" iddiası koda uyuyor
  3. README.md Lilith kararını (CLI-only) ve doğru dosya yolunu yazıyor
  4. Ana hattın kapısı reddederse CLI bunu "başarılı" diye sunmuyor (çıkış kodu 2)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_VENV_PY = ROOT / ".venv" / "bin" / "python"
# [2026-10-23] .venv her ortamda depo kökünde olmayabilir; yoksa
# betiği koşturan yorumlayıcı kullanılır (sessiz FileNotFoundError yok).
PY = str(_VENV_PY) if _VENV_PY.exists() else sys.executable


def run_tests(selector: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", selector, "-q", "-p", "no:cacheprovider", "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout or "")[-2500:]

def _dirty(rel_path: str) -> str:
    """Dosya HEAD'e göre kirli mi? (revert-doğrulama kirli ağaçta KOŞMAZ)

    [2026-10-23] Kanıt, bozuk bir ağaçta üretilemez: bir önceki koşum dosyayı
    geri yükleyemeden düşerse sonraki koşum "hedef metin bulunamadı" der ve
    gerçek durum görünmez. Bu kontrol o sessiz durumu imkânsız kılar.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", rel_path],
        cwd=ROOT, capture_output=True, text=True,
    )
    return (proc.stdout or "").strip()


def revert_step(name: str, target: str, rel_path: str, current: str, reverted: str,
                replace_all: bool = False) -> bool:
    """`current` (düzeltilmiş hâl) → `reverted` (düzeltme geri alınmış hâl).

    Dosya yedeği alır, değişimi uygular, hedef testi koşar ve KIRMIZI olduğunu
    doğruladıktan sonra dosyayı GERİ YÜKLER.
    """
    path = ROOT / rel_path
    dirty = _dirty(rel_path)
    if dirty:
        print(f"!! {name}: {rel_path} commit'lenmemiş değişiklik taşıyor — "
              "revert-doğrulama kirli dosyada koşmaz "
              f"({dirty.splitlines()[0]})")
        return False
    backup = Path(tempfile.mkdtemp()) / path.name
    shutil.copy2(path, backup)
    try:
        text = path.read_text(encoding="utf-8")
        if current not in text:
            print(f"!! {name}: hedef metin bulunamadı ({rel_path})")
            return False
        count = -1 if replace_all else 1
        path.write_text(text.replace(current, reverted, count), encoding="utf-8")
        code, out = run_tests(target)
    finally:
        # [2026-10-23] Geri yükleme ARTIK `finally` içinde: koşum düşse/kesilse
        # bile çalışma ağacı bozuk kalmaz (eskiden yalnız mutlu yolda çalışıyordu).
        shutil.copy2(backup, path)
        backup.unlink(missing_ok=True)
    ok = code != 0
    print(f"{'PASS' if ok else 'FAIL'} · {name}")
    print(f"      test: {target}")
    print(f"      revert sonrası pytest exit: {code} (beklenen: !=0)")
    if not ok:
        print(out)
    return ok


def main() -> int:
    results: list[bool] = []

    # 1) M-2: Lilith CLI kendi httpx adaptörünü değil ana hattın gateway'ini kullanmalı
    results.append(revert_step(
        "P3-1 M-2: Lilith CLI ana hattın bütçe/kapı düzenini bypass ediyor",
        "tests/unit/test_p3_lilith_cli.py::test_cli_uses_the_main_line_gateway_when_a_key_exists",
        "agent_core/agents/lilith_growth.py",
        current='''        if use_main_line_gateway and api_key:
            from agent_core.services.llm_gateway import LLMGateway

            return cls(llm_gateway=LLMGateway())''',
        reverted='''        if False:
            from agent_core.services.llm_gateway import LLMGateway

            return cls(llm_gateway=LLMGateway())''',
    ))

    # 2) README_TECHNICAL iddiası kodla uyumlu olmalı
    results.append(revert_step(
        "P3-2 doküman: README_TECHNICAL 'ham profil metni eklenmez' diyor, kod ekliyor",
        "tests/unit/test_p3_lilith_cli.py::test_readme_technical_claim_matches_the_code",
        "README_TECHNICAL.md",
        current='''**Verilen profildeki biyografi ve gönderi metni prompt bağlamına "sağlanan metin" olarak eklenir**''',
        reverted='''ham profil metni prompt bağlamına doğrudan eklenmez''',
    ))

    # 3) README: CLI-only kararı + doğru dosya yolu
    results.append(revert_step(
        "P3-3 doküman: README Lilith kararını ve dosya yolunu yazmıyor",
        "tests/unit/test_p3_lilith_cli.py::test_readme_states_the_cli_only_decision",
        "README.md",
        # [2026-10-23] README P9'da düz dile çevrildi; eski çıpa kalmadı.
        # Karar iki yerde geçiyor (6. bölüm + P3 satırı) → TÜMÜ değiştirilir,
        # yoksa test tek kalan "CLI-only" ifadesiyle yeşil kalırdı.
        current="CLI-only",
        reverted="CLI-DISI",
        replace_all=True,
    ))

    # 4) Ana hat kapısı reddederse CLI dürüst çıkmalı (sessiz "başarılı" yok)
    results.append(revert_step(
        "P3-4 kapı: CLI canlı çağrı reddini yutuyor (sessiz başarı)",
        "tests/unit/test_p3_lilith_cli.py::test_the_live_gate_blocks_the_cli_instead_of_failing_silently",
        "run_lilith.py",
        current='''    try:
        result = asyncio.run(agent.execute(payload))
    except RuntimeError as exc:
        # Ana hattın kapıları (canlı çağrı kapalı, bütçe, taşıma) CLI için de
        # geçerlidir: hüküm dürüstçe yazılır, SESSİZCE "başarılı" sayılmaz.
        print(f"[LILITH] ÇALIŞMADI: {exc}", file=sys.stderr)
        raise SystemExit(2)''',
        reverted='''    result = asyncio.run(agent.execute(payload))''',
    ))

    print()
    passed = sum(1 for r in results if r)
    print(
        f"REVERT-DOĞRULAMA (P3): {passed}/{len(results)} düzeltme geri alınınca "
        "KIRMIZIya döndü"
    )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
