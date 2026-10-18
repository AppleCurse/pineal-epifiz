#!/usr/bin/env python3
"""Revert-doğrulama: her P0 düzeltmesi geri alınınca test KIRMIZIya dönmeli.

Kullanım: python scripts/revert_verification_p0.py
Her adım: dosya yedeği al → düzeltmeyi geri al → hedef testi koş → KIRMIZI
olduğunu doğrula → dosyayı GERİ YÜKLE.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")



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
    raw_text = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw_text
    text = raw_text.replace("\r\n", "\n")
    if current not in text:
        print(f"!! {name}: hedef metin bulunamadi ({rel_path})")
        shutil.copy2(backup, path)
        return False
    new_text = text.replace(current, reverted, 1)
    if crlf:
        new_text = new_text.replace("\n", "\r\n")
    path.write_text(new_text, encoding="utf-8")
    code, out = run_tests(target)
    shutil.copy2(backup, path)
    ok = code != 0
    print(f"{'PASS' if ok else 'FAIL'} - {name}")

    print(f"      test: {target}")
    print(f"      revert sonrası pytest exit: {code} (beklenen: !=0)")
    if not ok:
        print(out)
    return ok


def main() -> int:
    results: list[bool] = []

    # 1) Kanıt tipi ayrımı — web dosyası snippet'ı `posts` alanına yazar
    results.append(revert_step(
        "P0-1 kanıt tipi: snippet 'gönderi' olarak yazılmaz",
        "tests/unit/test_p0_honest_status.py::test_web_dossier_never_marks_snippets_as_posts",
        "backend/services/web_dossier.py",
        current='''        "posts": [],
        "post_times": [],
        "posts_meta": [],
        "post_types": [],
        "post_evidence_types": [],
        "search_snippets": snippets,''',
        reverted='''        "posts": [s["text"] for s in snippets],
        "post_times": [],
        "posts_meta": [],
        "post_types": ["text" for _ in snippets],
        "post_evidence_types": [],
        "search_snippets": snippets,''',
    ))

    # 2) X sensörü — boş havuzda `no_session_pool` yerine `user_not_found`
    results.append(revert_step(
        "P0-2 X sensörü: boş havuz -> no_session_pool",
        "tests/unit/test_p0_honest_status.py::test_x_sensor_reports_no_session_pool_not_user_not_found",
        "agent_core/capabilities/adapters_sensors.py",
        current='''            pool_state = await _x_pool_state(api)
            if pool_state is not None and pool_state["accounts_active"] == 0:''',
        reverted='''            pool_state = await _x_pool_state(api)
            if False:''',
    ))

    # 3) UI yalan metni — "sosyal profil ve açık veri bağlandı"
    results.append(revert_step(
        "P0-3 UI: 'bağlandı' yalanı geri geliyor",
        "tests/unit/test_p0_honest_status.py::test_ui_does_not_claim_profiles_were_linked",
        "frontend/src/components/TacticalWarRoom.svelte",
        current="""        const parts: string[] = [];""",
        reverted="""        const parts: string[] = [];
        return `${detectedUrls.length} sosyal profil ve açık veri bağlandı`;""",
    ))

    # 4) Telemetri — `capabilities` tablosu kaldırılıyor
    results.append(revert_step(
        "P0-4 telemetri: capabilities[].reason kaynağı",
        "tests/unit/test_p0_honest_status.py::test_telemetry_payload_has_capabilities_and_x_reason",
        "backend/routes/telemetry.py",
        current='''            "capabilities": capabilities,''',
        reverted='''            "capabilities": [],''',
    ))

    # 5) accounts.db kirliliği — DB yolu tekrar depo köküne
    results.append(revert_step(
        "P0-5 accounts.db: DB yolu yeniden yapılandırılamaz",
        "tests/unit/test_p0_honest_status.py::test_x_accounts_db_path_is_configurable_and_not_repo_root",
        "agent_core/capabilities/adapters_sensors.py",
        current='''    configured = (os.getenv(_X_ACCOUNTS_DB_ENV) or "").strip()
    path = configured or _X_ACCOUNTS_DB_DEFAULT''',
        reverted='''    configured = ""
    path = "accounts.db"''',
    ))

    # 6) Hüküm belgesi — koşmayan kanallar listelenmiyor
    results.append(revert_step(
        "P0-6 hüküm belgesi: koşmayan kanallar listelenmiyor",
        "tests/unit/test_p0_honest_status.py::test_verdict_digest_lists_channels_that_did_not_run",
        "agent_core/services/verdict_synthesizer.py",
        current='''    blocked = _blocked_channels(snap)
    if blocked:''',
        reverted='''    blocked = []
    if blocked:''',
    ))

    # 7) Rapor — koşmayan kanallar listelenmiyor
    results.append(revert_step(
        "P0-7 rapor: koşmayan kanallar listelenmiyor",
        "tests/unit/test_p0_honest_status.py::test_report_markdown_lists_channels_that_did_not_run",
        "agent_core/services/report_factory.py",
        current='''    blocked = [
        row for row in (channels or [])
        if isinstance(row, dict) and str(row.get("status") or "") in ("not_run", "failed")
    ]''',
        reverted='''    blocked = []''',
    ))

    print()
    passed = sum(1 for r in results if r)
    print(f"REVERT-DOĞRULAMA: {passed}/{len(results)} düzeltme geri alınınca KIRMIZIya döndü")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
