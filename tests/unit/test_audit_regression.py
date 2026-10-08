"""E0 · DENETİM REGRESYON BEKÇİSİNİN KENDİSİ DENETLENİYOR.

`scripts/audit_regression.py` denetim raporundaki 24 bulguyu makine bekçisine
çeviriyor. Bu dosya o bekçinin **yanlış yeşil üretemeyeceğini** kilitler — çünkü
bir bekçi yanlış yeşil üretebiliyorsa, yokluğundan daha tehlikelidir: kimse
artık arkasına bakmaz.

Kilitlenen dört sınıf:

1. **AYRIŞTIRMA TAMLIGI** — 24 bulgunun tamamı okunur; her bulgu TAM BİR
   kontrol alır (hayalet kontrol yok, kontrolsüz bulgu yok).
2. **KAPI ISIRIYOR MU** — `KNOWN_OPEN` boşaltılınca her açık bulgu regresyona
   dönüşür ve çıkış kodu 1 olur. Isırmayan kapı dekorasyondur.
3. **UYDURMA YASAĞI** — kanıtsız `closed` hükmü YAPILAMAZ (RuntimeError);
   `unverifiable` sınıfı yapısal olarak `closed`/`open` DÖNDÜREMEZ; test-kapılı
   bir bulgu ancak test dosyası GERÇEK işaretleri içeriyorsa kapanır (boş dosya
   yetmez).
4. **KONTROLLER KUSURLA ONARIMI AYIRT EDER** — sahte repo üzerinde: kusur
   varken `open`, onarım varken `closed`. Ayrıca bu bekçinin geliştirme
   sırasında DÜŞTÜĞÜ üç gerçek tuzak yeniden kilitlenir (çok satırlı kalıp ·
   yanlış `browser/open` eşleşmesi · yorumda geçen dolgu kalıbı).

Ayrıca: denetimin `DOĞRULA` kalıplarından ikisinin bugün **bayat** olduğu
kanıtlanır (E-GÖZ2-8 · E-GÖZ3-4). Bekçi kalıbı değil kusuru aradığı için bu
iki bulguyu doğru okur; kalıbı birebir koşsaydı yanlış hüküm verirdi.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_regression.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# `scripts/` bir paket DEĞİL (`__init__.py` yok) ve olmamalı: CI onu düz betik
# olarak koşuyor. Bu yüzden bekçi dosyadan doğrudan yüklenir — `from scripts …`
# gibi bir import, sys.path/paket varsayımına bağımlı kırılgan bir yol olurdu.
_spec = importlib.util.spec_from_file_location("audit_regression", SCRIPT)
assert _spec and _spec.loader
ar = importlib.util.module_from_spec(_spec)
# `sys.modules` kaydı ZORUNLU: betik `from __future__ import annotations` +
# `@dataclass` kullanıyor ve dataclasses, string annotation'ları çözmek için
# modülün __dict__'ine `sys.modules[cls.__module__]` üzerinden bakıyor. Kayıt
# olmadan yükleme `AttributeError: 'NoneType' object has no attribute '__dict__'`
# ile patlar (ölçüldü).
sys.modules[_spec.name] = ar
_spec.loader.exec_module(ar)

EXPECTED_IDS = {f"E-GÖZ{eye}-{n}" for eye in (1, 2, 3) for n in range(1, 9)}


@pytest.fixture(scope="module")
def findings():
    return ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return ar.build_report(ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8")))


# ─────────────────────────────────────────────────────────────────────────────
# 1) AYRIŞTIRMA TAMLIGI
# ─────────────────────────────────────────────────────────────────────────────
def test_parser_extracts_all_24_findings(findings):
    assert len(findings) == 24
    assert {f.fid for f in findings} == EXPECTED_IDS


def test_every_finding_carries_its_audit_fields(findings):
    """Raporun alanları kayba uğramadan taşınır (uydurma doldurma yok)."""
    for f in findings:
        for label in ("ELEŞTİRİ", "YER", "KANIT", "ETKİ", "ÇÖZÜM", "BOYUT", "KAZANÇ", "DOĞRULA"):
            assert f.fields.get(label), f"{f.fid}: {label} alanı boş/eksik"
        assert f.severity in {"YÜKSEK", "ORTA", "DÜŞÜK"}, f"{f.fid}: {f.severity}"
        assert f.eye in (1, 2, 3)


def test_no_ghost_findings_invented(findings):
    """Bekçi raporda OLMAYAN bir bulgu icat edemez."""
    raw = ar.AUDIT_REPORT.read_text(encoding="utf-8")
    for f in findings:
        assert f"### {f.fid}" in raw, f"{f.fid} raporda yok — hayalet kayıt"


def test_check_registry_covers_exactly_the_parsed_findings(findings):
    """İki yönde birebir: hayalet kontrol yok, kontrolsüz bulgu yok."""
    assert set(ar.CHECKS) == {f.fid for f in findings}
    # build_report aynı kuralı çalışma zamanında da zorlar.
    rep = ar.build_report(findings)
    assert set(rep["findings"]) == EXPECTED_IDS


def test_every_check_kind_is_from_the_closed_vocabulary():
    for fid, check in ar.CHECKS.items():
        assert check.kind in ar.CHECK_KINDS, fid
        assert check.fid == fid, "kayıt anahtarı ile kontrolün kimliği ayrışmış"


def test_report_shape_is_machine_readable(report):
    meta = report["meta"]
    assert meta["finding_count"] == 24
    assert sum(meta["counts"].values()) == 24
    for fid, entry in report["findings"].items():
        assert entry["status"] in {ar.CLOSED, ar.CLOSED_BY_DESIGN, ar.OPEN, ar.UNVERIFIABLE}, fid
        assert isinstance(entry["evidence"], list) and entry["evidence"], fid
        assert entry["check_kind"] in ar.CHECK_KINDS, fid


# ─────────────────────────────────────────────────────────────────────────────
# 2) KAPI ISIRIYOR MU
# ─────────────────────────────────────────────────────────────────────────────
def test_baseline_gate_passes_today(report):
    """Taban çizgisi gerçekle birebir: ne regresyon ne bayat kayıt."""
    assert report["meta"]["regressions"] == []
    assert report["meta"]["stale_known_open"] == []
    assert report["meta"]["gate_passed"] is True


def test_known_open_matches_the_measured_open_set_exactly(report):
    """KNOWN_OPEN ne iyimser ne karamsar — ölçülen açık kümeyle BİREBİR.

    Bu test iki yönde de ısırır: bir bulgu onarılıp listeden çıkarılmazsa
    (bayat) ya da yeni bir kusur listeye yazılmadan geçerse (regresyon) kırmızı.
    """
    measured_open = {
        fid for fid, e in report["findings"].items() if e["status"] == ar.OPEN
    }
    assert set(ar.KNOWN_OPEN) == measured_open
    # Listedeki her kayıt gerçekten açık olmalı (karamser şişirme yok).
    for fid in ar.KNOWN_OPEN:
        assert report["findings"][fid]["status"] == ar.OPEN, fid


def test_gate_bites_when_known_open_is_emptied(report, monkeypatch):
    """Isırmayan kapı dekorasyondur: liste boşaltılınca her açık bulgu regresyon.

    [GÜNCELLEME 2026-10-08] Eski sürüm gerçek açık bulgu sayısını (>=10) pine
    bağlardı; bulgular onarıldıkça bu snapshot bayatlardı. Kapının ısırırlığı
    artık SENTETİK açık bulguyla kanıtlanır — gerçek açık sayısı kaç olursa olsun.
    """
    monkeypatch.setattr(
        ar,
        "CHECKS",
        {
            **ar.CHECKS,
            "E-GÖZ1-2": ar.Check(
                "E-GÖZ1-2", "static", lambda: ar.CheckResult(ar.OPEN, ("sentetik açık bulgu",))
            ),
        },
    )
    monkeypatch.setattr(ar, "KNOWN_OPEN", frozenset())
    rep = ar.build_report(ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8")))
    assert "E-GÖZ1-2" in rep["meta"]["regressions"]
    assert rep["meta"]["gate_passed"] is False


def test_gate_flags_a_single_new_regression(monkeypatch):
    """Tek bir bulgunun açılması listede yoksa yakalanır."""
    victim = "E-GÖZ1-2"  # bugün kapalı
    trimmed = ar.KNOWN_OPEN  # kapalı bulgu listede değil
    assert victim not in trimmed
    monkeypatch.setattr(
        ar, "CHECKS", {**ar.CHECKS, victim: ar.Check(victim, "static", lambda: ar.CheckResult(ar.OPEN, ("sahte açılma",)))}
    )
    rep = ar.build_report(ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8")))
    assert rep["meta"]["regressions"] == [victim]
    assert rep["meta"]["gate_passed"] is False


def test_gate_flags_a_stale_baseline_entry(monkeypatch):
    """Onarılan bulgu listede bırakılırsa 'bayat taban' olarak yakalanır.

    [GÜNCELLEME 2026-10-08] Eski sürüm sabit `E-GÖZ1-1` victim'ini açık ve listede
    sanıyordu; bulgu onarılınca test kendi kendine kırılırdı. Senaryo şimdi
    KAPALI bir bulgu (E-GÖZ1-2) listeye konularak üretilir — taban çizgisi temiz
    kalsa da bayat kayıt yakalanır.
    """
    victim = "E-GÖZ1-2"  # bugün kapalı
    assert victim not in ar.KNOWN_OPEN  # gerçek taban çizgisi temiz
    monkeypatch.setattr(ar, "KNOWN_OPEN", frozenset({victim}))
    rep = ar.build_report(ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8")))
    assert victim in rep["meta"]["stale_known_open"]
    assert rep["meta"]["gate_passed"] is False


def test_main_exit_code_is_zero_when_the_gate_passes():
    """Çıkış kodu hükmü taşır: gerçek depo bugün 0 dönmeli."""
    assert ar.main(["--quiet", "--no-write"]) == 0


def test_main_exit_code_is_one_on_regression(monkeypatch, tmp_path):
    """AÇIK bir bulgu taban çizgisinden çıkarılınca süreç gerçekten 1 döner.

    Bu test ayrı bir SÜREÇTE koşar: `ar.main` modülün kendi `ROOT`/`KNOWN_OPEN`
    değerlerini okur, yani test içi `monkeypatch` onu etkilemez. Sahte repo +
    boş taban çizgisi ile gerçek çıkış kodu ölçülür (ısırmayan kapı = dekor).
    """
    audit_text = ar.AUDIT_REPORT.read_text(encoding="utf-8")
    fake = tmp_path / "repo"
    (fake / "docs" / "reports").mkdir(parents=True)
    (fake / "docs" / "reports" / "JULES_DENETIM_2026-10-06.md").write_text(
        audit_text, encoding="utf-8"
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import importlib.util, pathlib, sys\n"
        f"spec = importlib.util.spec_from_file_location('ar', r'{SCRIPT}')\n"
        "ar = importlib.util.module_from_spec(spec)\n"
        "sys.modules['ar'] = ar\n"
        "spec.loader.exec_module(ar)\n"
        # Modül sabitleri import anında SCRIPT konumundan türer; bu yüzden
        # exec_module'dan SONRA atanır (önce atamak işe yaramaz, üzerine yazılır).
        f"ar.ROOT = pathlib.Path(r'{fake}')\n"
        "ar.AUDIT_REPORT = ar.ROOT / 'docs' / 'reports' / 'JULES_DENETIM_2026-10-06.md'\n"
        "ar.REPORT_OUT = ar.ROOT / 'reports' / 'audit_regression.json'\n"
        # Kontroller sahte depoda gerçek dosya bulamaz; bekçi SÖZLEŞMESİ
        # (durum + kanıt + exit code) ölçüldüğü için kontrollü sahte sonuçlar
        # enjekte edilir: 2 bulgu açık, 1'i kapalı.
        "ar.CHECKS = {\n"
        "    fid: (ar.Check(fid, 'static', lambda f=fid: ar.CheckResult(ar.OPEN, (f + ' açıldı',)))\n"
        "          if fid in ('E-GÖZ1-1', 'E-GÖZ1-2')\n"
        "          else ar.Check(fid, 'static', lambda f=fid: ar.CheckResult(ar.CLOSED, (f + ' kapalı',))))\n"
        "    for fid in ar.CHECKS\n"
        "}\n"
        # Taban çizgisi YALNIZ bir açığı kapsıyor → diğeri regresyon olmalı.
        "ar.KNOWN_OPEN = frozenset({'E-GÖZ1-1'})\n"
        "raise SystemExit(ar.main(['--quiet', '--no-write']))\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(driver)], cwd=tmp_path, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 1, (
        f"beklenen 1 (regresyon), gelen {proc.returncode}\n"
        + proc.stdout[-2_000:]
        + proc.stderr[-2_000:]
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3) UYDURMA YASAĞI
# ─────────────────────────────────────────────────────────────────────────────
def test_closed_verdict_without_evidence_is_impossible():
    """Kanıtı olmayan 'kapandı' hükmü kurulamaz (boş, whitespace, boş liste)."""
    for evidence in ((), ("",), ("   ", "\t")):
        with pytest.raises(ar.AuditGuardError):
            ar.CheckResult(ar.CLOSED, evidence)
    with pytest.raises(ar.AuditGuardError):
        ar.CheckResult(ar.OPEN, ())
    with pytest.raises(ar.AuditGuardError):
        ar.CheckResult("kapandi", ("kanıt var",))  # bilinmeyen durum adı


def test_unverifiable_checks_structurally_cannot_claim_closed():
    """'Ölçemedim ama kapalı' kaçışı tür seviyesinde kapalı."""
    for forbidden in (ar.CLOSED, ar.CLOSED_BY_DESIGN, ar.OPEN):
        check = ar.Check(
            "E-GÖZ9-9",
            "unverifiable",
            lambda f=forbidden: ar.CheckResult(f, ("cargo bu ortamda yok",)),
        )
        with pytest.raises(ar.AuditGuardError):
            check.run()


def test_all_unverifiable_findings_report_unverifiable(report):
    unverifiable = [f for f, c in ar.CHECKS.items() if c.kind == "unverifiable"]
    assert unverifiable, "hiç doğrulanamaz bulgu yok — bu rapor için inanılır değil"
    for fid in unverifiable:
        assert report["findings"][fid]["status"] == ar.UNVERIFIABLE, fid
        joined = " ".join(report["findings"][fid]["evidence"])
        # Ölçülememe sebebi SOMUT olmalı: hangi araç yok, otorite kim.
        assert "cargo" in joined or "pytest" in joined, fid


def test_test_gated_closure_requires_real_markers_not_an_empty_file(tmp_path, monkeypatch):
    """Boş bir test dosyası 'kapandı' demek için yetmez — işaretler aranır."""
    tests_dir = tmp_path / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_fake.py").write_text("# boş dosya: hiçbir iddia yok\n", encoding="utf-8")
    monkeypatch.setattr(ar, "ROOT", tmp_path)

    locked, evidence = ar._test_lock("tests/unit/test_fake.py", ("EXPECTED_EXEMPT_FILES",))
    assert locked is False
    assert any("EKSİK" in e or "eksik işaret" in e for e in evidence)


def test_no_closed_finding_relies_on_a_missing_test_file(report):
    """Test-kapılı her 'kapandı' hükmünün dosyası GERÇEKTEN diskte olmalı."""
    for fid, entry in report["findings"].items():
        if entry["status"] in (ar.CLOSED, ar.CLOSED_BY_DESIGN) and entry["check_kind"] == "test_gated":
            joined = " ".join(entry["evidence"])
            paths = re.findall(r"tests/[A-Za-z0-9_/.-]+\.py", joined)
            assert paths, f"{fid}: kanıtında test dosyası adı yok"
            for rel in set(paths):
                assert (ROOT / rel).exists(), f"{fid}: kanıt gösterdiği dosya yok → {rel}"


def test_guard_rejects_ghost_and_missing_checks(findings):
    """build_report iki yönde de hayaleti reddeder."""
    ghost = dict(ar.CHECKS)
    ghost["E-GÖZ9-9"] = ar.Check("E-GÖZ9-9", "static", lambda: ar.CheckResult(ar.OPEN, ("x",)))
    with pytest.raises(ar.AuditGuardError, match="hayalet"):
        original = ar.CHECKS
        try:
            ar.CHECKS = ghost  # type: ignore[assignment]
            ar.build_report(findings)
        finally:
            ar.CHECKS = original  # type: ignore[assignment]

    trimmed = {k: v for k, v in ar.CHECKS.items() if k != "E-GÖZ1-1"}
    original = ar.CHECKS
    try:
        ar.CHECKS = trimmed  # type: ignore[assignment]
        with pytest.raises(ar.AuditGuardError, match="kontrolsüz"):
            ar.build_report(findings)
    finally:
        ar.CHECKS = original  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# 4) KONTROLLER KUSURLA ONARIMI AYIRT EDER (sahte repo üzerinde)
# ─────────────────────────────────────────────────────────────────────────────
WORKER_DEFECT = '''\
import asyncio
import logging

logger = logging.getLogger("agent_worker")


async def run_worker(agent_id: str):
    tracker = None
    try:
        await asyncio.sleep(0)
    except asyncio.CancelledError:
        logger.info(f"[{agent_id}] Worker durduruluyor")
        if tracker:
            try:
                await tracker.set_wait(agent_id)
            except Exception:
                pass
        raise


async def _post(url):
    try:
        return await _send(url)
    except Exception:
        pass  # Backend yoksa sessizce devam
'''

#: Onarılmış sürüm — girintiye DUYARSIZ üretilir. İki `except Exception: pass`
#: bloğunun girintisi farklı (16 ve 20 boşluk); sabit metinle denemek
#: geliştirme sırasında iki kez sessizce başarısız oldu ve "onarım uygulanmadı"
#: sahte kırmızısı üretti. Bu yüzden onarım programatik ve doğrulanabilir.
WORKER_FIXED = re.sub(
    r"^([ \t]*)pass  # Backend yoksa sessizce devam$",
    r'\1logger.warning("Backend REST fallback failed", exc_info=True)',
    WORKER_DEFECT,
    flags=re.MULTILINE,
)
WORKER_FIXED = re.sub(
    r"^([ \t]*)except Exception:\n[ \t]*pass$",
    r'\1except Exception:\n\1    logger.error("set_wait failed on shutdown", exc_info=True)',
    WORKER_FIXED,
    flags=re.MULTILINE,
)


def test_fixture_itself_is_well_formed():
    """Fixture'ın kendisi de denetlenir: onarım gerçekten iki kusuru gidermeli.

    Bu test olmadan sabit metin kaymaları (örn. girinti) sessizce "onarım
    uygulanmadı" sahte kırmızısı üretir — geliştirme sırasında tam olarak bu
    oldu: 16 boşluk girintili `pass`, 12 boşlukla arandığı için değişmedi.
    """
    assert "Backend yoksa sessizce devam" in WORKER_DEFECT
    assert "Backend yoksa sessizce devam" not in WORKER_FIXED
    # İKİ sessiz yutma da gerçekten giderilmiş olmalı (biri kalkıp diğeri
    # kalırsa fixture "onarım" değil "kısmi değişiklik" olur ve testler
    # bekçinin kusurunu değil fixture'ın kusurunu ölçer).
    assert WORKER_DEFECT.count("except Exception:") == 2
    assert re.search(r"except Exception:\n[ \t]*pass", WORKER_DEFECT)
    assert not re.search(r"except Exception:\n[ \t]*pass", WORKER_FIXED)
    assert WORKER_FIXED.count("exc_info=True") == 2
    # Onarım, denetimin ÇÖZÜM maddesinde istediği şey olmalı (log + exc_info).
    assert "logger.warning" in WORKER_FIXED and "logger.error" in WORKER_FIXED


def _fake_root(tmp_path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_worker(tmp_path, monkeypatch):
    def build(content: str) -> Path:
        root = _fake_root(tmp_path, {"agent_core/workers/agent_worker.py": content})
        monkeypatch.setattr(ar, "ROOT", root)
        return root

    return build


def test_goz1_1_separates_defect_from_fix(fake_worker):
    fake_worker(WORKER_DEFECT)
    assert ar.check_goz1_1().status == ar.OPEN

    fake_worker(WORKER_FIXED)
    result = ar.check_goz1_1()
    assert result.status == ar.CLOSED, result.evidence


#: [GÜNCELLEME 2026-10-08] E-GÖZ1-6, 2026-10-07 işaretçi (beacon) tasarımı
#: öncesindeki eski sözleşmeye göre yazılmıştı (`tracker.set_wait` kapanışı).
#: İşaretçi artık ajan durumuna ASLA yazmaz (test-locked); kapanışta KENDİ
#: kanalına `alive=False` yayınlar. Bu fixture yeni sözleşmeyi taklit eder.
BEACON_DEFECT = '''\
import asyncio
import logging

logger = logging.getLogger("agent_worker")


async def run_worker(agent_id: str):
    bus = None
    try:
        await asyncio.sleep(0)
    except asyncio.CancelledError:
        logger.info(f"[{agent_id}] Worker durduruluyor")
        try:
            await bus.publish("pineal:agent:beacon", {"beacon": {"alive": False}})
        except Exception:
            pass
        raise
'''

#: Onarılmış sürüm — kapanış yayınındaki sessiz `pass` log ile değiştirilir.
BEACON_FIXED = re.sub(
    r"^([ \t]*)except Exception:\n[ \t]*pass$",
    r'\1except Exception:\n\1    logger.warning("beacon kapanış yayını başarısız", exc_info=True)',
    BEACON_DEFECT,
    flags=re.MULTILINE,
)


def test_beacon_fixture_itself_is_well_formed():
    """İşaretçi fixture'ı da denetlenir: kusur gerçekten sessiz, onarım gerçekten loglu."""
    assert "except asyncio.CancelledError:" in BEACON_DEFECT
    assert '{"alive": False}' in BEACON_DEFECT
    assert re.search(r"except Exception:\n[ \t]*pass", BEACON_DEFECT)
    assert not re.search(r"except Exception:\n[ \t]*pass", BEACON_FIXED)
    assert BEACON_FIXED.count("exc_info=True") == 1
    assert "logger.warning" in BEACON_FIXED


def test_goz1_6_separates_defect_from_fix(fake_worker):
    fake_worker(BEACON_DEFECT)
    assert ar.check_goz1_6().status == ar.OPEN

    fake_worker(BEACON_FIXED)
    assert ar.check_goz1_6().status == ar.CLOSED


def test_goz1_6_flags_a_worse_regression_than_the_audit_found(fake_worker):
    """Kapanışta `alive=False` yayını hiç yoksa (daha beter) kontrol kör kalmaz."""
    no_publish = BEACON_DEFECT.replace(
        '''        try:
            await bus.publish("pineal:agent:beacon", {"beacon": {"alive": False}})
        except Exception:
            pass
''',
        "",
    )
    fake_worker(no_publish)
    result = ar.check_goz1_6()
    assert result.status == ar.OPEN
    assert "yayını yok" in " ".join(result.evidence)


def test_goz3_2_detects_the_production_gate_when_added(fake_worker):
    fake_worker(WORKER_DEFECT)
    assert ar.check_goz3_2().status == ar.OPEN

    gated = WORKER_DEFECT.replace(
        "import asyncio",
        'import asyncio\nimport os\n\n_PINEAL_ENV = os.getenv("PINEAL_ENV", "development")',
    ).replace(
        "        pass  # Backend yoksa sessizce devam",
        '        if _PINEAL_ENV == "production":\n            raise RuntimeError("Redis zorunlu")',
    )
    fake_worker(gated)
    assert ar.check_goz3_2().status == ar.CLOSED


def test_goz1_3_detects_spine_migration(tmp_path, monkeypatch):
    """8 dosyalık bypass: bir dosya omurgaya alınınca sayı gerçekten düşer."""
    files = {
        f"agent_core/services/svc_{i}.py": "import httpx\n" for i in range(8)
    }
    _fake_root(tmp_path, files)
    monkeypatch.setattr(ar, "ROOT", tmp_path)

    result = ar.check_goz1_3()
    assert result.status == ar.OPEN
    assert "8 dosya" in " ".join(result.evidence)

    # Bir dosya omurgaya alındı (satır başı import kalktı).
    (tmp_path / "agent_core/services/svc_0.py").write_text(
        "from agent_core.capabilities.runner import run_capability\n", encoding="utf-8"
    )
    result = ar.check_goz1_3()
    assert result.status == ar.OPEN
    assert "7 dosya" in " ".join(result.evidence)

    for i in range(1, 8):
        (tmp_path / f"agent_core/services/svc_{i}.py").write_text(
            "from agent_core.capabilities.runner import run_capability\n", encoding="utf-8"
        )
    assert ar.check_goz1_3().status == ar.CLOSED


def test_goz2_3_needs_a_real_gate_not_the_word_vault(tmp_path, monkeypatch):
    """UYDURMA YASAĞI'nın somut hâli: 'vault' kelimesi kapı demek değildir."""
    naive = (
        "def fetch():\n"
        "    # X scraper.py ile aynı mimari: Playwright, vault'tan cookie\n"
        "    self.vault_cookies = {}\n"
    )
    _fake_root(tmp_path, {"agent_core/scraper/ghost.py": naive, "backend/api.py": "def _require_vault_open():\n    return None\n"})
    monkeypatch.setattr(ar, "ROOT", tmp_path)

    result = ar.check_goz2_3()
    assert result.status == ar.OPEN, "'vault' geçen dosya kapalı sayıldı — sahte pozitif"
    assert "sahte pozitif" in " ".join(result.evidence)

    gated = naive + "\ndef _preflight():\n    if get_vault_status()['locked']:\n        raise VaultLockedError()\n"
    (tmp_path / "agent_core/scraper/ghost.py").write_text(gated, encoding="utf-8")
    assert ar.check_goz2_3().status == ar.CLOSED


def test_goz3_4_counts_a_comment_as_record_not_as_live_defect(tmp_path, monkeypatch):
    """Geliştirme sırasında DÜŞÜLEN tuzak: yorumda geçen dolgu kalıbı.

    Kusuru anlatan açıklama yorumu canlı kusur değildir; ama aynı kalıp gerçek
    kodda duruyorsa bulgu açıktır. İki yön de kilitlenir.
    """
    # Kontrolün ölçtüğü GERÇEK dosya adı — farklı bir ad uydurmak testi sahte
    # kırmızıya boyar (geliştirme sırasında düşüldü, düzeltildi).
    rel = "frontend/src/components/AtlasPinealCockpit.svelte"
    commented = (
        "<script>\n"
        '  // Bulunan açık: modal alanları `|| "Veri mevcut değil"` benzeri dolgu ile\n'
        "  // şişirilmiş görünüyordu; kaldırıldı.\n"
        "  const INSUFFICIENT_EVIDENCE = 'YETERSİZ KANIT';\n"
        "  function hasEvidence(value: unknown): boolean {\n"
        "    return value !== null && value !== '';\n"
        "  }\n"
        "</script>\n"
        "<p>{#if hasEvidence(x)}{x}{:else}{INSUFFICIENT_EVIDENCE}{/if}</p>\n"
    )
    _fake_root(tmp_path, {rel: commented})
    monkeypatch.setattr(ar, "ROOT", tmp_path)
    assert ar.check_goz3_4().status == ar.CLOSED, "yorum canlı kusur sayıldı — sahte açık"

    live = commented.replace(
        "<p>{#if hasEvidence(x)}{x}{:else}{INSUFFICIENT_EVIDENCE}{/if}</p>",
        '<p>{x || "Veri mevcut değil"}</p>',
    )
    (tmp_path / rel).write_text(live, encoding="utf-8")
    result = ar.check_goz3_4()
    assert result.status == ar.OPEN, "canlı dolgu kalıbı yorum sanılıp atlandı"


def test_hits_matches_patterns_that_cross_line_boundaries(tmp_path, monkeypatch):
    """Çok satırlı kalıp tuzağı: `except Exception:\\n  pass` tek satırda yok."""
    rel = "agent_core/x.py"
    _fake_root(tmp_path, {rel: "try:\n    a()\nexcept Exception:\n    pass\n"})
    monkeypatch.setattr(ar, "ROOT", tmp_path)

    assert ar._hits(rel, r"except Exception:\s*\n\s*pass"), "çok satırlı kalıp görülmedi"
    # Yorum/kod ayrımı satır bazlı kalmalı (DOTALL lookahead'i yenmemeli).
    _fake_root(
        tmp_path,
        {rel: '// açıklama: "Veri mevcut değil"\nx = 1\n'},
    )
    assert ar._code_hits(rel, r'["\']Veri mevcut değil["\']') == []


def test_goz2_5_finds_the_route_not_the_inventory_list(tmp_path, monkeypatch):
    """İkinci düşülen tuzak: yol adı dosyada iki kez geçer (envanter + route).

    İlk geçen yere bakmak 'kapı bağlı değil' sahte açığını üretiyordu.
    """
    rel = "backend/api.py"
    source = (
        'EGRESS = [\n    "/api/browser/open",\n]\n'
        + "# " + "dolgu " * 200 + "\n"
        + '@app.post("/api/browser/open")\nasync def browser_open(payload):\n'
        + "    if (locked := _require_vault_open(payload.client_id)) is not None:\n"
        + "        return locked\n    return {}\n"
        + "def _require_vault_open(client_id):\n    return None\n"
    )
    _fake_root(
        tmp_path,
        {rel: source, "tests/unit/test_vault_egress_lock.py": "423 VAULT_LOCKED YAPI DENETİMİ muafiyet"},
    )
    monkeypatch.setattr(ar, "ROOT", tmp_path)
    assert ar.check_goz2_5().status == ar.CLOSED, "envanter listesi route sanıldı"

    unwired = source.replace(
        "    if (locked := _require_vault_open(payload.client_id)) is not None:\n        return locked\n", ""
    )
    (tmp_path / rel).write_text(unwired, encoding="utf-8")
    assert ar.check_goz2_5().status == ar.OPEN, "kapısız route kapalı sayıldı"


# ─────────────────────────────────────────────────────────────────────────────
# 5) DENETİMİN `DOĞRULA` KALIPLARI BAYAT — bekçi kalıbı değil kusuru arar
# ─────────────────────────────────────────────────────────────────────────────
def test_goz2_8_audit_pattern_is_stale_but_the_finding_is_closed(findings, report):
    """Denetimin `grep -r 'minor_gate' backend/api.py` komutu yanlış hüküm verirdi."""
    entry = report["findings"]["E-GÖZ2-8"]
    assert entry["status"] == ar.CLOSED

    api_text = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    audit_hits = [
        line for line in api_text.splitlines() if re.search(r"(?i)minor_gate", line)
    ]
    real_hits = [line for line in api_text.splitlines() if "_require_minor_clearance" in line]
    # Denetimin kalıbı bugün yalnız ölçüm YORUMU bulur; gerçek kapı başka adla.
    assert all(line.strip().startswith("#") for line in audit_hits), (
        "denetim kalıbı artık gerçek kodu buluyor — bulgu metnini güncelle"
    )
    assert real_hits, "çocuk kilidi API sınırından kalkmış"
    assert entry["audit_verify_stale"], "bayat kalıp raporda belgelenmemiş"
    assert "_require_minor_clearance" in entry["audit_verify_stale"]

    finding = next(f for f in findings if f.fid == "E-GÖZ2-8")
    assert "minor_gate" in finding.verify  # denetimin yazdığı komut korunuyor


def test_goz3_4_audit_pattern_survives_only_as_a_record(report):
    entry = report["findings"]["E-GÖZ3-4"]
    assert entry["status"] == ar.CLOSED
    assert entry["audit_verify_stale"]
    svelte = (ROOT / "frontend/src/components/AtlasPinealCockpit.svelte").read_text(encoding="utf-8")
    assert "INSUFFICIENT_EVIDENCE" in svelte
    assert "YETERSİZ KANIT" in svelte
    # Canlı dolgu kalıbı yok: yorum olmayan hiçbir satırda geçmez.
    live = [
        line
        for line in svelte.splitlines()
        if "Veri mevcut değil" in line and not line.strip().startswith("//")
    ]
    assert live == [], f"canlı UI dolgusu geri gelmiş: {live}"


def test_findings_with_stale_audit_patterns_are_declared(report):
    """Kalıbı bayatlayan her bulgu bunu raporda AÇIKÇA beyan eder (halı altı yok)."""
    declared = {
        fid for fid, e in report["findings"].items() if e["audit_verify_stale"]
    }
    assert {"E-GÖZ2-8", "E-GÖZ3-4"} <= declared, sorted(declared)


# ─────────────────────────────────────────────────────────────────────────────
# 6) CI + rapor bağlama
# ─────────────────────────────────────────────────────────────────────────────
def test_ci_runs_the_guard_as_a_gate():
    """Bekçi CI'da bir ADIM olarak koşmalı — yoksa yerel bir oyuncaktır.

    Adım YAPISAL olarak aranır (ad + gövde aynı blokta), çünkü "workflow'da adı
    geçiyor" tek başına yetmez: bir yorum satırında da geçebilirdi. Gövde,
    YAML blok skalerini (`run: |`) de tek satırlı `run:` biçimini de kapsar.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/audit_regression.py" in text, "bekçi CI'ya bağlı değil"

    step = re.search(
        r"- name: (?P<name>[^\n]*[Aa]udit[^\n]*)\n"
        r"(?:[ \t]+#[^\n]*\n)*"  # adım ile run arasındaki açıklama yorumları
        r"[ \t]+run: (?P<run>.?)(?P<body>(?:\n[ \t]+[^\n]*)*)",
        text,
    )
    assert step, "bekçi adımı yapısal olarak bulunamadı (name + run aynı blokta)"
    body = (step.group("run") or "") + (step.group("body") or "")
    assert "scripts/audit_regression.py" in body, "adım var ama bekçiyi KOŞMUYOR"
    # Rapor tazeliği de denetlenmeli: üretilen JSON commit'lenenden sapamaz.
    assert "git diff" in body and "audit_regression.json" in body, (
        "rapor tazeliği CI'da kilitli değil"
    )
    # [SESSİZ-ÇÖKME-YOK] Actions logları her ortamdan okunamaz; başarısızlık
    # ayrıntısı annotation olarak yüzeye çıkmalı (repo kuralı, rust-core emsali).
    assert "::error title=" in body, "bekçi kırmızısı CI'da sessiz çöker"

    # Adım `backend` işinde olmalı: bağımlılık kurulumu orada yapılıyor.
    backend_job = text.split("  backend:", 1)[1].split("\n  frontend:", 1)[0]
    assert "audit_regression.py" in backend_job


def test_guard_script_is_pure_python_product_path():
    """Saflık kuralı: `scripts/*.py` içinde alt-çizgili Rust kaynak dizini adı geçemez.

    Bu bekçi geliştirilirken kurala takıldı; atıf CI **işinin adıyla** (tire ile)
    yapılır. Kuralı esnetmek yerine betik düzeltildi — kalıcı kilit burada.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "rust_" + "core" not in text, "Python ürün-yolu saflık kuralı ihlali"
    # Rust tarafına atıf gerekiyorsa CI işinin adıyla yapılır.
    assert "rust-core" in text
    # Ruhsat: betik Rust bulgularını glob ile ölçer, adı literal yazmaz.
    assert "rust_*/src/vault.rs" in text or "rust_*/tests/purity_scan.rs" in text


def test_written_report_is_valid_and_matches_stdout_gate(tmp_path):
    """`--json` çıktısı ile dosyaya yazılan rapor aynı hükmü taşır."""
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--no-write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert out.returncode == 0, out.stdout[-3_000:] + out.stderr[-3_000:]
    payload = json.loads(out.stdout)
    assert payload["meta"]["gate_passed"] is True
    assert payload["meta"]["finding_count"] == 24
    assert sum(payload["meta"]["counts"].values()) == 24


def test_report_is_deterministic_so_the_ci_diff_gate_is_meaningful():
    """Aynı kaynak → bayt bayt aynı JSON.

    CI adımı ``git diff --exit-code`` ile raporun tazeliğini denetliyor. Üretime
    anlık bir damga karışsaydı dosya HER koşuda değişir, adım sürekli kırmızı
    yanar ve gerçek regresyon gürültüye boğulurdu. Bu geliştirme sırasında
    yakalanan gerçek bir kusurdu; kalıcı kilidi burada.
    """
    first = json.dumps(ar.build_report(_fresh_findings()), ensure_ascii=False, sort_keys=True)
    second = json.dumps(ar.build_report(_fresh_findings()), ensure_ascii=False, sort_keys=True)
    assert first == second
    assert "source_stamp" in json.loads(first)["meta"]
    # Damga "şimdi" değil, KAYNAĞIN mührüdür.
    stamp = json.loads(first)["meta"]["source_stamp"]
    assert stamp.startswith("sha256:"), stamp


def test_stamp_follows_content_not_the_environment(tmp_path, monkeypatch):
    """Damga git derinliğinden, saat diliminden ve mtime'dan BAĞIMSIZ olmalı.

    Bu, CI'da gerçekten kırmızı üreten bir kusurdu (run 37585688805 · adım 7):
    Actions sığ klon yaptığı için `git log -1 --format=%cI` commit tarihini KOŞU
    ZAMANINA eşitliyordu ve checkout mtime'ı her ortamda farklıydı. Aynı içerik
    iki farklı damga üretince `git diff` kapısı "bayat rapor" diye yanıyordu —
    üstelik Actions logları okunamadığı için sebep de görünmüyordu.
    """
    fake = tmp_path / "repo"
    (fake / "docs" / "reports").mkdir(parents=True)
    report_path = fake / "docs" / "reports" / "JULES_DENETIM_2026-10-06.md"
    report_path.write_text("sürüm A\n", encoding="utf-8")
    monkeypatch.setattr(ar, "AUDIT_REPORT", report_path)

    first = ar._source_stamp()
    # Yalnız mtime değişir (içerik aynı) → damga DEĞİŞMEMELİ.
    os.utime(report_path, (0, 0))
    assert ar._source_stamp() == first, "damga mtime'a bağlı — CI'da sahte bayatlık üretir"
    # İçerik değişir → damga DEĞİŞMELİ (mühür kaynağı gerçekten izler).
    report_path.write_text("sürüm B\n", encoding="utf-8")
    assert ar._source_stamp() != first, "damga içeriği izlemiyor — mühür sahte"
    assert ar._source_stamp().startswith("sha256:")


def test_stamp_is_never_invented_when_the_source_is_unreadable(tmp_path, monkeypatch):
    """Kaynak okunamıyorsa damga UYDURULMAZ; mühürsüzlük açıkça görünür."""
    monkeypatch.setattr(ar, "AUDIT_REPORT", tmp_path / "yok.md")
    stamp = ar._source_stamp()
    assert stamp.startswith("unreadable-source:"), stamp
    assert not stamp.startswith("sha256:")


#: Rapor determinizmini bozan çevresel izler. İkisi de CI'da GERÇEK kırmızı
#: üretti: mutlak araç yolu (`/home/runner/.cargo/bin/cargo` — GitHub imajında
#: Rust kurulu, sandbox'ta değil) ve ortama özgü anlatım.
ENVIRONMENT_LEAKS = (
    "/home/",
    "/usr/",
    "/tmp/",
    "C:\\",
    "sandbox",
)


def test_committed_report_carries_no_machine_specific_trace(report):
    """Commit'lenen rapor HANGİ makinede üretildiğini ele veremez.

    Bu kural iki CI kırmızısının ortak köküydü ve ikincisini ancak annotation
    sayesinde okuyabildik. Bekçinin hükmü kaynak koddan türer; makineden değil.
    Tarama betik KAYNAĞINI da kapsar: kanıt dizeleri oradan kopyalandığı için
    kaynak temizse rapor da temizdir (tek istisna, bu kusurun tarihçesini
    anlatan belge dizesi — `shutil.which` anması bir ölçüm değil, kayıttır).
    """
    blob = json.dumps(report, ensure_ascii=False)
    for leak in ENVIRONMENT_LEAKS:
        assert leak not in blob, f"raporda makine izi sızıyor: {leak!r}"

    source = SCRIPT.read_text(encoding="utf-8")
    history_line = "shutil.which"  # kusurun tarihçesini anlatan tek belge dizesi
    for leak in ENVIRONMENT_LEAKS:
        offenders = [
            line
            for line in source.splitlines()
            # Muaf: shebang (`#!/usr/bin/env python3`) bir ortam izi değil,
            # çalıştırılabilir betiğin yorumlayıcı bildirimi — CI'ın `python
            # scripts/...` çağrısı da ona dayanmaz. Bu muafiyet olmadan test
            # kendi sahte pozitifini üretiyor (ölçüldü).
            if leak in line
            and history_line not in line
            and not line.startswith("#!")
        ]
        assert not offenders, f"betik kaynağında makine izi: {leak!r} → {offenders[:2]}"


def test_unverifiable_status_does_not_depend_on_the_local_toolchain(report, monkeypatch, tmp_path):
    """"Doğrulanamaz" hükmü araç zincirinin burada olup olmamasına bağlanamaz.

    GitHub `ubuntu-latest` imajı Rust'ı KURULU getirir; geliştirme ortamı
    getirmiyor. Hüküm ikisinde de aynı kalmalı — aksi hâlde rapor makineye göre
    değişir ve tazelik kapısı anlamsızlaşır.

    Ölçüm SAHTE `PATH` ile yapılır (içi boş bir mock değil): bir uçta PATH
    tamamen boşaltılır, diğer uçta sahte ama ÇALIŞAN bir `cargo`/`rustc`
    konur. Bekçi ikisinde de bayt bayt aynı raporu üretmeli — çünkü artık araç
    zincirini HİÇ sorgulamıyor (sorgulamak raporu makineye bağlardı).
    """
    before = json.dumps(report, ensure_ascii=False, sort_keys=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("cargo", "rustc"):
        stub = bin_dir / tool
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    monkeypatch.setenv("PATH", str(bin_dir))
    with_tool = json.dumps(
        ar.build_report(_fresh_findings()), ensure_ascii=False, sort_keys=True
    )
    monkeypatch.setenv("PATH", str(tmp_path / "bos"))
    without_tool = json.dumps(
        ar.build_report(_fresh_findings()), ensure_ascii=False, sort_keys=True
    )

    assert with_tool == without_tool, "rapor araç zincirine göre değişiyor"
    assert with_tool == before, "rapor PATH'e göre değişiyor (CI'da sahte bayatlık)"
    unverifiable = [f for f, e in report["findings"].items() if e["check_kind"] == "unverifiable"]
    assert unverifiable, "doğrulanamaz bulgu yok — test anlamsız"


def _fresh_findings():
    return ar.parse_findings(ar.AUDIT_REPORT.read_text(encoding="utf-8"))


def test_committed_report_is_fresh():
    """Depoya yazılan rapor bayat olamaz: bekçi yeniden koşunca aynı hüküm çıkar."""
    path = ROOT / "reports" / "audit_regression.json"
    assert path.exists(), "rapor depoya yazılmamış"
    committed = json.loads(path.read_text(encoding="utf-8"))
    fresh = ar.build_report(_fresh_findings())
    for fid, entry in fresh["findings"].items():
        assert committed["findings"][fid]["status"] == entry["status"], fid
    assert committed["meta"]["counts"] == fresh["meta"]["counts"]
    assert committed["meta"]["gate_passed"] is fresh["meta"]["gate_passed"]
