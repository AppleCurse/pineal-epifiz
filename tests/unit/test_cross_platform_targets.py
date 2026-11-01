"""P10 · ÇAPRAZ PLATFORM HEDEF KABULÜ — Aspasia kapısı + profil yönlendirici.

Köken: PR #150 (dal `arena/1fb51980-pineal-epifiz`). O PR kapatıldı çünkü
özelliğin kendisi `main`'e doğrudan atılan `5e60a75` / `53729c8`
commit'leriyle zaten girmişti ve PR dalı kendi içinde kırıktı
(`agent_core/aspasia/interface.py` girinti hatası, `profile_router.py`
içinde art arda iki `_social_route` gövdesi). Bu dosya o PR'ın NİYETİNİ
korur — ama dalın kopyası üzerinden değil, bugünkü `main` API'si üzerinden.

Sözleşme:
1) TEK doğruluk kaynağı: Aspasia'nın hedef kapısı profil shape'ini
   ``profile_router.classify_url``'dan okur (Kural [009]); platform
   listesi Aspasia tarafında KOPYALANMAZ.
2) Bilinen sosyal profiller (IG/X sensörlü + çapraz platform tablosu)
   kabul edilir; IG/X kendi sensörüne, diğerleri
   ``extractor.identity.socid`` yeteneğine gider.
3) Shape dışı yollar, rezerv kelimeler, bakış-benzeri (lookalike) hostlar,
   ``http://`` ve bilinmeyen hostlar REDDEDİLİR — fail-closed; görev
   BAŞLAMAZ ve sebep makine-okunur raporlanır.
4) Kapı LLM'e bağlı değildir: niyet sahte gateway'den gelir, ağ YOK.

Bilinen açık (bu dosyada `xfail` ile işaretli, sessizce yutulmaz):
  * ``https://www.tiktok.com/tag/dance`` → ana tablo "tag" rezervini
    platform-bazlı tutmadığı için profil sayılıyor.
  * ``https://t.me/s/kanal`` → ``main`` bunu kanalın herkese açık önizlemesi
    olarak profile bağlıyor; PR #150 tablosu reddediyordu.
"""

from __future__ import annotations

import contextlib

import pytest

from agent_core.aspasia.interface import AspasiaCommandGateway, AspasiaIntent
from agent_core.services.profile_router import (
    CAPABILITY_INSTAGRAM,
    CAPABILITY_SOCID,
    CAPABILITY_X,
    REASON_NOT_A_PROFILE,
    REASON_UNSUPPORTED,
    classify_url,
)

# ---------------------------------------------------------------- 1) kabul
# (url, beklenen handle) — her platformun kanonik profil biçimi.
ACCEPT = [
    ("https://www.instagram.com/nasa/", "nasa"),
    ("https://instagram.com/nasa", "nasa"),
    ("https://x.com/nasa", "nasa"),
    ("https://twitter.com/nasa", "nasa"),
    ("https://www.linkedin.com/in/nasa", "nasa"),
    ("https://www.linkedin.com/company/pineal", "pineal"),
    ("https://www.facebook.com/nasa", "nasa"),
    ("https://fb.com/nasa", "nasa"),
    ("https://www.tiktok.com/@nasa", "nasa"),
    ("https://www.youtube.com/@nasa", "nasa"),
    ("https://www.youtube.com/c/nasa", "nasa"),
    ("https://www.youtube.com/user/nasa", "nasa"),
    ("https://www.youtube.com/channel/UC1234567890abcdef", "UC1234567890abcdef"),
    ("https://www.threads.net/@nasa", "nasa"),
    ("https://github.com/torvalds", "torvalds"),
    ("https://www.reddit.com/user/nasa", "nasa"),
    ("https://www.pinterest.com/nasa/", "nasa"),
    ("https://www.twitch.tv/nasa", "nasa"),
    ("https://t.me/nasa", "nasa"),
    ("https://telegram.me/nasa", "nasa"),
    ("https://medium.com/@nasa", "nasa"),
    ("https://vk.com/nasa", "nasa"),
    ("https://www.snapchat.com/add/nasa", "nasa"),
    ("https://steamcommunity.com/id/nasa", "nasa"),
    ("https://steamcommunity.com/profiles/76561198000000000", "76561198000000000"),
    ("https://www.behance.net/nasa", "nasa"),
    ("https://dribbble.com/nasa", "nasa"),
    ("https://linktr.ee/nasa", "nasa"),
]

# --------------------------------------------------------------- 2) red
# (url, beklenen sebep) — fail-closed: kabul edilmemesi YAŞANIR.
REJECT = [
    # bakış-benzeri hostlar (N4 dersi — çapraz platform geneli)
    ("https://notinstagram.com/ornek", REASON_UNSUPPORTED),
    ("https://www.instagram.com.evil.com/ornek", REASON_UNSUPPORTED),
    ("https://evilinkedin.com/in/nasa", REASON_UNSUPPORTED),
    ("https://github.com.evil.example/torvalds", REASON_UNSUPPORTED),
    ("https://tiktok.co/@nasa", REASON_UNSUPPORTED),
    ("https://youtube.co/@nasa", REASON_UNSUPPORTED),
    # bilinmeyen host
    ("https://example.com/nasa", REASON_UNSUPPORTED),
    # profil OLMAYAN yollar (rezerv / shape dışı)
    ("https://www.instagram.com/p/CxYz123/", REASON_NOT_A_PROFILE),
    ("https://www.linkedin.com/", REASON_NOT_A_PROFILE),
    ("https://www.linkedin.com/in/", REASON_NOT_A_PROFILE),
    ("https://www.youtube.com/watch?v=abc123", REASON_NOT_A_PROFILE),
    ("https://www.youtube.com/c/", REASON_NOT_A_PROFILE),
    ("https://www.reddit.com/r/python", REASON_NOT_A_PROFILE),
    ("https://github.com/torvalds/linux", REASON_NOT_A_PROFILE),
    ("https://www.facebook.com/login", REASON_NOT_A_PROFILE),
    ("https://www.twitch.tv/directory", REASON_NOT_A_PROFILE),
    ("https://steamcommunity.com/id/", REASON_NOT_A_PROFILE),
]

# ------------------------------------------------ 3) bilinen açık (xfail)
# `main` bugün bunları KABUL ediyor; PR #150'nin platform-bazlı rezerv
# tablosu reddediyordu. Düzeltme yapılırsa test XPASS olur (strict=False,
# yani süiti kırmaz) ve buradaki işaret güncellenmelidir.
KNOWN_SHAPE_GAPS = [
    ("https://www.tiktok.com/tag/dance", "tiktok 'tag' rezervi platform-bazlı değil"),
    ("https://t.me/s/publicchannel", "t.me/s önizlemesi kanal olarak kabul ediliyor"),
]


@pytest.mark.parametrize("url,handle", ACCEPT)
def test_known_social_profile_routes_to_socid(url, handle):
    route = classify_url(url)
    assert route.runnable is True, f"{url} reddedildi: {route.reason}"
    assert route.handle == handle, f"{url} -> {route.handle!r}"
    # IG/X hariç tüm sosyal profiller identity extractor'ına gider.
    if route.platform in ("instagram", "x"):
        assert route.capability_id in (CAPABILITY_INSTAGRAM, CAPABILITY_X)
    else:
        assert route.capability_id == CAPABILITY_SOCID


@pytest.mark.parametrize("url,reason", REJECT)
def test_non_profile_or_lookalike_is_rejected_with_reason(url, reason):
    route = classify_url(url)
    assert route.runnable is False, f"{url} kabul edilmemeli"
    assert route.reason == reason, f"{url} -> {route.reason!r} (beklenen {reason!r})"


@pytest.mark.xfail(reason="[P10 devir] platform-bazlı rezerv tablosu yok", strict=False)
@pytest.mark.parametrize("url,note", KNOWN_SHAPE_GAPS)
def test_known_profile_shape_gaps(url, note):
    route = classify_url(url)
    assert route.runnable is False, f"{url} kabul edildi ({note})"


# ------------------------------------------- 4) Aspasia komut kapısı (gerçek)
class _IntentGW:
    """Niyet çıkarımını konserve `AspasiaIntent` ile döndüren sahte gateway.

    Ağ yok: kapı yalnız URL doğrular, LLM çağrısı taklit edilir.
    """

    def __init__(self, intent: AspasiaIntent) -> None:
        self._intent = intent

    def capture_calls(self, task_id, agent_id):  # noqa: D102 - protokol uyumu
        return contextlib.nullcontext()

    async def query_json_chain(self, **kwargs):  # noqa: D102 - protokol uyumu
        return self._intent


async def _submit(url: str):
    launched: list[dict] = []
    intent = AspasiaIntent(
        intent="run_profile_analysis", target_url=url, rationale="test",
        goals=["profile_analysis"],
    )
    commands = AspasiaCommandGateway(
        dispatch=lambda spec: launched.append(spec) or "op_cross_0001",
        gateway=_IntentGW(intent),
    )
    result = await commands.submit(f"bu profili incele: {url}", client_id="c1")
    return result, launched


@pytest.mark.parametrize("url,_h", ACCEPT)
async def test_aspasia_gate_accepts_all_known_platforms(url, _h):
    result, launched = await _submit(url)
    assert result.accepted, f"Aspasia kapısı {url} adresini reddetti: {result.reason}"
    assert launched and launched[0]["target_url"], "kabul edilen hedef dispatch edilmedi"


@pytest.mark.parametrize("url,_r", REJECT)
async def test_aspasia_gate_rejects_non_targets_without_dispatching(url, _r):
    result, launched = await _submit(url)
    assert result.accepted is False, f"Aspasia kapısı {url} adresini kabul etti"
    assert result.reason == "unsupported_or_missing_target"
    assert launched == [], "reddedilen hedefte görev BAŞLAMAMALI"


async def test_aspasia_gate_requires_https():
    # classify_url http:// kabul eder; Aspasia kapısı daha sıkı: yalnız https
    # (kural: kapı asla gevşemez).
    assert classify_url("http://instagram.com/nasa").runnable is True
    for insecure in ("http://instagram.com/nasa", "http://x.com/nasa"):
        result, launched = await _submit(insecure)
        assert result.accepted is False, f"{insecure} kabul edilmemeli"
        assert launched == []


@pytest.mark.parametrize("junk", ["", "   ", "https://", "@nasa", "nasa"])
async def test_aspasia_gate_rejects_garbage(junk):
    result, launched = await _submit(junk)
    assert result.accepted is False, f"çöp kabul edildi: {junk!r}"
    assert launched == []


async def test_aspasia_gate_upgrades_schemeless_host_path_to_https():
    """Şemasız `host/yol` kabul edilir — ama https'e YÜKSELTİLEREK.

    `_normalize_target_url`'in belgelenmiş davranışı (operatör elle
    "instagram.com/nasa" yazar); aşağı akış yine https görür.
    """
    result, launched = await _submit("instagram.com/nasa")
    assert result.accepted is True
    assert launched[0]["target_url"] == "https://instagram.com/nasa"


def test_aspasia_gate_stays_classify_url_driven():
    """Kapı platform kararını KOPYALAMAZ; `classify_url`'a delege eder.

    `_TARGET_RE` yalnız hızlı ön eleme; shape kararı profil
    yönlendiricisinde kalmalı (Kural [009] — ikinci doğruluk kaynağı yok).
    """
    from pathlib import Path

    source = Path("agent_core/aspasia/interface.py").read_text(encoding="utf-8")
    submit_block = source.split("async def submit", 1)[1]
    gate_block = submit_block.split("run_profile_analysis", 1)[1][:1200]
    assert "classify_url(" in gate_block, "Aspasia kapısı classify_url'a delege etmiyor"
