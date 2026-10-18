"""GÖREV 2 ARTIKLARI — shadow strateji eslemesi + PIL doygunlugu.

Kapsam:
  1. strategy_from_depth: 4 vektor + esikler + oncelik + tactic cumleleri
     (tasarım karari birebir) + total-fonksiyon + sinyal denetim izi.
  2. ShadowExecutor: verdict-ok derinlik BIRINCIL kaynaktir; yoksa/bozuksa
     legacy esik yolu (davranis kilitleri korunur).
  3. measure_saturation: PIL yoksa None+not;Stub-PIL ile HSV matematigi;
     bozuk dosya sayimi; gercek-PIL testi (ortamda varsa calisir).
  4. Ch3 rupture_kinds sinyali (tur listesi okunur, uydurulmaz).

Dogruluk ilkesi: esik-altı gozlem strateji uretmez; olculmeyen None kalir.
"""

import pytest

from agent_core.psychology.dark_triad import (
    DEPTH_ALLIANCE_REPETITION,
    DEPTH_MIRRORING_REACTION,
    DarkTriadAnalyzer,
)
from agent_core.services.psychodynamic_depth import (
    HAS_PIL,
    analyze_depth,
    measure_saturation,
)
from agent_core.shadow.shadow_executor import ShadowExecutor


def _depth(react=0.0, rep=0.0, nrup=0, kinds=None, verdict="ok", comp=0.1):
    return {
        "verdict": verdict,
        "confidence": 0.7,
        "compensation_index": comp,
        "reaction_formation_index": react,
        "channels": {
            "declaration": {
                "completeness": 0.7,
                "signals": {"repetition_score": rep},
            },
            "staging": {"completeness": 0.6, "signals": {}},
            "rhythm": {
                "completeness": 0.5,
                "signals": {
                    "n_ruptures": nrup, "rupture_kinds": list(kinds or []),
                },
            },
        },
    }


# ------------------------------------------------------------------ #
# 1) strateji eslemesi
# ------------------------------------------------------------------ #
def test_threshold_constants_are_design_values():
    assert DEPTH_MIRRORING_REACTION == 0.40
    assert DEPTH_ALLIANCE_REPETITION == 0.40


def test_mirroring_above_threshold_with_exact_tactic():
    s = DarkTriadAnalyzer().strategy_from_depth(_depth(react=0.61))
    assert s["vector"] == "mirroring"
    assert s["tactic"] == "Savunulan benlik idealini ve vitrini aynala"
    assert s["source"] == "psychodynamic_depth"
    assert s["signal"]["reaction_formation_index"] == 0.61


def test_alliance_above_threshold_with_exact_tactic():
    s = DarkTriadAnalyzer().strategy_from_depth(_depth(rep=0.55))
    assert s["vector"] == "alliance"
    assert s["tactic"] == "Kompülsif tekrar döngüsüne uyumlu öngörülebilir ortak çıkar"
    assert s["signal"]["repetition_score"] == 0.55


def test_thrill_on_rupture_count_with_exact_tactic():
    s = DarkTriadAnalyzer().strategy_from_depth(
        _depth(nrup=2, kinds=["entropy_jump", "variance_shift"]))
    assert s["vector"] == "thrill"
    assert s["tactic"] == "Faz kırılması ve volatiliteye uyumlu risk"
    assert s["signal"]["n_ruptures"] == 2


def test_thrill_on_entropy_jump_kind_alone():
    """'n_ruptures >= 1 VEYA entropy_jump' — tur tek basina yeter."""
    s = DarkTriadAnalyzer().strategy_from_depth(
        _depth(nrup=0, kinds=["entropy_jump"]))
    assert s["vector"] == "thrill"


def test_boundary_040_fires_0399_does_not():
    assert DarkTriadAnalyzer().strategy_from_depth(
        _depth(react=0.40))["vector"] == "mirroring"
    assert DarkTriadAnalyzer().strategy_from_depth(
        _depth(react=0.399))["vector"] == "unobserved"
    assert DarkTriadAnalyzer().strategy_from_depth(
        _depth(rep=0.40))["vector"] == "alliance"
    assert DarkTriadAnalyzer().strategy_from_depth(
        _depth(rep=0.399))["vector"] == "unobserved"


def test_precedence_mirroring_over_alliance_over_thrill():
    s = DarkTriadAnalyzer().strategy_from_depth(
        _depth(react=0.9, rep=0.9, nrup=5, kinds=["entropy_jump"]))
    assert s["vector"] == "mirroring"
    s2 = DarkTriadAnalyzer().strategy_from_depth(
        _depth(react=0.1, rep=0.9, nrup=5, kinds=["entropy_jump"]))
    assert s2["vector"] == "alliance"


def test_below_thresholds_is_unobserved_not_unavailable():
    s = DarkTriadAnalyzer().strategy_from_depth(_depth())
    assert s["vector"] == "unobserved"
    assert s["source"] == "psychodynamic_depth"


def test_non_ok_or_malformed_depth_is_unavailable_total():
    analyzer = DarkTriadAnalyzer()
    assert analyzer.strategy_from_depth({"verdict": "no_evidence"})["vector"] == "unavailable"
    assert analyzer.strategy_from_depth({})["vector"] == "unavailable"
    assert analyzer.strategy_from_depth(None)["vector"] == "unavailable"
    assert analyzer.strategy_from_depth("junk")["vector"] == "unavailable"
    assert analyzer.strategy_from_depth({"verdict": "ok"})["vector"] == "unavailable"
    assert analyzer.strategy_from_depth(
        {"verdict": "ok", "channels": {"declaration": {"signals": {}},
                                      "rhythm": {"signals": {}}}})["vector"] == "unobserved"
    # Sayisal olmayan sinyal esik gecemez, cokmez.
    bad = _depth()
    bad["reaction_formation_index"] = "yuksek"
    assert analyzer.strategy_from_depth(bad)["vector"] == "unobserved"


# ------------------------------------------------------------------ #
# 2) ShadowExecutor derinlik-onceligi
# ------------------------------------------------------------------ #
async def test_shadow_uses_depth_as_primary_source():
    executor = ShadowExecutor()
    result = await executor.execute({
        "target_profile": {"bio": "Sıradan bir insan.", "posts": []},
        "user_profile": {"rituals": ["kahve"], "music": "", "envies": ""},
        "target_beliefs": ["kontrolü elde tutmak"],
        "psychodynamic_depth": _depth(react=0.61),
    })
    assert result.strategy == "mirroring"
    assert result.data_confidence is True
    assert result.confidence == 0.6  # depth source completeness, not legacy trait score count
    assert result.trait_scores_measured is False
    assert result.dark_profile["narcissism"] is None
    assert isinstance(result.message, str) and len(result.message) > 0


async def test_shadow_depth_strategy_rejects_invalid_confidence_before_synthesis():
    executor = ShadowExecutor()
    depth = _depth(react=0.61)
    depth["confidence"] = float("nan")
    result = await executor.execute({
        "target_profile": {"bio": "A supplied target profile"},
        "psychodynamic_depth": depth,
    })
    assert result.data_confidence is False
    assert result.confidence == 0.0
    assert result.fallback_reason == "invalid_depth_confidence"
    assert result.message == ""
    assert result.strategy == "unavailable"
    assert result.dark_profile["narcissism"] is None


async def test_shadow_without_usable_depth_falls_back_to_legacy():
    executor = ShadowExecutor()
    result = await executor.execute({
        "target_profile": {"bio": "Sıradan bir insan.", "posts": []},
        "user_profile": {"rituals": ["kahve"], "music": "", "envies": ""},
        "psychodynamic_depth": {"verdict": "no_evidence"},
    })
    assert result.strategy == "unavailable"
    assert result.message == ""
    assert result.fallback_reason == "dark_triad_markers_unobserved"


# ------------------------------------------------------------------ #
# 3) doygunluk
# ------------------------------------------------------------------ #
def test_saturation_without_pil_is_honest_none():
    if HAS_PIL:
        pytest.skip("PIL kurulu; None-dali bu ortamda calismaz")
    res = measure_saturation(["/yok/1.jpg", "/yok/2.jpg"])
    assert res["mean_saturation"] is None
    assert res["has_pil"] is False
    assert res["n_total"] == 2
    assert res["n_measured"] == 0
    assert "PIL" in res["note"]


class _StubHSV:
    def __init__(self, pixels):
        self._pixels = pixels

    def getdata(self):
        return list(self._pixels)


class _StubImg:
    def __init__(self, pixels, fail=False):
        self._pixels = pixels
        self._fail = fail

    def __enter__(self):
        if self._fail:
            raise OSError("bozuk dosya")
        return self

    def __exit__(self, *a):
        return False

    def convert(self, mode):
        assert mode in ("RGB", "HSV")
        if mode == "HSV":
            return _StubHSV(self._pixels)
        return self

    def thumbnail(self, size):
        pass


class _StubPIL:
    files = {}

    @classmethod
    def open(cls, path):
        pixels, fail = cls.files[path]
        return _StubImg(pixels, fail)


def test_saturation_math_with_stub_pil(monkeypatch):
    import agent_core.services.psychodynamic_depth as pd

    monkeypatch.setattr(pd, "HAS_PIL", True)
    monkeypatch.setattr(pd, "_PILImage", _StubPIL)
    _StubPIL.files = {
        "a": ([(0, 128, 200), (0, 255, 200)], False),
        "b": ([(0, 0, 200)], False),
        "c": ([], True),  # bozuk: atlanir ve sayilir
    }
    res = measure_saturation(["a", "b", "c"])
    # a: (128+255)/2/255 = 0.75098; b: 0.0; ort = 0.37549 -> 0.375
    assert res["mean_saturation"] == 0.375
    assert res["n_measured"] == 2
    assert res["n_total"] == 3
    assert res["has_pil"] is True
    assert "2/3" in res["note"]


def test_saturation_all_corrupt_measures_nothing(monkeypatch):
    import agent_core.services.psychodynamic_depth as pd

    monkeypatch.setattr(pd, "HAS_PIL", True)
    monkeypatch.setattr(pd, "_PILImage", _StubPIL)
    _StubPIL.files = {"x": ([], True)}
    res = measure_saturation(["x"])
    assert res["mean_saturation"] is None
    assert res["n_measured"] == 0
    assert res["has_pil"] is True


@pytest.mark.skipif(not HAS_PIL, reason="PIL yok; local'de (pillow kurulu) calisir")
def test_saturation_with_real_pil_red_square(tmp_path):
    from PIL import Image

    path = str(tmp_path / "kirmizi.png")
    Image.new("RGB", (4, 4), (255, 0, 0)).save(path)
    res = measure_saturation([path])
    assert res["has_pil"] is True
    assert res["n_measured"] == 1
    assert res["mean_saturation"] == 1.0


# ------------------------------------------------------------------ #
# 4) rupture_kinds sinyali
# ------------------------------------------------------------------ #
def test_rhythm_signals_carry_sorted_rupture_kinds():
    rep = analyze_depth({
        "target_profile": {},
        "visual_evidence": {},
        "timing_forensics": {
            "samples": 6,
            "trajectory": {"ruptures": [
                {"kind": "variance_shift"}, {"kind": "entropy_jump"},
            ]},
        },
        "follower_audit": {},
    })
    sig = rep["channels"]["rhythm"]["signals"]
    assert sig["n_ruptures"] == 2
    assert sig["rupture_kinds"] == ["entropy_jump", "variance_shift"]
