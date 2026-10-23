"""GÖLGE DENETİMİ betiğinin sözleşmesi — "hiçbir şey gölgede kalmasın" kilidi.

`scripts/golge_denetimi.py` ürünün TAMAMINI (yetenek defteri, ajanlar, HTTP
uçları, env kapıları, erişilebilirlik, gömülü varlıklar) ölçer ve raporu
`docs/reports/GOLGE_DENETIMI.md` + `reports/golge_denetimi.json` olarak yazar.

Bu test betiğin kendisini değil SÖZLEŞMESİNİ kilitler:

  * defterdeki HER yetenek için bir uyanma sınıfı vardır (``hazır`` /
    ``sadece_kapi`` / ``kurulum_gerekli``) — sınıfsız yetenek olamaz;
  * iki senaryo (şalterler kapalı / tüm şalterler açık) birlikte ölçülür;
    aksi hâlde "şalteri aç, biter" yanılgısı rapora sızar;
  * giriş noktalarından (AST ile) ulaşılamayan modül listesi üretilir —
    CLI araçları beyan edilmiş giriş noktası sayesinde yanlış "ölü kod"
    damgası yemez;
  * Markdown raporu bütün bölümleri içerir.

Test, rapordaki SAYILARI kilitlemez (ortam değişince bağımlılık sebepleri
değişir); yalnız yapının eksiksizliğini kilitler.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "golge_denetimi.py"


def _module():
    spec = importlib.util.spec_from_file_location("golge_denetimi", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_her_yetenek_uyanma_sinifi_tasir() -> None:
    data = _module().build()
    caps = data["yetenekler"]
    assert caps.get("error") is None, caps.get("error")
    assert caps["items"], "yetenek defteri boş olamaz"
    for cap in caps["items"]:
        assert cap["wake_class"] in {"hazır", "sadece_kapi", "kurulum_gerekli"}, cap
        #: Şalterler açıkken "hazır" olan bir yetenek "kurulum_gerekli" sınıfına düşemez.
        if cap["available_gates_open"]:
            assert cap["wake_class"] in {"hazır", "sadece_kapi"}, cap
        else:
            assert cap["wake_class"] == "kurulum_gerekli", cap


def test_uc_taramasi_ve_kapi_taramasi_bos_donmez() -> None:
    data = _module().build()
    assert data["uclar"]["count"] > 0
    assert data["kapilar"]["managed"], "yönetilen kapı listesi okunamadı"
    #: Kodda okunan ENABLE_* adları ölçülmeli; boş liste taramanın koptuğunu gösterir.
    assert data["kapilar"]["code_gates"]


def test_erisim_analizi_beyanli_giris_noktalarini_kullanir() -> None:
    data = _module().build()
    erisim = data["erisim"]
    assert erisim["entrypoints"]
    assert erisim["module_count"] > 0
    assert erisim["reachable_count"] <= erisim["module_count"]
    #: CLI aracı `run_lilith.py` beyan edilmiş giriş noktasıdır: onun ajanı
    #: "ölü kod" listesine düşmemelidir (yanlış alarm = güven kaybı).
    unreachable = {row["module"] for row in erisim["unreachable"]}
    assert "agent_core.agents.lilith_growth" not in unreachable


def test_markdown_raporu_butun_bolumleri_icerir() -> None:
    mod = _module()
    data = mod.build()
    md = mod.markdown(data)
    for baslik in (
        "# GÖLGE DENETİMİ",
        "## 1 · Yetenek defteri",
        "## 2 · Zincir",
        "## 3 · Ajanlar",
        "## 4 · HTTP uçları",
        "## 5 · Kapılar",
        "## 6 · Erişilemeyen modüller",
        "## 7 · Uyanma planı",
        "## 8 · Depoda duran gömülü varlıklar",
    ):
        assert baslik in md, f"rapor bölümü eksik: {baslik}"
