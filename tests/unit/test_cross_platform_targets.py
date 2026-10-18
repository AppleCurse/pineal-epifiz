"""P10 · ÇAPRAZ PLATFORM HEDEF KABULÜ — Aspasia kapısı + profil yönlendirici.

Sözleşme:
1) TEK doğruluk kaynağı: Aspasia'nın hedef kapısı
   ``profile_router.classify_url``'dan okur (Kural [009]);
   platform listesi burada KOPYALANMAZ.
2) Bilinen sosyal profiller (IG/X sensörlü + 16 çapraz platform)
   kabul edilir; kabul edilen sosyal yolun capability'si
   ``extractor.identity.socid``'dir.
3) Shape dışı yollar, rezerv kelimeler, bakış-benzeri hostlar,
   http:// ve bilinmeyen hostlar REDDEDİLİR (fail-closed;
   sebep makine-okunur raporlanır, sessiz düşürülmez).
4) IG/X regression: kendi sensörlerine gitmeye devam eder.
Gerçek network yok — sınıflandırıcı saf (ağ YOK, yan etki YOK).
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import agent_core.services.llm_gateway as gwl
from agent_core.aspasia.interface import AspasiaCommandGateway, _is_supported_target
from agent_core.services.llm_gateway import LLMGateway
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
    ("https://www.tiktok.com/tag/dance", REASON_NOT_A_PROFILE),
    ("https://t.me/s/publicchannel", REASON_NOT_A_PROFILE),
    ("https://www.facebook.com/login", REASON_NOT_A_PROFILE),
    ("https://www.twitch.tv/directory", REASON_NOT_A_PROFILE),
    ("https://steamcommunity.com/id/", REASON_NOT_A_PROFILE),
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


# ------------------------------------------------- 3) Aspasia hedef kapısı
@pytest.mark.parametrize("url,_h", ACCEPT)
def test_aspasia_gate_accepts_all_known_platforms(url, _h):
    assert _is_supported_target(url), f"Aspasia kapısı {url}'yi reddetti"


@pytest.mark.parametrize("url,_r", REJECT)
def test_aspasia_gate_rejects_non_targets(url, _r):
    assert not _is_supported_target(url), f"Aspasia kapısı {url}'yi kabul etti"


def test_aspasia_gate_requires_https():
    # classify_url http:// kabul eder; Aspasia kapısı daha sıkı:
    # yalnız https (kural: kapı asla gevşemez).
    assert not _is_supported_target("http://instagram.com/nasa")
    assert not _is_supported_target("http://x.com/nasa")


def test_aspasia_gate_rejects_garbage():
    for junk in ("", "   ", "https://", "instagram.com/nasa", "@nasa"):
        assert not _is_supported_target(junk), f"çöp kabul edildi: {junk!r}"


# ------------------------------------------- 4) Aspasia komut döngüsü (mock)
_ENV_KEYS = (
    "OPENROUTER_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
    "CEREBRAS_API_KEY", "NOUS_API_KEY", "PINEAL_ALLOW_PAID_ESCALATION",
    "PINEAL_ALLOW_UNPRICED_MODELS", "OPENROUTER_MAX_SPEND_USD",
    "OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "OPENROUTER_AGENT_CHAIN_ASPASIA",
    "USE_LOCAL_LLM", "LIVE_LLM_E2E", "PINEAL_ROUTER_LIVE",
)


class _FakeProvider:
    """AsyncOpenAI dikişi — niyet JSON'unu döndürür (transport mock)."""

    def __init__(self, payload):
        self._payload = payload

    def factory(self, *, base_url, api_key, max_retries=0, **kw):
        outer = self

        class _C:
            def __init__(self, bu):
                self.chat = SimpleNamespace(completions=_Comp(bu, outer))

        class _Comp:
            def __init__(self, bu, owner):
                self._bu = bu
                self._owner = owner

            async def create(self, **kwargs):
                return SimpleNamespace(
                    usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                    model=kwargs["model"],  # ikame denetimi: istenen model
                    choices=[SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(self._owner._payload)
                        )
                    )],
                )

        return _C("https://fake.provider.local/v1")


@pytest.fixture()
def clean_env(monkeypatch):
    fake = _FakeProvider({})
    monkeypatch.setattr(gwl, "AsyncOpenAI", lambda **kw: fake.factory(**kw))
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    return fake


def _gw():
    gw = LLMGateway()
    gw.live_unlocked = True
    return gw


def test_aspasia_dispatches_cross_platform_target(clean_env):
    clean_env._payload = {
        "intent": "run_profile_analysis",
        "target_url": "https://www.tiktok.com/@nasa",
        "rationale": "test",
        "goals": ["profile_analysis"],
    }
    launched: list[dict] = []
    commands = AspasiaCommandGateway(
        dispatch=lambda spec: launched.append(spec) or "op_cross_0001",
        gateway=_gw(),
    )
    res = asyncio.run(
        commands.submit("bu profili incele: https://www.tiktok.com/@nasa", client_id="c1")
    )
    assert res.accepted, f"kabul edilmedi: {res.reason}"
    assert res.intent == "run_profile_analysis"
    assert launched and launched[0]["target_url"] == "https://www.tiktok.com/@nasa"


def test_aspasia_rejects_unsupported_platform_and_never_dispatches(clean_env):
    clean_env._payload = {
        "intent": "run_profile_analysis",
        "target_url": "https://example.com/nasa",
        "rationale": "test",
        "goals": [],
    }
    launched: list[dict] = []
    commands = AspasiaCommandGateway(
        dispatch=lambda spec: launched.append(spec) or "op_never_0001",
        gateway=_gw(),
    )
    res = asyncio.run(
        commands.submit("incele: https://example.com/nasa", client_id="c1")
    )
    assert not res.accepted
    assert res.reason == "unsupported_or_missing_target"
    assert launched == []  # uydurma/ytabancı hedefte görev BAŞLAMAZ
