"""GÖREV 2 — psikodinamik motor sozlesmeleri (2.1 - 2.4).

Kapsam:
  2.1  Denetimsiz kumeleme: birlesme/ayrisma/kararlilik/anomali + bos-girdi.
  2.2  S(t) yorungesi: kirilma tespiti (entropi/varyans), rejimler, <3 None,
       legacy anahtarlar + hizalama-disi sayim oduncu yasagi.
  2.3  4 kanal + capraz gerilim (simetri/kosegen), telafi/reaksiyon araligi.
  2.4  Epistemik kapi: metin yoksa w_decl=0 + butce kaymasi; hic kanal
       yoksa no_evidence (HALT YOK); doygunluk None-kilidi.
  Govde: dark-triad trait sifirlari + tema tasiyicisi + esik-mantigi koruma.

Dogruluk ilkesi: olculen yazar, olculemeyen None/kapali olur; motor halt etmez.
"""

from agent_core.services.theme_cluster import (
    THEME_SIM_THRESHOLD,
    cluster_texts,
)
from agent_core.services.timing_forensics import (
    analyze_timing,
    analyze_trajectory,
)
from agent_core.services.psychodynamic_depth import analyze_depth
from agent_core.services.follower_audit import audit_followers
from agent_core.psychology.dark_triad import DarkTriadAnalyzer, DarkTriadProfile


# ------------------------------------------------------------------ #
# 2.1 kumeleme
# ------------------------------------------------------------------ #
def test_cluster_merges_near_duplicates():
    res = cluster_texts([
        "gece stüdyo kayıtları devam ediyor",
        "gece stüdyo kayıtları sürüyor",
    ])
    assert res["n_texts"] == 2
    assert res["n_themes"] == 1
    assert res["themes"][0]["members"] == [0, 1]
    assert res["repetition_score"] == 1.0
    assert res["isolated_anomaly_count"] == 0


def test_cluster_splits_distinct_texts():
    res = cluster_texts([
        "müzik prodüksiyon şirketi",
        "yat tatili bodrum deniz",
    ])
    assert res["n_themes"] == 2
    assert res["repetition_score"] == 0.5
    assert res["anomaly_indices"] == [0, 1]
    assert res["isolated_anomaly_count"] == 2


def test_cluster_detects_repetition_vs_isolated_anomaly():
    res = cluster_texts([
        "gece stüdyo kayıtları devam ediyor",
        "gece stüdyo kayıtları sürüyor",
        "yat tatili bodrum",
    ])
    assert res["n_themes"] == 2
    assert res["repetition_score"] == 0.667
    assert res["anomaly_indices"] == [2]
    assert res["themes"][1]["size"] == 1


def test_cluster_is_deterministic_and_total():
    texts = ["Mükemmel benzersiz seçilmiş", "Mükemmel benzersiz", "kontrol bende"]
    assert cluster_texts(texts) == cluster_texts(texts)
    assert cluster_texts([])["n_themes"] == 0
    assert cluster_texts([])["repetition_score"] == 0.0
    assert cluster_texts(["", "  ", None, 123])["n_texts"] == 0
    assert cluster_texts(["tek"])["n_themes"] == 1
    assert THEME_SIM_THRESHOLD == 0.30


# ------------------------------------------------------------------ #
# 2.2 yorunge
# ------------------------------------------------------------------ #
ENTROPY_SERIES = [
    "2024-05-01T10:00:00+00:00",
    "2024-05-02T10:30:00+00:00",
    "2024-05-03T11:00:00+00:00",
    "2024-05-04T23:30:00+00:00",
    "2024-05-05T06:00:00+00:00",
    "2024-05-06T20:00:00+00:00",
]

VARIANCE_SERIES = [
    "2024-05-01T10:00:00+00:00",
    "2024-05-01T11:00:00+00:00",
    "2024-05-01T12:00:00+00:00",
    "2024-05-01T13:00:00+00:00",
    "2024-05-03T14:00:00+00:00",
    "2024-05-03T15:00:00+00:00",
]


def test_trajectory_entopy_rupture_and_regimes():
    traj = analyze_trajectory(ENTROPY_SERIES)
    assert traj["n"] == 6
    assert traj["t_0"] < traj["t_N"]
    assert [s["gap_hours"] for s in traj["states"]][0] is None
    kinds = [r["kind"] for r in traj["ruptures"]]
    assert "entropy_jump" in kinds
    jump = next(r for r in traj["ruptures"] if r["kind"] == "entropy_jump")
    assert jump["magnitude"] > 0.5
    assert len(traj["regimes"]) == 2
    assert traj["regimes"][0]["dominant_daypart"] == "workday"
    assert traj["note"] == "ok"


def test_trajectory_variance_scissors_without_entropy_jump():
    traj = analyze_trajectory(VARIANCE_SERIES)
    kinds = [r["kind"] for r in traj["ruptures"]]
    assert kinds == ["variance_shift"]
    assert traj["var_ratio"] > 3.0
    assert traj["entropy_jump"] == 0.0


def test_trajectory_minimums_are_honest():
    assert analyze_trajectory([]) is None
    assert analyze_trajectory(["2024-05-01T10:00:00+00:00", ""]) is None
    three = analyze_trajectory(ENTROPY_SERIES[:3])
    assert three["n"] == 3
    assert three["ruptures"] == []
    assert "n<4" in three["note"]
    assert len(three["regimes"]) == 2


def test_trajectory_engagement_realigns_after_sort():
    """Sayimlar siralama sonrasi GERCEK posttan alinir, komsudan degil."""
    times = list(reversed(VARIANCE_SERIES))
    # engagement GIRIS sirasiyla hizalidir (ters kronoloji).
    engagement = [
        {"like_count": like, "comment_count": 0}
        for like in (60, 50, 40, 30, 20, 10)
    ]
    traj = analyze_trajectory(times, engagement=engagement)
    eng = traj["engagement"]
    # Kronolojik ilk yari = dusuk begeniler (10, 20, 30).
    assert eng["like_mean_first"] == 20.0
    assert eng["like_mean_second"] == 50.0
    assert eng["like_shift_ratio"] == 2.5


def test_legacy_timing_keys_preserved_with_trajectory():
    res = analyze_timing([
        "2026-08-20T02:15:00",
        "2026-08-21T03:30:00",
        "2026-08-22T01:45:00",
        "2026-08-23T14:00:00",
    ])
    assert res["samples"] == 4
    assert res["night_share"] == 0.75
    assert res["trajectory"]["n"] == 4


# ------------------------------------------------------------------ #
# 2.3 / 2.4 derinlik + epistemik kapi
# ------------------------------------------------------------------ #
def _full_input():
    return {
        "target_profile": {
            "bio": "gece stüdyo kayıtları",
            "posts": ["gece stüdyo kayıtları devam", "yat tatili bodrum"],
            "images": ["http://x.example/1.jpg", "http://x.example/2.jpg"],
            "post_types": ["image", "video", "unknown"],
        },
        "visual_evidence": {
            "detected_objects": ["mikrofon", "mikser", "mikrofon"],
            "aesthetic_style": "loş",
            "visual_confidence": 0.8,
        },
        "timing_forensics": {
            "samples": 6,
            "night_share": 0.5,
            "peak_hour": "23:00",
            "median_drift_hours": 1.5,
            "trajectory": {
                "ruptures": [{"kind": "entropy_jump", "at_idx": 3,
                              "at_t": "2024-05-04T23:30:00+00:00",
                              "magnitude": 0.8}],
                "regimes": [{}, {}],
                "span_hours": 100.0,
            },
        },
        "follower_audit": audit_followers(
            1000,
            100,
            [{"like_count": 50, "comment_count": 0}],
        ).model_dump(),
    }


def test_depth_full_report_shape_and_tension_math():
    rep = analyze_depth(_full_input())
    assert rep["verdict"] == "ok"
    assert set(rep["channels"]) == {"declaration", "staging", "rhythm", "social"}
    for ch in rep["channels"].values():
        assert set(ch) == {"intensity", "coherence", "completeness", "signals"}
        assert all(0.0 <= ch[k] <= 1.0 for k in ("intensity", "coherence", "completeness"))
    weights = rep["epistemic_weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.002
    assert rep["confidence"] > 0.0
    matrix = rep["tension_matrix"]
    assert len(matrix) == 4 and all(len(row) == 4 for row in matrix)
    for i in range(4):
        assert matrix[i][i] == 0.0
        for j in range(4):
            assert matrix[i][j] == matrix[j][i]
            assert 0.0 <= matrix[i][j] <= 1.0
    assert 0.0 <= rep["compensation_index"] <= 1.0
    assert 0.0 <= rep["reaction_formation_index"] <= 1.0
    assert rep["reaction_formation_index"] == matrix[0][1]
    assert rep["channels"]["declaration"]["signals"]["n_texts"] == 3
    social = rep["channels"]["social"]["signals"]
    assert social["engagement_rate"] == 5.0  # producer emits percentage points
    assert social["followers"] == 1000
    assert social["following"] == 100
    assert rep["channels"]["social"]["intensity"] == 0.5  # 5% of the 10% reference


def test_depth_nonfinite_social_metrics_are_not_counted_as_evidence():
    data = _full_input()
    data["follower_audit"]["data_completeness"] = float("nan")
    data["follower_audit"]["engagement_rate"] = float("inf")
    report = analyze_depth(data)
    social = report["channels"]["social"]
    assert report["verdict"] == "ok"
    assert social["completeness"] == 0.0
    assert social["intensity"] == 0.0
    assert social["signals"]["engagement_rate"] is None


def test_depth_saturation_is_locked_null():
    rep = analyze_depth(_full_input())
    staging = rep["channels"]["staging"]["signals"]
    assert staging["color_saturation"] is None
    assert "PIL" in staging["saturation_note"]


def test_depth_without_text_shifts_budget_not_halt():
    data = _full_input()
    data["target_profile"]["bio"] = ""
    data["target_profile"]["posts"] = []
    rep = analyze_depth(data)
    assert rep["verdict"] == "ok"  # HALT YOK
    assert rep["epistemic_weights"]["w_declaration"] == 0.0
    assert rep["confidence"] > 0.0
    assert "metin kanali kapali" in rep["reason"]
    assert rep["channels"]["declaration"]["completeness"] == 0.0


def test_depth_visual_temporal_only_budget_is_one():
    """Spec formulu: yalniz gorsel+zaman varsa w_vis + w_temp = 1.0."""
    data = _full_input()
    data["target_profile"]["bio"] = ""
    data["target_profile"]["posts"] = []
    data["follower_audit"] = {}
    rep = analyze_depth(data)
    weights = rep["epistemic_weights"]
    assert weights["w_declaration"] == 0.0
    assert weights["w_social"] == 0.0
    assert abs(weights["w_staging"] + weights["w_rhythm"] - 1.0) < 0.002
    assert rep["verdict"] == "ok"


def test_depth_without_any_channel_reports_no_evidence():
    rep = analyze_depth({})
    assert rep["verdict"] == "no_evidence"  # HALT DEGIL, verdict
    assert rep["confidence"] == 0.0
    assert all(w == 0.0 for w in rep["epistemic_weights"].values())


def test_depth_never_raises_on_adversarial_shapes():
    rep = analyze_depth({
        "target_profile": None,
        "visual_evidence": "junk",
        "timing_forensics": [],
        "follower_audit": "x",
    })
    assert rep["verdict"] == "no_evidence"
    assert rep["confidence"] == 0.0


def test_depth_without_trajectory_ruptures_still_produces_report():
    """[BOSS-13] Regresyon: `trajectory.ruptures` yokken blok TypeError
    fırlatıyordu; savunma hattı onu yutup TÜM raporu 'no_evidence' yapıyordu.
    Sahici bir hedef profili (kırılma verisi olmadan) artık sonuç üretmeli."""
    rep = analyze_depth({
        "target_profile": {
            "bio": "Mimar. Gece calisirim.",
            "posts": ["Gece yuruyusleri iyi geliyor", "Sessizlik huzurdur"],
            "post_times": ["2026-01-02T23:10:00+00:00", "2026-03-05T21:05:00+00:00"],
            "post_types": ["image", "image"],
        },
        "timing_forensics": {"samples": 2, "night_share": 1.0, "trajectory": None},
    })
    assert rep["verdict"] == "ok", rep.get("reason")
    assert rep["confidence"] > 0.0
    rhythm = rep["channels"]["rhythm"]["signals"]
    assert rhythm["n_ruptures"] == 0
    assert rhythm["rupture_kinds"] == []


def test_depth_trajectory_without_ruptures_key_is_safe():
    """`trajectory` var ama `ruptures` anahtarı hiç yoksa da çökmemeli."""
    rep = analyze_depth({
        "target_profile": {"bio": "gece stüdyo", "posts": ["gece stüdyo kayıtları"]},
        "timing_forensics": {"samples": 4, "trajectory": {"regimes": [], "span_hours": 12.0}},
    })
    assert rep["verdict"] == "ok", rep.get("reason")
    assert rep["channels"]["rhythm"]["signals"]["n_ruptures"] == 0


# ------------------------------------------------------------------ #
# Govde: dark-triad sifirlari + esik koruma
# ------------------------------------------------------------------ #
def test_dark_shell_returns_zeros_with_themes():
    analyzer = DarkTriadAnalyzer()
    profile = analyzer.analyze({
        "bio": "gece stüdyo kayıtları",
        "posts": ["gece stüdyo kayıtları devam", "yat tatili bodrum"],
    })
    assert profile.machiavellianism == 0.0
    assert profile.narcissism == 0.0
    assert profile.psychopathy == 0.0
    assert profile.exploitability == 0.0
    assert profile.theme_analysis["n_texts"] == 3
    assert profile.theme_analysis["n_themes"] == 2


def test_dark_shell_is_deterministic_and_total():
    analyzer = DarkTriadAnalyzer()
    payload = {"bio": "x", "posts": ["y"]}
    assert analyzer.analyze(payload).model_dump() == analyzer.analyze(payload).model_dump()
    assert analyzer.analyze({}).theme_analysis["n_texts"] == 0
    assert analyzer.analyze({"posts": "tek metin", "bio": ""}).theme_analysis["n_texts"] == 1
    assert DarkTriadProfile().theme_analysis is None


def test_dark_strategy_thresholds_preserved_for_explicit_profiles():
    analyzer = DarkTriadAnalyzer()
    assert analyzer.generate_strategy(DarkTriadProfile())["vector"] == "unavailable"
    assert analyzer.generate_strategy(DarkTriadProfile(narcissism=0.8))["vector"] == "mirroring"
    assert analyzer.generate_strategy(DarkTriadProfile(machiavellianism=0.7))["vector"] == "alliance"
    assert analyzer.generate_strategy(DarkTriadProfile(psychopathy=0.6))["vector"] == "thrill"
    assert analyzer.generate_strategy(DarkTriadProfile(narcissism=0.2))["vector"] == "unobserved"
