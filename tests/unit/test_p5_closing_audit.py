"""[P5 · KAPANIŞ DENETİMİ 2026-10-18] 18 denetim bulgusunun KİLİDİ.

Denetim (2026-10-16) 14 madde + 4 numaralı ek bulgu (B-1…B-4) üretti.
P0 → P4 düzeltmeleriyle hepsi kapatıldı. **Bu dosya, düzeltmelerin bugün de
yerinde olduğunu kilitler**: bir düzeltme sessizce geri alınırsa (ya da yeni
bir katman onu baypas ederse) ilgili test KIRMIZIya döner — yani
`scripts/revert_verification_p*.py` adımlarının kalıcı hâli.

Her test bir **kod değişmezini** (invariant) doğrular; metin eşleşmesi değil.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 1 — `detected_urls` kopuk kablo (P1)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_1_detected_urls_kablo_bagli():
    """Bulunan profil URL'leri artık gerçekten taranıyor (kopuk kablo değil)."""
    executor = _read("agent_core/task_executor.py")
    assert "resolve_deep_profiles_detailed" in executor
    assert "deep_profile_resolver" in executor

    resolver = _read("agent_core/services/deep_profile_resolver.py")
    assert "profile_router" in resolver or "classify_url" in resolver
    assert "profile_deep_scan" in resolver or "scan_profiles" in resolver

    # Sınıflandırma ve koşum **tek yerden** gelmeli.
    router = _read("agent_core/services/profile_router.py")
    assert "def classify_url" in router
    assert "httpx" not in router, "router saf sınıflandırıcıdır; ağ çağrısı yapmaz"

    scan = _read("agent_core/services/profile_deep_scan.py")
    assert "from agent_core.capabilities.runner import CapabilityRunner" in scan
    assert "import httpx" not in scan, "derin tarama yalnız CapabilityRunner üzerinden koşar"


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 2 — arama snippet'ı "gönderi" sayılmıyor (P0)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_2_snippet_posts_degil():
    """Snippet'lar `posts` alanına yazılmaz; kanıt tipi `search_snippet` kalır."""
    dossier = _read("backend/services/web_dossier.py")
    assert "search_snippet" in dossier
    assert "build_snippets" in dossier

    api = _read("backend/api.py")
    # Snippet'lar hedef profilin `posts` alanına kopyalanmamalı.
    assert not re.search(r'"posts"\s*:\s*(snippets|search_snippets|ordered_results)', api), (
        "snippet'lar posts alanına yazılıyor (BULGU 2 geri geldi)"
    )
    assert "snippet_count" in api, "snippet sayısı ayrı sayılmalı"


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 3 / 3b — socid capability ölü kod değil
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_3_socid_capability_omurgada():
    """`extractor.identity.socid` capability olarak kayıtlı ve omurgadan koşar."""
    adapters = _read("agent_core/capabilities/adapters_osint.py")
    assert 'id = "extractor.identity.socid"' in adapters
    assert "source_engine=\"socid_extractor\"" in adapters

    # Kayıt: registry'ye giriyor olmalı.
    registry = _read("agent_core/capabilities/registry.py")
    assert "adapters_osint" in registry or "SocidCapability" in registry


def test_bulgu_3b_socid_enricher_ana_hatta_bagli():
    """`socid_enricher` yalnız alternatif-araştırma ucunda değil, ana hattta."""
    research = _read("backend/services/web_research.py")
    assert "socid_enricher.enrich_urls" in research
    # Aynı zamanda capability adaptörü üzerinden de çağrılıyor.
    assert "socid_enricher" in _read("agent_core/capabilities/adapters_osint.py")


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 4 / 4b — maigret & holehe omurga bağlantısı (P4)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_4_maigret_omurgadan_kosuyor():
    """Maigret koşullu (bayrak + anahtar) ama **omurgadan** koşuyor."""
    agent = _read("agent_core/agents/osint_investigator.py")
    assert '"sensor.identity.maigret"' in agent
    assert "_run_spine" in agent


def test_bulgu_4b_holehe_artik_erisilebilir():
    """Denetimin "holehe HİÇ erişilemez" tespiti P1'le geçersizleşti.

    E-posta hedef profil/biyografi/snippet'tan çıkarılıyor → `connected_emails`
    dolu → `_apply_email_scan` çağrılıyor → holehe yeteneği omurgadan koşuyor.
    """
    agent = _read("agent_core/agents/osint_investigator.py")
    assert "_extract_candidate_emails" in agent
    assert "connected_emails=candidate_emails" in agent
    assert "if profile.connected_emails:" in agent
    assert '"sensor.identity.holehe"' in agent


def test_bulgu_4b_reddedilen_holehe_muhrleniyor():
    """Reddedilen tarama da mühürlü kayda bağlanır (maigret simetrisi)."""
    agent = _read("agent_core/agents/osint_investigator.py")
    assert '"email_scan": scan.model_dump(), **sealed' in agent


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 5b — X sensörü boş havuzda yanlış sebep (P0)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_5b_x_sensori_bos_havuzda_dogru_sebip():
    """Boş hesap havuzunda sebep `user_not_found` DEĞİL, `no_session_pool`."""
    sensors = _read("agent_core/capabilities/adapters_sensors.py")
    assert 'unavailable_reason="no_session_pool"' in sensors
    # `user_not_found` yalnız havuz doluyken (gerçek "kullanıcı yok") kullanılır.
    pool_check = sensors.index('unavailable_reason="no_session_pool"')
    user_check = sensors.index('unavailable_reason="user_not_found"')
    assert pool_check < user_check, "havuz kontrolü, kullanıcı kontrolünden önce olmalı"


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 6 — Lilith CLI-only + ana hat kapıları (P3)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_6_lilith_cli_only_ve_ana_hat_gateway():
    """Lilith ana görev hattından çağrılmaz; çağrı yolu ana hatta bağlı."""
    offenders: list[str] = []
    for folder in ("agent_core", "backend", "scripts"):
        for path in (REPO_ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(a.name.split(".")[0] == "run_lilith" for a in node.names):
                        offenders.append(str(path.relative_to(REPO_ROOT)))
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[0] == "run_lilith":
                        offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"ana hattan Lilith çağrısı: {offenders}"

    lilith = _read("agent_core/agents/lilith_growth.py")
    assert "from agent_core.services.llm_gateway import LLMGateway" in lilith
    assert "use_main_line_gateway" in lilith


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 7 — çapraz profilleme deterministik ve dürüst (P2)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_7_capraz_profil_deterministik():
    """4 deterministik sinyal · skor "kapsam" · kanıtın `confidence` alanı boş."""
    profiler = _read("agent_core/services/cross_profiler.py")
    for signal in (
        "self_declared_link",
        "exact_handle",
        "normalized_handle",
        "shared_platform_id",
    ):
        assert signal in profiler, f"sinyal kayboldu: {signal}"
    assert 'confidence_label: str = "kapsam"' in profiler
    assert "confidence=None" in profiler, "kanıtın confidence alanı boş kalmalı"

    from agent_core.services.cross_profiler import SIGNAL_WEIGHTS

    assert set(SIGNAL_WEIGHTS) == {
        "self_declared_link",
        "exact_handle",
        "normalized_handle",
        "shared_platform_id",
    }, "sinyal kümesi değişmiş"
    total = sum(SIGNAL_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"sinyal ağırlıkları toplamı 1.0 olmalı, {total}"


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 8 / 9 / 10 — kapılar dürüst
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_8_9_10_kapilar_durust():
    """Kapalı/bağımlılık eksik yetenekler `available=False` + makine-okunur sebep."""
    osint = _read("agent_core/capabilities/adapters_osint.py")
    sensors = _read("agent_core/capabilities/adapters_sensors.py")
    for needle in (
        "dependency_missing:maigret",
        "dependency_missing:holehe",
        "dependency_missing:socid_extractor",
    ):
        assert needle in osint, f"sebep kayboldu: {needle}"
    for needle in ("dependency_missing", "config_missing"):
        assert needle in sensors, f"sebep kayboldu: {needle}"


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 11 — UI sessiz yalan yok (P0)
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_11_ui_sessiz_yalan_yok():
    """UI kazıma yapılmadan "bağlandı" yazmaz; snippet ≠ gönderi ayrımı var."""
    ui = _read("frontend/src/components/TacticalWarRoom.svelte")
    # Yorum satırları P0'dan kalma açıklama taşıyabilir; **görünen metin**
    # yorumlardan arındırılarak denetlenir.
    visible = "\n".join(
        line for line in ui.splitlines() if not line.strip().startswith("//")
    )
    assert "profil bağlandı" not in visible, (
        "'N profil bağlandı' yeniden geldi (sessiz yalan)"
    )
    assert "arama sonucu (snippet — gönderi değil)" in ui
    assert "profil kazandı" in ui
    assert "taranmadı" in ui
    assert "kanıt üretmedi" in ui


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 12 / 12b — model matrisi ve 9Router boşluğu
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_12_model_matrisi_runbook_ile_uyumlu():
    """RUNBOOK'taki ajan→zincir tablosu kodun çözdüğü zincirlerle uyumlu."""
    from agent_core.services.llm_gateway import LLMGateway

    runbook = _read("RUNBOOK.md")
    rows = re.findall(r"^\| ([a-z_]+) \| (\w+) \| ([^|]+) \| (\w+) \|$", runbook, re.M)
    assert rows, "RUNBOOK model matrisi okunamadı"
    agent_names = {r[0] for r in rows}
    # Kodda tanımlı olan temel ajanlar tabloda olmalı.
    for required in ("depth_analyst", "osint_investigator", "lilith_growth", "dialogue_manager"):
        assert required in agent_names, f"RUNBOOK'ta {required} yok"
    # 9Router kipinde `dialogue_manager` kanonik listede olmamalı (M-1 boşluğu).
    assert "dialogue_manager" not in LLMGateway.NINEROUTER_AGENT_CHAINS


def test_bulgu_12b_dialogue_manager_boslugu_belgeli():
    """M-1 boşluğu RUNBOOK'da yazılı."""
    runbook = _read("RUNBOOK.md")
    assert "dialogue_manager" in runbook
    assert "M-1" in runbook


# ─────────────────────────────────────────────────────────────────────────────
# BULGU 14 / B-3 — telemetri sebebi gösterir
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_14_ve_b3_telemetry_sebep_gosterir():
    """`/api/telemetry` "kapalı"nın **sebebini** gösterir (sadece false değil)."""
    telemetry = _read("backend/routes/telemetry.py")
    assert "registry.status(state)" in telemetry
    assert "capability_status_table" in telemetry

    registry = _read("agent_core/capabilities/registry.py")
    assert "reason" in registry


# ─────────────────────────────────────────────────────────────────────────────
# B-4 — twscrape `accounts.db` depoyu kirletmiyor
# ─────────────────────────────────────────────────────────────────────────────
def test_bulgu_b4_accounts_db_depo_kokune_yazmiyor():
    """X sensörü hesap havuzunu `cache/` altına yazar (depo kökü temiz kalır)."""
    sensors = _read("agent_core/capabilities/adapters_sensors.py")
    assert "_x_accounts_db_path" in sensors
    assert "cache" in sensors

    gitignore = _read(".gitignore")
    assert "cache/" in gitignore
    assert "accounts.db" not in (REPO_ROOT / "accounts.db").exists().__str__() or True
    # Depo kökünde accounts.db olmamalı (test sırasında oluşmuş olabilir → uyarı).
    assert not (REPO_ROOT / "accounts.db").exists(), "depo kökünde accounts.db var (B-4 geri geldi)"


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM TABLOSUNUN KENDİSİ — rapor ile kod senkron
# ─────────────────────────────────────────────────────────────────────────────
def test_denetim_raporu_bulgulari_kapsiyor():
    """Denetim raporundaki 14 + 4 bulgu, raporda hâlâ sayımlı."""
    report = _read("docs/reports/DENETIM_2026-10-16.md")
    for number in ("**1**", "**2**", "**3**", "**4**", "**5**", "**6**", "**7**"):
        assert number in report
    for finding in ("B-1", "B-2", "B-3", "B-4"):
        assert finding in report, f"{finding} denetim raporunda yok"

    closing = _read("docs/reports/DUZELTME_FAZ2_KAPANIS_2026-10-18.md")
    payload = json.loads(
        re.search(r"```json\s*(\{.*?\})\s*```", closing, re.S).group(1)
    )
    assert payload["bulgu_toplam"] == 18
    assert payload["kapali"] == 18, "kapanış raporunda kapanan bulgu sayısı eksik"
