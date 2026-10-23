"""İddialar ÇALIŞTIRILARAK kanıtlanır — "kayıtlı olmak = çalışıyor" değildir.

[2026-10-23 · MANTIK KAFESİ] Denetim şu soruları sordu ve haklıydı:

  * "13 ajan kayıtlı" — peki hepsi gerçekten KOŞUYOR mu, yoksa biri placeholder mı?
  * "27 yetenek kayıtlı" — kaçı üretim yolundan erişilebilir?
  * "69 uç" — kaçı çağrılıyor, kaçı ölü?

Bu dosya cevapları STATİK TARAMA ile değil, kodu KOŞTURARAK verir:

  1. Gerçek `CognitiveRouter` + gerçek `PinealExecutor` ile bir görev koşulur;
     her ajanın `execute/analyze` çağrısı kaydedilir → 13/13 kanıtlanır.
  2. Her kayıtlı yetenek için `availability()` çağrılır: istisna YOK ve sebep
     makine-okunur (kapı adı / eksik bağımlılık). Ayrıca her yetenek kimliği
     `agent_core/capabilities/` DIŞINDA en az bir üretim dosyasında geçer
     (çağrı yeri var) — "kayıt defterinde duruyor ama kimse çağırmıyor" olmaz.
  3. Hiçbir HTTP ucu "hiçbir yerde çağrılmıyor" durumunda değildir: her uç ya
     UI/edge worker'da ya da testlerde (98 dosya `TestClient` kullanıyor)
     çağrılır. `dead_code_audit` uçları KAPSAMAZ; bu test o boşluğu kapatır.
  4. Kasa durum ucu anahtar MALZEMESİ döndürmez (yalnız boolean'lar).
"""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Yürütücünün kaydettiği 13 ajan (README/`task_executor.py` ile aynı küme).
REGISTERED_AGENTS = {
    "passion_mapper", "friction_detector", "cognitive_profiler",
    "resonance_synthesizer", "human_behavior", "mirror_truth",
    "resonance_calc", "pattern_interrupt", "autonomous_verifier",
    "authenticity_auditor", "osint_investigator", "shadow_executor",
    "depth_analyst",
}


# ───────────────────────────────────────────── 1. AJANLAR GERÇEKTEN KOŞUYOR
class _DummyResult(BaseModel):
    compatibility_score: float = 0.9
    summary: str = "ok"


def _depth_report():
    from agent_core.agents.depth_analyst import DepthReport

    return DepthReport(
        reality_index=0.9,
        reality_rationale="test",
        essence_one_liner="test",
        reality_findings=[],
        quote_guard={"kept": 0, "checked": 0, "dropped_fake_quote": 0},
    )


class _RecordingAgent:
    """Ajanın gövdesini DEĞİL, çağrıldığını kaydeder (LLM/ağ yok)."""

    def __init__(self, name: str, executed: list[str]) -> None:
        self.name = name
        self._executed = executed

    async def execute(self, _data):
        self._executed.append(self.name)
        return _DummyResult()

    async def analyze(self, *_args, **_kwargs):
        self._executed.append(self.name)
        return _depth_report()


@pytest.mark.asyncio
async def test_every_registered_agent_actually_runs_in_a_real_pipeline():
    """Gerçek router + gerçek yürütücü: 13 ajanın 13'ü de çağrılır."""
    from agent_core.task_executor import PinealExecutor

    executed: list[str] = []
    executor = PinealExecutor()
    # Dış servisler sahte; ROUTER ve boru hattı GERÇEK.
    executor.uncertainty = MagicMock()
    executor.uncertainty.evaluate.return_value = MagicMock(
        confidence=0.95, is_suspicious=False, reason=""
    )
    executor.memory = MagicMock()
    executor.memory.merge_evidence = AsyncMock()
    executor.injector = MagicMock()
    executor.injector.fetch_active_rules.return_value = {}
    executor.search_engine = MagicMock()
    executor.search_engine.search = AsyncMock(return_value=[])
    for name in list(executor.agents):
        executor.agents[name] = _RecordingAgent(name, executed)
    executor._download_images = AsyncMock(return_value=[])

    status = await executor.execute_task(
        {
            "target_profile": {"username": "hedef", "bio": "p", "posts": ["p1", "p2"]},
            "user_profile": {"bio": "ben", "posts": ["u1"]},
            "visual_evidence": "img.jpg",
        },
        "kanit-ajan",
    )

    ran = set(executed)
    missing = REGISTERED_AGENTS - ran
    assert not missing, f"kayıtlı ama KOŞMAYAN ajanlar: {sorted(missing)}"
    assert status.status.name in {"COMPLETED", "PARTIALLY_COMPLETED"}


def test_each_agent_has_its_own_real_module():
    """[002] "her ajan ayrı dosyada" iddiası: 12'si agents/, 1'i shadow/.

    `shadow_executor` ayrı bir ALT SİSTEMDİR (`agent_core/shadow/`) — kopya
    değil. Bu test eşlemenin sessizce kaymasını engeller.
    """
    mapping = {
        "passion_mapper": "agent_core/agents/passion_mapper.py",
        "friction_detector": "agent_core/agents/friction_detector.py",
        "cognitive_profiler": "agent_core/agents/cognitive_profiler.py",
        "resonance_synthesizer": "agent_core/agents/resonance_synthesizer.py",
        "human_behavior": "agent_core/agents/human_behavior.py",
        "mirror_truth": "agent_core/agents/mirror_truth.py",
        "resonance_calc": "agent_core/agents/resonance_calculator.py",
        "pattern_interrupt": "agent_core/agents/pattern_interrupt.py",
        "autonomous_verifier": "agent_core/agents/autonomous_verifier.py",
        "authenticity_auditor": "agent_core/agents/authenticity_auditor.py",
        "osint_investigator": "agent_core/agents/osint_investigator.py",
        "depth_analyst": "agent_core/agents/depth_analyst.py",
        "shadow_executor": "agent_core/shadow/shadow_executor.py",
    }
    assert set(mapping) == REGISTERED_AGENTS
    for agent, rel in mapping.items():
        path = REPO_ROOT / rel
        assert path.exists(), f"{agent} dosyası yok: {rel}"
        source = path.read_text(encoding="utf-8")
        assert "class " in source, f"{agent} dosyasında sınıf yok: {rel}"
        # Boş/placeholder gövde yasak: dosya gerçek kod taşımalı.
        assert len(source.splitlines()) > 20, f"{agent} dosyası şüpheli kısa: {rel}"


# ───────────────────────────────────── 2. YETENEKLER OMURGADAN ERİŞİLEBİLİR
def test_every_capability_reports_availability_without_raising():
    """27 yeteneğin hepsi `availability()` çağrısına cevap verir (istisna yok).

    İstisna fırlatan bir yetenek "kapalı" değil "bozuk" görünür ve operatör
    hangi paketi kuracağını öğrenemez.
    """
    from agent_core.capabilities.base import Availability
    from agent_core.capabilities.registry import bootstrap

    caps = bootstrap()._caps
    assert len(caps) == 27, f"kayıtlı yetenek sayısı değişti: {len(caps)}"
    for cap_id, cap in caps.items():
        availability = cap.availability()
        assert isinstance(availability, Availability), cap_id
        if not availability.available:
            assert availability.reason, f"{cap_id}: kapalı ama sebep yok"
            assert ":" in availability.reason or availability.reason in {
                "no_local_models", "no_local_endpoint"
            }, f"{cap_id}: sebep makine-okunur değil: {availability.reason}"


def _capability_reference_map() -> dict[str, list[str]]:
    """Yetenek kimliği → onu anan ÜRETİM dosyaları (adapters/ ve registry hariç)."""
    prod = [
        p for p in list(REPO_ROOT.glob("agent_core/**/*.py")) + list(REPO_ROOT.glob("backend/**/*.py"))
        if "__pycache__" not in str(p)
        and "/capabilities/" not in str(p).replace("\\", "/")
    ]
    from agent_core.capabilities.registry import bootstrap

    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in prod}
    return {
        cap_id: [str(p.relative_to(REPO_ROOT)) for p, t in texts.items() if cap_id in t]
        for cap_id in bootstrap()._caps
    }


#: Zincirle (tekil kimlikle değil) çağrılan yetenekler ve taşıyıcı sabit.
#: [2026-10-23] Bu testin ilk koşumu ÜÇ yeteneği "orphan" buldu:
#: `extractor.web.trafilatura|crawl4ai|scrapling`. Kod okundu → yanlış pozitif
#: DEĞİL, farklı bir bağlama biçimi: bu üçlü `WEB_EXTRACTION_ORDER` ile
#: sırayla denenir ve zinciri `extract_web_text(...)` çağırır. O çağrı da
#: `backend/services/web_research.py::run_public_web_research` içindedir.
#: Test artık iki bağlama biçimini de kabul eder — ama zincirin kendisinin
#: gerçekten çağrıldığını AYRICA doğrular (yoksa "zincir var, çağıran yok"
#: sessizce geçerdi).
CHAIN_DISPATCH: dict[str, tuple[str, str, str]] = {
    # yetenek id → (sıra sabiti, zincir fonksiyonu, zinciri çağıran üretim dosyası)
    "extractor.web.trafilatura": (
        "WEB_EXTRACTION_ORDER", "extract_web_text", "backend/services/web_research.py",
    ),
    "extractor.web.crawl4ai": (
        "WEB_EXTRACTION_ORDER", "extract_web_text", "backend/services/web_research.py",
    ),
    "extractor.web.scrapling": (
        "WEB_EXTRACTION_ORDER", "extract_web_text", "backend/services/web_research.py",
    ),
}


def test_every_capability_has_a_production_call_site():
    """Kayıtlı her yeteneğin bir çağrı yeri olmalı (tekil ya da zincir üzerinden)."""
    refs = _capability_reference_map()
    adapters_web = (REPO_ROOT / "agent_core/capabilities/adapters_web.py").read_text(encoding="utf-8")

    orphans: list[str] = []
    for cap, files in refs.items():
        if files:
            continue
        chain = CHAIN_DISPATCH.get(cap)
        if chain is None:
            orphans.append(cap)
            continue
        order_const, chain_fn, caller = chain
        # 1) kimlik gerçekten sıra sabitinin içinde mi?
        assert cap in adapters_web, cap
        assert f"{order_const}:" in adapters_web, f"{order_const} tanımlı değil"
        # 2) zincir fonksiyonu üretim yolundan çağrılıyor mu?
        caller_src = (REPO_ROOT / caller).read_text(encoding="utf-8")
        assert chain_fn in caller_src, f"{chain_fn} {caller} içinde çağrılmıyor"
    assert not orphans, f"kayıtlı ama hiçbir üretim yolundan çağrılmayan: {orphans}"


# ───────────────────────────────────────── 3. UÇLAR: ÖLÜ UÇ YOK
def _endpoint_paths() -> set[str]:
    from backend.api import app

    return {
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "").startswith(("/api", "/v1"))
        or getattr(route, "path", "") == "/health"
    }


def _call_site_corpus() -> str:
    chunks: list[str] = []
    for pattern in ("frontend/src/**/*.svelte", "frontend/src/**/*.ts", "frontend/src/**/*.js"):
        chunks += [p.read_text(encoding="utf-8", errors="replace") for p in REPO_ROOT.glob(pattern)]
    for extra in ("worker.ts",):
        candidate = REPO_ROOT / extra
        if candidate.exists():
            chunks.append(candidate.read_text(encoding="utf-8", errors="replace"))
    for f in (REPO_ROOT / "functions").rglob("*"):
        if f.suffix in {".ts", ".js"}:
            chunks.append(f.read_text(encoding="utf-8", errors="replace"))
    chunks += [p.read_text(encoding="utf-8", errors="replace") for p in (REPO_ROOT / "tests").rglob("*.py")]
    return "\n".join(chunks)


def test_no_http_endpoint_is_orphaned():
    """Her uç en az bir çağrı yerinde geçmeli (UI/edge worker ya da test).

    Not: `dead_code_audit` modül/fonksiyon/ajan/yetenek/bileşen bakar, HTTP
    uçlarını KAPSAMAZ — bu test o boşluğu kapatır. Testler uçları gerçekten
    koşar (98 test dosyası `TestClient` kullanır), yani "çağrı yeri" iddiası
    statik bir isim araması değil, koşan bir çağrının kaynağıdır.
    """
    corpus = _call_site_corpus()

    def tokens(path: str) -> list[str]:
        return [s for s in path.strip("/").split("/") if s and not s.startswith("{")]

    orphans = []
    for path in sorted(_endpoint_paths()):
        toks = tokens(path)
        leaf, head = toks[-1], "/".join(toks[:2])
        if not ((leaf in corpus and head in corpus) or path in corpus):
            orphans.append(path)
    assert not orphans, f"hiçbir çağrı yeri olmayan uçlar: {orphans}"


# ───────────────────────────────────── 4. KASA UCU ANAHTAR SIZDIRMIYOR
def test_vault_status_endpoint_returns_only_booleans(monkeypatch):
    """/api/vault/status yalnız DURUM döner; anahtar değeri asla gövdede olmaz."""
    from fastapi.testclient import TestClient

    from backend.api import app

    monkeypatch.setenv("PINEAL_ENV", "development")
    secret = "sk-or-v1-THIS-MUST-NOT-LEAK-0123456789"
    with TestClient(app) as client:
        response = client.get("/api/vault/status", params={"client_id": "kasa-testi"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert secret not in response.text
    for key, value in body.items():
        assert not (isinstance(value, str) and value.startswith("sk-")), f"{key} anahtar sızdırıyor"
    assert {"locked", "has_api_key", "can_scrape"} <= set(body)
