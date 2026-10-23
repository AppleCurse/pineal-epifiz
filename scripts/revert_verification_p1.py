#!/usr/bin/env python3
"""Revert-doğrulama (P1): her P1 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p1.py

Her adım: dosya yedeği al → düzeltmeyi geri al → hedef testi koş → KIRMIZI
olduğunu doğrula → dosyayı GERİ YÜKLE. Böylece çalışma ağacı değişmez.

P1 düzeltmeleri (Faz 2 · profil derinleştirme):
  1. URL → yetenek sınıflandırması (router)
  2. Derin tarama GERÇEKTEN yeteneği koşar (CapabilityRunner)
  3. Kapalı/engelli kapı → `not_run` + MAKİNE-OKUNUR sebep
  4. Bulunan profiller görev akışında gerçekten taranır (görev yürütücüsü bağlantısı)
  5. socid/derin tarama kanıtı kanonik kanıt zincirine girer
  6. Public-web araştırma gövdesi api.py'den AYRILDI (API-BÖLME 4)
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


def revert_step(name: str, target: str, rel_path: str, current: str, reverted: str) -> bool:
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
        path.write_text(text.replace(current, reverted, 1), encoding="utf-8")
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

    # 1) Sınıflandırma: URL → yetenek eşleşmesi kayboluyor
    results.append(revert_step(
        "P1-1 router: profil URL'si doğru yeteneğe bağlanmıyor",
        "tests/unit/test_p1_profile_routing.py::test_instagram_profile_url_routes_to_instagrapi",
        "agent_core/services/profile_router.py",
        current='''    for builder in (_instagram_route, _x_route, _social_route):
        route = builder(raw)
        if route is not None:
            return route''',
        reverted='''    for builder in ():
        route = builder(raw)
        if route is not None:
            return route''',
    ))

    # 2) Derin tarama yeteneği KOŞMUYOR
    results.append(revert_step(
        "P1-2 koşum: derin tarama yeteneği çalıştırmıyor",
        "tests/unit/test_p1_profile_routing.py::test_deep_scan_runs_through_the_capability_runner",
        "agent_core/services/profile_deep_scan.py",
        current='''        result = await active.run(route.capability_id, ctx, state=state)''',
        reverted='''        from agent_core.capabilities.base import CapabilityResult

        result = CapabilityResult(
            capability_id=route.capability_id,
            available=False,
            unavailable_reason="not_attempted",
        )''',
    ))

    # 3) Kapalı kapı → sebep kayboluyor (sessiz "ok")
    results.append(revert_step(
        "P1-3 kapalı kapı: koşmama sebebi yazılmıyor",
        "tests/unit/test_p1_profile_routing.py::test_closed_sensor_yields_not_run_with_machine_reason",
        "agent_core/services/profile_deep_scan.py",
        current='''    if available and error is None:
        return ok(channel, detail=f"{detail} · {len(items)} kanıt")
    if error:
        return failed(channel, reason=str(error), detail=detail)
    return not_run(channel, reason=str(reason or "unavailable"), detail=detail)''',
        reverted='''    return ok(channel, detail=f"{detail} · {len(items)} kanıt")''',
    ))

    # 4) GÖREV YÜRÜTÜCÜSÜ bağlantısı: bulunan profiller taranmıyor
    #    (koşum tek yerde: deep_profile_resolver → profile_router → CapabilityRunner)
    results.append(revert_step(
        "P1-4 görev yürütücüsü bağlantısı: bulunan profiller taranmıyor",
        "tests/unit/test_p1_profile_routing.py::test_executor_actually_runs_the_deep_scan_for_detected_profiles",
        "agent_core/task_executor.py",
        # [2026-10-23] Çıpa #153 refactor'üne göre güncellendi: `if _detected_urls:`
        # bloğunun ilk satırı artık `detected_urls` defterini yazıyor (eski
        # metin "try:" ile başlıyordu → "hedef metin bulunamadı").
        current='''        if _detected_urls:
            input_data.setdefault("target_profile", {})["detected_urls"] = list(_detected_urls)''',
        reverted='''        if False:  # [REVERT-DOĞRULAMA] derin tarama koşumu kaldırıldı
            input_data.setdefault("target_profile", {})["detected_urls"] = list(_detected_urls)''',
    ))

    # 5) Kanıt zinciri: derin tarama kanıtı kanonik listeye girmiyor
    results.append(revert_step(
        "P1-5 kanıt zinciri: socid/derin tarama kanıtı forensik kanıta girmiyor",
        "tests/unit/test_p1_profile_routing.py::test_deep_scan_evidence_merges_into_the_canonical_chain",
        "agent_core/services/pillar_evidence_adapter.py",
        current='''    for raw in extra_items or ():
        if isinstance(raw, EvidenceItem):
            items.append(raw)
        elif isinstance(raw, dict):
            items.append(EvidenceItem.model_validate(raw))
        else:
            raise TypeError(
                "extra_items yalnız EvidenceItem veya sözlük kabul eder: "
                f"{type(raw).__name__}"
            )''',
        reverted='''    for raw in ():
        items.append(raw)''',
    ))

    # 6) API-BÖLME 4: public-web araştırma gövdesi api.py'ye geri döndü
    results.append(revert_step(
        "P1-6 API-BÖLME 4: public-web araştırma gövdesi api.py içinde yeniden tanımlandı",
        "tests/unit/test_api_monolith_ratchet.py::test_api_does_not_redefine_web_research_body",
        "backend/api.py",
        current='''from backend.services.web_research import (  # noqa: F401 (yeniden ihraç, dış sözleşme)
    extract_handle_from_url as _extract_handle_from_url,
    run_public_web_research as _run_public_web_research,
)''',
        reverted='''def _extract_handle_from_url(url: str) -> str:
    """[REVERT-DOĞRULAMA] gövde api.py'ye geri kondu."""
    return (url or "").rstrip("/").split("/")[-1].lower()


async def _run_public_web_research(url: str, search_engine, client_id: str = "default"):
    """[REVERT-DOĞRULAMA] gövde api.py'ye geri kondu."""
    return {"status": "unavailable", "available": False, "results": []}''',
    ))

    print()
    passed = sum(1 for r in results if r)
    print(
        f"REVERT-DOĞRULAMA (P1): {passed}/{len(results)} düzeltme geri alınınca "
        "KIRMIZIya döndü"
    )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
