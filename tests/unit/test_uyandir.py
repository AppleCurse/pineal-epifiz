"""`scripts/uyandir.py` sözleşmesi — "kapıyı açmak = çalıştırmak" yanılgısını kilitler.

Bu betik, kullanıcıya "hepsini açalım" dediğinde NE OLACAĞINI önceden söyler.
Kilitlenen davranışlar:

  * üç uyanma sınıfı (``hazır`` / ``sadece_kapi`` / ``kurulum_gerekli``)
    ölçümün kendisinden türetilir — "şimdi" ölçümü env DEĞİŞTİRİLMEDEN alınır;
  * ``guvenli`` grubu YALNIZ şalteri açınca gerçekten uyanan yeteneklerin
    kapılarını seçer (kurulum isteyenlerin kapısı boşuna açılmaz);
  * ``hepsi`` yönetilen kapıların tamamıdır;
  * bilinmeyen kapı adı sessizce yok sayılmaz — gürültülü hata;
  * ``write_env`` mevcut `.env` satırlarını ve hizalanmış yorumları korur,
    eksik kapıyı ekler, yedek alır.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "uyandir.py"


def _module():
    spec = importlib.util.spec_from_file_location("uyandir", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_uyanma_siniflari_ve_olcum_sirasi() -> None:
    mod = _module()
    rows, managed = mod.measure()
    assert rows and managed
    assert {r["kclass"] for r in rows} <= {"hazır", "sadece_kapi", "kurulum_gerekli"}
    for row in rows:
        if row["kclass"] == "hazır":
            assert row["reason_now"] is None, row
        if row["kclass"] == "sadece_kapi":
            #: "şimdi" kapalı olmalı: env değiştirilmeden ölçüldüğünün kanıtı.
            assert row["reason_now"] is not None, row
            assert row["reason_open"] is None, row
        if row["kclass"] == "kurulum_gerekli":
            assert row["reason_open"] is not None, row


def test_guvenli_grup_yalniz_kapi_ile_uyananlari_secer() -> None:
    mod = _module()
    rows, managed = mod.measure()
    flags = mod.select_flags(rows, managed, "guvenli")
    assert set(flags) <= set(managed)
    wake_by_gate = {g for row in rows if row["kclass"] == "sadece_kapi" for g in row["gates"]}
    assert set(flags) == wake_by_gate
    #: KİLİTLENEN GERÇEK: kapılar PAYLAŞILIR (ör. `ENABLE_REPORT_FACTORY`
    #: pdf+diyagramı uyandırır, videoyu uyandırmaz — ffmpeg yok). Yani bir
    #: kapıyı açmak gruptaki HER yeteneği açtığını iddia etmez; bu yüzden
    #: rapor "açıldı" demez, "şalter açıldı ama şu sebeple hâlâ kapalı" der.
    shared = [
        row for row in rows
        if row["kclass"] == "kurulum_gerekli" and set(row["gates"]) & set(flags)
    ]
    for row in shared:
        assert row["reason_open"], row  # sessizce "açıldı" sayılmaz, sebebi raporlanır



def test_hepsi_ve_bilinmeyen_kapi() -> None:
    mod = _module()
    rows, managed = mod.measure()
    assert mod.select_flags(rows, managed, "hepsi") == sorted(managed)
    with pytest.raises(SystemExit):
        mod.select_flags(rows, managed, "ENABLE_YOK_BOYLE_BIR_SEY")


def test_write_env_yorumlari_korur_ve_eksik_kapiyi_ekler(tmp_path: Path) -> None:
    mod = _module()
    env = tmp_path / ".env"
    env.write_text(
        "ENABLE_MAIGRET=false            # kimlik taramasi\n"
        "OTHER_SETTING=deger\n",
        encoding="utf-8",
    )
    path, backup, added = mod.write_env(["ENABLE_MAIGRET", "ENABLE_HOLEHE"], path=env)
    text = path.read_text(encoding="utf-8")
    assert "ENABLE_MAIGRET=true            # kimlik taramasi" in text, text
    assert "OTHER_SETTING=deger" in text
    assert "ENABLE_HOLEHE=true" in text
    assert added == ["ENABLE_HOLEHE"]
    assert backup is not None and backup.exists()
