"""ASPASIA PROMOTION — merkezi doğal-dil arayüzünün okuma/komut katmanı.

Mimari sözleşme:
- Aspasia = doğal-zekâ arayüzü (seyirci + açıklayıcı + komut formüle edici).
- Orchestrator Core = api.run_mission + PinealExecutor + TaskLifecycleRegistry
  (BURADAN YÖNETİLMEZ, BURAYA TAKLİT YAZILMAZ; yalnız dispatch ile tetiklenir).
- Agent planlaması = CognitiveRouter (SoT). Komut katmanı ajan listesi UYDURMAZ.
- Routing/kota/harcama yetkisi = LLMGateway + final_routing_policy. Bu modül
  yalnız okur; set_key/quota/spend/provider HTTP mutasyonu YAPMAZ ve YAPAMAZ.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import contextlib
import os
import re
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from agent_core.services import final_routing_policy as policy
from agent_core.services.cognitive_router import GOAL_FOCUS

# Goal sozlesmesi COGNITIVE_ROUTER'da turetilir (tek kaynak); Aspasia kendi
# vocabulariesini ICATMAZ — Literal, gercek GOAL_FOCUS anahtarlarindan olusur.
_GOAL_IDS = tuple(GOAL_FOCUS.keys())


def _status_value(status: Any) -> Any:
    """PipelineStatus/str/None -> karsilastirilabilir durum degeri.

    [FAZ 2 / N1-ikizi] Python 3.11'de f"{PipelineStatus.COMPLETED}" ->
    'PipelineStatus.COMPLETED' (deger degil, repr). Aspasia metinleri ve
    /api/aspasia/state bununla normalize edilir; FastAPI zaten enum'u
    value olarak serilestirdigi icin API JSON ciktisi DEGISTMEZ.
    """
    value = getattr(status, "value", status)
    return str(value).lower() if value is not None else None


def _normalize_target_url(url: Optional[str]) -> str:
    """[FAZ 2] Paylasim artiklarini dusur, katiligi koru.

    Mobil paylasim URL'leri (?igsh=, ?utm_source=, #fragman) ayni profile
    isaret eder; _TARGET_RE eslesmesi oncesi dusurulur. Host/path kurali
    DEGISMEZ: yalniz https + instagram.com|instagr.am + tek segment kabul
    edilir (lookalike host ve hedefsiz komut yine reddedilir).
    """
    candidate = (url or "").strip()
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ""
    if parts.scheme.lower() != "https" or not parts.netloc:
        return ""
    return f"https://{parts.netloc}{parts.path}"

# ---------------------------------------------------------------- inspectors


class RoutingInspector:
    """Read-only explanation of the agent-chain + provider cost ladder."""

    def __init__(self, gateway: Any):
        self._gateway = gateway

    def explain(self, agent_name: str, task: str = "dialogue") -> Dict[str, Any]:
        gw = self._gateway
        chain: List[str] = []
        try:
            chain = list(gw.get_agent_chain(agent_name, task))
        except Exception as exc:  # pragma: no cover - defensive read
            return {"agent": agent_name, "error": f"{type(exc).__name__}: {exc}"[:140]}
        env_var = f"OPENROUTER_AGENT_CHAIN_{agent_name.upper()}"
        if os.getenv(env_var):
            source = "env_override"
        elif agent_name in getattr(gw, "AGENT_CHAINS", {}):
            source = "agent_matrix"
        else:
            source = "task_chain"
        variants: List[Dict[str, Any]] = []
        if chain:
            first = chain[0]
            try:
                for route in gw.agent_route_variants(first):
                    if route is None:
                        variants.append({
                            "route_key": f"{first}@openrouter",
                            "provider": "openrouter",
                            "endpoint": getattr(gw, "openrouter_base_url", ""),
                            "pricing": gw.MODEL_PRICING.get(first),
                            "tier": "pool-provider",
                        })
                    else:
                        entry = {
                            "route_key": f"{route.model}@{route.provider_id}",
                            "provider": route.provider_id,
                            "endpoint": route.base_url,
                            "pricing": route.pricing,
                            "tier": (
                                "free" if not route.pricing
                                or (route.pricing["in"] == 0 and route.pricing["out"] == 0)
                                else "paid"
                            ),
                        }
                        if route.list_input_per_million_usd:
                            entry["list_pricing"] = {
                                "in": route.list_input_per_million_usd,
                                "out": route.list_output_per_million_usd,
                            }
                            entry["discount_pct"] = round(
                                (1.0 - route.input_per_million_usd / route.list_input_per_million_usd)
                                * 100.0, 1
                            )
                        variants.append(entry)
            except Exception as exc:  # pragma: no cover
                variants.append({"error": f"{type(exc).__name__}: {exc}"[:120]})
        # FAZ 3: elenen saglayicilar + nedenleri (havuz gorunurlugu).
        # route_diagnostics yoksa (eski sahte gateway) bos kalir; explain asla kirilmaz.
        blocked: List[Dict[str, Any]] = []
        if chain:
            diagnostics = getattr(gw, "route_diagnostics", None)
            if callable(diagnostics):
                try:
                    info = diagnostics(chain[0]) or {}
                    for provider_id, entry in (info.get("skipped") or {}).items():
                        if isinstance(entry, dict):
                            blocked.append({
                                "provider": provider_id,
                                "reason": entry.get("reason"),
                                "key_present": bool(entry.get("key_present")),
                            })
                except Exception:
                    blocked = []
        return {
            "agent": agent_name,
            "task": task,
            "chain": chain,
            "chain_source": source,
            "selected": variants[0] if variants else None,
            "alternatives": variants[1:],
            "blocked": blocked,
            "fallback_rule": (
                "gecici hata -> siradaki rota, o biterse siradaki model; "
                "spend-cap/paid-escalation/unknown-pricing/substitution reddi -> ZINCIR DURUR"
            ),
        }


class TelemetryReader:
    """Bounded view over the gateway call log; no parallel telemetry store."""

    _FIELDS = (
        "call_id", "model", "requested_model", "actual_model", "provider",
        "route_key", "fallback_reason", "chain_source", "quota_status",
        "error", "duration_ms", "cost_usd", "agent_id",
    )

    def __init__(self, gateway: Any, limit: int = 40):
        self._gateway = gateway
        self._limit = limit

    def recent(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for record in list(getattr(self._gateway, "call_log", []))[-self._limit:]:
            if agent_id and record.get("agent_id") != agent_id:
                continue
            rows.append({k: record.get(k) for k in self._FIELDS if record.get(k) is not None})
        return rows

    def anomalies(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"fallbacks": [], "substitution_denials": [], "model_mismatches": []}
        denial_re = re.compile(
            r"MODEL_SUBSTITUTION_DENIED: requested '([^']+)' but provider returned '([^']+)'"
        )
        for record in list(getattr(self._gateway, "call_log", []))[-self._limit:]:
            if record.get("fallback_reason"):
                out["fallbacks"].append({
                    "model": record.get("model"),
                    "provider": record.get("provider"),
                    "reason": record.get("fallback_reason"),
                })
            error_text = str(record.get("error", ""))
            if "MODEL_SUBSTITUTION_DENIED" in error_text:
                match = denial_re.search(error_text)
                # STRUCTURED field once (ROUTING-HARDENING); eski kayitlarda
                # error-metin regex'i fallback'tir — hicbir alan uydurulmaz.
                out["substitution_denials"].append({
                    "model": record.get("model"),
                    "provider": record.get("provider"),
                    "requested_model": (record.get("requested_model")
                                        or (match.group(1) if match else None)),
                    "actual_model": (match.group(2) if match
                                     else record.get("actual_model")),
                })
            requested = record.get("requested_model")
            actual = record.get("actual_model")
            if requested and actual and requested != actual:
                out["model_mismatches"].append({"requested": requested, "actual": actual,
                                                "provider": record.get("provider")})
        return out


class QuotaReader:
    """Reads the QuotaGovernor + policy QUOTAS; unknown stays 'unknown'."""

    def __init__(self, governor: Any = None, gateway: Any = None):
        self._governor = governor
        self._gateway = gateway

    def _gov(self):
        if self._governor is None:
            accessor = getattr(self._gateway, "_quota_governor", None)
            if not callable(accessor):
                # GOZLEM DURUMUNUN TEK SoT'U gateway governor'idir. Bos bir
                # governor UYDURMAK "HEALTHY" demek olurdu -> unavailable.
                return None
            self._governor = accessor()
        return self._governor

    def snapshot(self, provider: str) -> Dict[str, Any]:
        limits: Dict[str, Any] = {}
        for dim, value in policy.QUOTAS.get(provider, {}).items():
            limits[dim] = "unknown" if value in (None, policy.QUOTA_UNKNOWN) else value
        gov = self._gov()
        if gov is None:
            status, remaining, source = "unavailable", None, None
        else:
            try:
                snap = gov.snapshot(provider)
                # [FAZ 2] .name ("UNKNOWN") degil .value ("unknown"): digest
                # uyelik testi ve limits "unknown" sozlesmesi lowercase'dir.
                # Buyuk-harf ad, bilinmeyeni gozlemlenmis gibi gosteriyordu.
                status = getattr(snap.status, "value", snap.status)
                status = str(status) if status is not None else "unknown"
                remaining = getattr(snap, "remaining_fraction", None)
                source = getattr(snap, "source", None)
            except Exception:  # pragma: no cover
                status, remaining, source = "unavailable", None, None
        return {
            "provider": provider,
            "limits": limits,
            "status": status,
            "remaining_fraction": remaining,
            "source": source,
            "note": "unknown limits are NEVER treated as unlimited (fail-closed doctrine)",
        }


class CostReader:
    """Budget snapshot + effective-vs-list pricing (Nous doctrine)."""

    def __init__(self, gateway: Any):
        self._gateway = gateway

    def snapshot(self) -> Dict[str, Any]:
        try:
            return dict(self._gateway.budget_status())
        except Exception as exc:  # pragma: no cover
            return {"error": f"{type(exc).__name__}"}

    def pricing_overview(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for key, spec in policy.ROUTES.items():
            row = {
                "route_key": key,
                "model": spec.model,
                "provider": spec.provider,
                "tier": spec.tier,
                "effective": {"in": spec.input_per_million_usd, "out": spec.output_per_million_usd},
            }
            if spec.list_input_per_million_usd is not None:
                row["list"] = {"in": spec.list_input_per_million_usd,
                               "out": spec.list_output_per_million_usd}
                row["discount_pct"] = round(
                    (1.0 - spec.input_per_million_usd / spec.list_input_per_million_usd) * 100.0, 1
                )
            rows.append(row)
        return rows


class AgentInspector:
    """Reads the REAL registry (executor.agents) + lifecycle snapshot."""

    def __init__(self, executor: Any = None):
        self._executor = executor

    def registry(self) -> List[str]:
        agents = getattr(self._executor, "agents", {}) or {}
        return sorted(agents.keys())

    def run_status(self, room_state: Any) -> Dict[str, Any]:
        if not isinstance(room_state, dict):
            return {"state": "no-room"}
        active = room_state.get("active_tasks") or {}
        if not active:
            return {"state": "idle"}
        snapshot = list(active.values())[-1]
        if not isinstance(snapshot, dict):
            snapshot = {
                "task_id": getattr(snapshot, "task_id", None),
                "status": getattr(snapshot, "status", None),
                "planned_agents": getattr(snapshot, "planned_agents", []),
                "completed_agents": getattr(snapshot, "completed_agents", []),
                "current_agent": getattr(snapshot, "current_agent", None),
                "agent_runs": getattr(snapshot, "agent_runs", {}),
            }
        raw_status = snapshot.get("status")
        # [FAZ 2] status normalize edilir (enum repr sizintisi yok); is_final
        # ayni normalize degerden turetilir (cift-kaynak karsilastirma yok).
        norm_status = _status_value(raw_status)
        return {
            "task_id": snapshot.get("task_id"),
            "status": norm_status,
            # Faz-6: snapshot terminal durumdaysa ARTIK CANLI degildir;
            # canliyi "bayat" diye etiketle — Aspasia kanonik kaynaga yonlendirilir.
            "is_final": (norm_status or "") in FINAL_TASK_STATUSES,
            "planned": snapshot.get("planned_agents") or [],
            "completed": snapshot.get("completed_agents") or [],
            "current": snapshot.get("current_agent"),
            "runs": {
                name: {"status": run.get("status") if isinstance(run, dict) else
                       getattr(run, "status", None)}
                for name, run in (snapshot.get("agent_runs") or {}).items()
            },
        }


# ---------------------------------------------------------------- commands

class AspasiaIntent(BaseModel):
    """LLM-uretimli YAPILANDIRILMIS niyet sozlesmesi.

    extra='forbid': model/provider/quota gibi alanlar UYDURULAMAZ — routing
    ve planlama yetkisi Aspasia'da degildir (CognitiveRouter + LLMGateway SoT).
    `goals`: kullanicinin AMACI tasir (semantic plan), AJAN LISTESI degil —
    ajan secimi CognitiveRouter'ın kanit/kabiliyet kapilarinda kalir.
    """

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="none", pattern="^(none|explain_status|run_profile_analysis)$")
    target_url: Optional[str] = None
    rationale: Optional[str] = None
    goals: List[Literal[_GOAL_IDS]] = Field(default_factory=list)


# Hedef dogrulama: yalnizca mevcut scraper sozlesmesinin gercek host'lari.
# (Ornek-uydurmama doktrini [009]: placeholder veri ASLA uretilmez.)
_TARGET_RE = re.compile(r"^https://(www\.)?(instagram\.com|instagr\.am)/[A-Za-z0-9._@-]{1,64}/?$")

_GOAL_DOC = "\n".join(f'- "{g}": {", ".join(agents)}' for g, agents in GOAL_FOCUS.items())

_INTENT_INSTRUCTION = (
    "Kullanicinin cumlesini siniflandir. Yalniz su niyetler gecerlidir:\n"
    '- "run_profile_analysis": kullanici belirli bir Instagram profilini inceletmek istiyor '
    've mesajda acik bir profil URL\'i var -> target_url alanina BIREBIR URL yaz.\n'
    '- "explain_status": kullanici sistem/ajan/analiz durumu hakkinda bilgi istiyor.\n'
    '- "none": hicbiri.\n'
    "URL mesajda ACIKCA yoksa uydurma; intent='none' dondur.\n\n"
    "goals: kullanicinin AMACINI tasir; AJAN ISMI YAZMAZSIN. Gecerli goal id'leri "
    "(baska isim UYDURMA; message'da acik karsiligi yoksa hic goal ekleme):\n"
    + _GOAL_DOC + "\n"
    "Ornek: 'cümlesinde çelişki arıyorsa' -> contradiction_detection. "
    "Ek odak yoksa goals: [\"profile_analysis\"].\n\n"
    "JSON:\n"
    '{{"intent": "...", "target_url": null, "rationale": "tek cümle", '
    '"goals": ["..."]}}\n\n'
    "KULLANICI MESAJI:\n{text}\n"
)


class AspasiaCommandResult(BaseModel):
    command_id: str
    accepted: bool
    intent: str
    task_id: Optional[str] = None
    reason: Optional[str] = None


class AspasiaCommandGateway:
    """Single sanctioned WRITE path for Aspasia: intent -> validation -> dispatch.

    `dispatch(spec: dict) -> Optional[str]` is injected by the real orchestrator
    wiring (api.py) and MUST route through the same task-launch path a human
    uses (/api/initiate semantics): rate limits, lifecycle transitions,
    executor planning. This gateway holds no provider client, no key, no
    quota/spend mutation surface.
    """

    def __init__(self, dispatch: Callable[[Dict[str, Any]], Optional[str]], *, gateway: Any = None):
        self._dispatch = dispatch
        self._gateway = gateway
        self._audit: deque[Dict[str, Any]] = deque(maxlen=64)

    # -- audit ---------------------------------------------------------
    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    def _record(self, **fields: Any) -> Dict[str, Any]:
        entry = {"created_at": datetime.now(timezone.utc).isoformat(), **fields}
        self._audit.append(entry)
        return entry

    # -- submit --------------------------------------------------------
    async def submit(self, user_message: str, client_id: str = "default") -> AspasiaCommandResult:
        command_id = uuid.uuid4().hex[:12]
        gateway = self._gateway
        if gateway is None:
            self._record(command_id=command_id, status="rejected", reason="gateway_unavailable")
            return AspasiaCommandResult(
                command_id=command_id, accepted=False, intent="none",
                reason="gateway_unavailable",
            )
        try:
            # Niyet cikarimi AYNI routing yiginindan gecer (aspasia chain'i,
            # provider merdiveni, spend/quota gate'leri) — ayrica bir "akilli
            # LLM cagrisi" kanali ACILMAZ. Cagri, MEVCUT capture_calls kapsami
            # altinda agent_id=aspasia ile etiketlenir (paralel telemetri yok).
            capture = getattr(gateway, "capture_calls", None)
            scope_ctx = capture(None, "aspasia") if callable(capture) else contextlib.nullcontext()
            with scope_ctx:
                intent: AspasiaIntent = await gateway.query_json_chain(
                    prompt=_INTENT_INSTRUCTION.format(text=(user_message or "")[:1200]),
                    schema=AspasiaIntent,
                    task="dialogue",
                    agent_name="aspasia",
                )
        except Exception as exc:
            self._record(command_id=command_id, status="intent_unavailable",
                         error=f"{type(exc).__name__}"[:80])
            return AspasiaCommandResult(
                command_id=command_id, accepted=False, intent="none",
                reason="intent_unavailable",
            )

        if intent.intent == "none":
            self._record(command_id=command_id, status="no_action", intent="none")
            return AspasiaCommandResult(command_id=command_id, accepted=True,
                                        intent="none", reason="no_action")
        if intent.intent == "explain_status":
            self._record(command_id=command_id, status="read_only", intent=intent.intent)
            return AspasiaCommandResult(command_id=command_id, accepted=True,
                                        intent=intent.intent, reason="read_only")
        # run_profile_analysis — TEK yazma eylemi; hedef dogrulama sart.
        # [FAZ 2] Eslesme normalize URL uzerinden (?igsh=/fragment dusmus);
        # dispatch'e de normalize URL gider (asagi akis ayni hedefi gorur).
        url = _normalize_target_url(intent.target_url)
        if not _TARGET_RE.match(url):
            self._record(command_id=command_id, status="rejected", intent=intent.intent,
                         reason="unsupported_or_missing_target")
            return AspasiaCommandResult(command_id=command_id, accepted=False,
                                        intent=intent.intent,
                                        reason="unsupported_or_missing_target")
        try:
            task_id = self._dispatch({
                "client_id": client_id,
                "target_url": url,
                # AMAC KAYBI FIX: goal'lar dispatch'e aynen tasinir; plan
                # yetkisi CognitiveRouter'da kalir (goal != agent listesi).
                "goals": list(intent.goals),
            })
        except Exception as exc:
            self._record(command_id=command_id, status="dispatch_failed",
                         intent=intent.intent, error=f"{type(exc).__name__}"[:80])
            return AspasiaCommandResult(command_id=command_id, accepted=False,
                                        intent=intent.intent, reason="dispatch_failed")
        # [AUDIT N1] dispatch "None" dönerse görev BAŞLATILMAMIŞTIR (oda
        # doymuş / kapasite reddi). Eski kod bunu accepted=True + task_id=None
        # olarak "dispatched" kaydediyordu (yalan kabul).
        if task_id is None:
            self._record(command_id=command_id, status="rejected",
                         intent=intent.intent, reason="dispatch_rejected")
            return AspasiaCommandResult(command_id=command_id, accepted=False,
                                        intent=intent.intent,
                                        reason="dispatch_rejected")
        self._record(command_id=command_id, status="dispatched", intent=intent.intent,
                     task_id=task_id, goals=list(intent.goals),
                     target_host=re.sub(r"^https://", "", url).split("/")[0])
        return AspasiaCommandResult(command_id=command_id, accepted=True,
                                    intent=intent.intent, task_id=task_id)


# Kanonik sonuc icin terminal durumlar (PipelineStatus degerleri) — snapshot
# bunlardan birindeyse ARTIK CANLI degildir; kanonik kaynak CanonicalMemory'dir.
# [FAZ 2] backend.api._TERMINAL_PIPELINE_STATES ile SENKRON tutulur: kullanici
# iptali/durdurmasi (cancelled/canceled/halted_user) da terminaldir; eksik
# kalirsa Aspasia bayat snapshot'i canli sanir ve SONUC satiri uretmez.
# Senkron kilidi: tests/unit/test_aspasia_state_consistency.py.
FINAL_TASK_STATUSES = {
    "completed", "partially_completed", "halted_evidence", "halted_critical",
    "halted_frequency", "failed",
    # [BOSS-8] Görev bütçesi doldu → terminal; yoksa Aspasia bayat snapshot'ı
    # canlı sanıp sonuç satırı üretmez.
    "timed_out",
    "cancelled", "canceled", "halted_user",
}


def extract_depth_digest(evidence: Any) -> Optional[Dict[str, Any]]:
    """HÜKÜM: kanıt zincirinden derinlik özetini OKUR (hesaplamaz).

    verdict ok + sayısal telafi/reaksiyon yoksa None döner (Aspasia susar;
    eksik özet sayı uydurularak tamamlanmaz). Birden çok mühür varsa SON
    mühür geçerlidir (zincir sırası = zaman sırası).
    """
    if not isinstance(evidence, list):
        return None
    sealed: Any = None
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        if entry.get("agent") != "psychodynamic_depth":
            continue
        result = entry.get("result")
        depth = result.get("depth") if isinstance(result, dict) else None
        if isinstance(depth, dict):
            sealed = depth
    if not isinstance(sealed, dict) or sealed.get("verdict") != "ok":
        return None
    comp = sealed.get("compensation_index")
    react = sealed.get("reaction_formation_index")
    if not isinstance(comp, (int, float)) or isinstance(comp, bool):
        return None
    if not isinstance(react, (int, float)) or isinstance(react, bool):
        return None
    channels = sealed.get("channels")
    rhythm = channels.get("rhythm") if isinstance(channels, dict) else None
    rsig = rhythm.get("signals") if isinstance(rhythm, dict) else None
    rsig = rsig if isinstance(rsig, dict) else {}
    kinds = rsig.get("rupture_kinds")
    return {
        "verdict": "ok",
        "confidence": sealed.get("confidence"),
        "compensation_index": comp,
        "reaction_formation_index": react,
        "epistemic_weights": sealed.get("epistemic_weights"),
        "n_ruptures": rsig.get("n_ruptures"),
        "n_regimes": rsig.get("n_regimes"),
        "rupture_kinds": list(kinds) if isinstance(kinds, list) else [],
        "reason": sealed.get("reason"),
    }


def _depth_digest_line(depth: Any, sep: str = " derinlik: ") -> str:
    """Derinlik özeti -> olgu soneki; özet yoksa '' (Aspasia susar)."""
    if not isinstance(depth, dict):
        return ""
    comp = depth.get("compensation_index")
    react = depth.get("reaction_formation_index")
    n_rup = depth.get("n_ruptures")
    kinds = depth.get("rupture_kinds") or []
    if not isinstance(comp, (int, float)) or isinstance(comp, bool):
        return ""
    if not isinstance(react, (int, float)) or isinstance(react, bool):
        return ""
    kinds_txt = "+".join(k for k in kinds if isinstance(k, str)) if kinds else "-"
    n_txt = n_rup if isinstance(n_rup, int) and not isinstance(n_rup, bool) else "?"
    return (f"{sep}telafi={comp:.2f} reaksiyon={react:.2f} "
            f"kırılma={n_txt} [{kinds_txt}]")


class MissionResultReader:
    """CanonicalMemory uzerinden salt-okur sonuc ozeti — PARALEL STORE YOK.

    Corrupted kanonik kayit sessizce 'bos' sayilmaz (fail-closed bellek
    sozlesmesi): 'corrupted' doner, Aspasia kullaniciya kurtarma gerekir der.
    """

    @staticmethod
    def latest_task_id(room_state: Any) -> Optional[str]:
        if not isinstance(room_state, dict):
            return None
        active = room_state.get("active_tasks") or {}
        if not active:
            return None
        return list(active.keys())[-1]

    @staticmethod
    def latest_finished_task_id(room_state: Any) -> Optional[str]:
        if not isinstance(room_state, dict):
            return None
        active = room_state.get("active_tasks") or {}
        for task_id in reversed(list(active.keys())):
            snap = active[task_id]
            status = (snap.get("status") if isinstance(snap, dict)
                      else getattr(snap, "status", None))
            if str(getattr(status, "value", status)) in FINAL_TASK_STATUSES:
                return task_id
        return None

    def read(self, executor: Any, task_id: Optional[str]) -> Dict[str, Any]:
        if not task_id:
            return {"state": "no-task"}
        memory = getattr(executor, "memory", None)
        getter = getattr(memory, "get_task_memory", None)
        if not callable(getter):
            return {"state": "unsupported"}
        try:
            doc = getter(task_id)
        except Exception as exc:
            return {"state": "corrupted",
                    "error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        if not doc:
            # Eksik dosya = bos hafiza (CanonicalMemory sozlesmesi), uydurma yok.
            return {"state": "missing", "task_id": task_id}
        evidence = doc.get("evidence") or []
        agents = sorted({
            e.get("agent") for e in evidence
            if isinstance(e, dict) and e.get("agent")
        })
        return {
            "state": "ok",
            "task_id": doc.get("task_id", task_id),
            "last_updated": doc.get("last_updated"),
            "overall_confidence": doc.get("confidence"),
            "evidence_count": len(evidence),
            "agents": agents,
            "depth": extract_depth_digest(evidence),
        }


class DiskMemoryBridge:
    """RAM bosken CanonicalMemory (disk) salt-okur koprusu — PARALEL STORE YOK.

    Kaynak: executor.memory (CanonicalMemory SoT). Dizin LISTELENIR, her aday
    inspect_task_memory ile fail-closed OKUNUR (bozuk dosya asla icerik gibi
    sunulmaz; kayip dosya zaten listede yoktur). En fazla _MAX_INSPECT aday
    incelenir (dosya-adi ters-sirasi oncelikli: op_YYYYMMDDHHMMSS_* kronolojiktir).
    """

    _MAX_INSPECT = 25
    _MAX_REPORT = 3

    def __init__(self, executor: Any = None):
        self._executor = executor

    def _storage_dir(self) -> Optional[str]:
        memory = getattr(self._executor, "memory", None)
        path = getattr(memory, "storage_path", None)
        if not path or not isinstance(path, str):
            return None
        return path if os.path.isdir(path) else None

    def latest(self) -> Dict[str, Any]:
        """{'state': ok|empty|unsupported, 'tasks': [...], 'corrupted': N}."""
        memory = getattr(self._executor, "memory", None)
        inspect = getattr(memory, "inspect_task_memory", None)
        storage = self._storage_dir()
        if not callable(inspect) or storage is None:
            return {"state": "unsupported", "tasks": [], "corrupted": 0}
        try:
            names = sorted(
                (n for n in os.listdir(storage)
                 if n.endswith(".json") and n != "learnings.json"),
                reverse=True,
            )
        except OSError:
            return {"state": "unsupported", "tasks": [], "corrupted": 0}
        ready: List[Dict[str, Any]] = []
        corrupted = 0
        for name in names[: self._MAX_INSPECT]:
            task_id = name[: -len(".json")]
            # Karantina/yedek artefaktlari (*.corrupt.*, *.tmp) .json ile
            # bitmedigi icin listeye girmez; task_id disi kokler atlanir.
            if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
                continue
            try:
                result = inspect(task_id)
            except Exception:
                corrupted += 1
                continue
            if not isinstance(result, dict):
                continue
            if result.get("state") == "CORRUPTED":
                corrupted += 1
                continue
            if result.get("state") != "READY":
                continue
            data = result.get("data") or {}
            evidence = data.get("evidence")
            ready.append({
                "task_id": task_id,
                "last_updated": data.get("last_updated"),
                "evidence_count": len(evidence) if isinstance(evidence, list) else None,
                "confidence": data.get("confidence"),
                "depth": extract_depth_digest(evidence),
            })
            if len(ready) >= self._MAX_REPORT:
                break
        if not ready and not corrupted:
            return {"state": "empty", "tasks": [], "corrupted": 0}
        return {"state": "ok", "tasks": ready, "corrupted": corrupted}


def build_oversight_digest(
    gateway: Any,
    room_state: Any = None,
    executor: Any = None,
    command_gateway: Optional[AspasiaCommandGateway] = None,
    last_agent: Optional[str] = None,
) -> str:
    """Compact, source-backed state block for the ASPASIA system prompt.

    Dürüstlük kurali: satir yalnizca OKUNABILIR kanit varsa eklenir. "veri
    yok" satirlari bloku gürültüleme; hic içerik yoksa bos string döner ve
    chat() DENETİM bloğunu hic açmaz (uydurma digest yok).
    """
    lines: List[str] = []
    has_content = False
    try:
        routing = RoutingInspector(gateway).explain(last_agent or "friction_detector")
        chain = routing.get("chain") or []
        if chain:
            has_content = True
            selected = routing.get("selected") or {}
            # FAZ 2-EK: aday rota, gozlemlenmis gercek gibi sunulmaz. Sistem
            # bostayken (call_log'da bu ajana ait cagri yokken) uretilen
            # ROUTING satiri PLAN'dir; Aspasia bunu "calisti" diye anlatirsa
            # halusinasyondur. Cagri varsa son gozlem (model@provider) eklenir.
            observed = TelemetryReader(gateway).recent(agent_id=str(routing.get("agent")))
            if observed:
                kind = "ROUTING"
                last = observed[-1]
                fact_suffix = (
                    f" gozlemlenen={last.get('actual_model') or last.get('model')}"
                    f"@{last.get('provider')}"
                )
            else:
                kind = "ROUTING-ADAY"
                fact_suffix = " (henüz çağrı yok; bu satır plan, gerçekleşmiş karar değil)"
            lines.append(
                kind + "[" + str(routing.get("agent")) + "]: "
                f"chain={'>'.join(chain)} kaynak={routing.get('chain_source')}"
                + (f" ilk-siradaki={selected.get('route_key')}"
                   if selected else "")
                + (f" indirim={selected.get('discount_pct')}%" if selected.get("discount_pct") else "")
                + fact_suffix
            )
    except Exception:  # pragma: no cover
        logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:746 (pass)')
    try:
        anomalies = TelemetryReader(gateway).anomalies()
        counts = {k: len(v) for k, v in anomalies.items()}
        if any(counts.values()):
            has_content = True
            lines.append(
                "TELEMETRI: fallback={fallbacks} substitution={substitution_denials} "
                "uyusmazlik={model_mismatches}".format(**counts)
            )
        # Faz-5: requested != actual AYRINTISI chat'e tasinir (call_log'dan
        # okunur; yeni store yok) — reddedilen ikame aciklanabilir olmali.
        for denial in anomalies["substitution_denials"][-2:]:
            lines.append(
                "SUBSTITUTION DENIED: istenen='" + str(denial.get("requested_model"))
                + "' saglayici dondurdu='" + str(denial.get("actual_model"))
                + "' (" + str(denial.get("provider")) + ") — ikame reddedildi, zincir durdu"
            )
    except Exception:  # pragma: no cover
        logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:765 (pass)')
    try:
        snap = CostReader(gateway).snapshot()
        if "error" not in snap:
            has_content = True
            lines.append(
                f"MALİYET: harcama=${snap.get('spend_usd', 0):.4f} rezerve=${snap.get('reserved_usd', 0):.4f} "
                f"limit={'sinirsiz' if not snap.get('cap_usd') else '$%.2f' % snap.get('cap_usd', 0)}"
            )
    except Exception:  # pragma: no cover
        logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:775 (pass)')
    try:
        quotas = []
        for provider in ("groq", "cerebras"):
            q = QuotaReader(gateway=gateway).snapshot(provider)
            if q["status"] not in ("unknown", "unavailable"):
                has_content = True
            quotas.append(f"{provider}:{q['status']}" + (
                f" kalan={round(q['remaining_fraction'] * 100)}%"
                if q.get("remaining_fraction") is not None else ""
            ))
        if quotas and has_content:
            lines.append("KOTA: " + " | ".join(quotas))
    except Exception:  # pragma: no cover
        logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:789 (pass)')
    try:
        # ROUTING-HARDENING: saglayici saglik devresi gorunur (gateway'in kendi
        # durumu okunur; yeni store yok). Bos ise satir eklenmez — gurultu yok.
        ph = getattr(gateway, "provider_health", None)
        if callable(ph):
            cooling = {k: v for k, v in ph().items() if v and v > 0}
            if cooling:
                has_content = True
                lines.append("SAĞLIK: " + " | ".join(
                    f"{p} cooldown={s:.0f}s" for p, s in sorted(cooling.items())))
    except Exception:  # pragma: no cover
        logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:801 (pass)')
    if executor is not None:
        try:
            status = AgentInspector(executor).run_status(room_state)
            if status.get("state") not in (None, "no-room", "idle") or status.get("task_id"):
                has_content = True
                stale = " [BAYAT-snapshot; kanonik: CanonicalMemory]" if status.get("is_final") else ""
                lines.append(
                    f"TASK: {status.get('task_id', '-')} durum={status.get('status', 'idle')} "
                    f"tamamlanan={len(status.get('completed') or [])}/{len(status.get('planned') or [])}"
                    + stale
                )
            # Faz-3/4: sonuc dongusu — kanonik hafiza OKUNUR (paralel store yok).
            finished = MissionResultReader.latest_finished_task_id(room_state)
            if finished:
                result = MissionResultReader().read(executor, finished)
                if result.get("state") == "ok":
                    has_content = True
                    conf = result.get("overall_confidence")
                    lines.append(
                        f"SONUÇ[{result.get('task_id')}]: güven={'%.2f' % conf if isinstance(conf, (int, float)) else '?'} "
                        f"kanıt={result.get('evidence_count')} "
                        f"ajanlar={','.join(result.get('agents') or []) or '-'} (CanonicalMemory)"
                        + _depth_digest_line(result.get("depth"))
                    )
                elif result.get("state") == "corrupted":
                    has_content = True
                    lines.append(
                        "SONUÇ: kanonik hafıza BOZUK — analiz özetlenemez, açık kurtarma gerekir "
                        f"({result.get('error')})"
                    )
                elif result.get("state") == "missing":
                    has_content = True
                    lines.append("SONUÇ: kanonik kayıt yok — görev henüz mühürlenmemiş olabilir")
            # RAM-DISK KOPRUSU: odada canli/bitmis gorev YOKSA (RAM bos) ve
            # diskte kanonik kayit VARSA, Aspasia diskten okur — RAM boslugu
            # "hicbir sey olmadi" diye anlatilmaz. RAM doluysa satir eklenmez.
            if not status.get("task_id") and not finished:
                disk = DiskMemoryBridge(executor).latest()
                if disk.get("state") == "ok":
                    has_content = True
                    chunks = []
                    for task in disk.get("tasks") or []:
                        conf = task.get("confidence")
                        chunks.append(
                            f"{task.get('task_id')}:kanıt={task.get('evidence_count')},"
                            f"güven={('%.2f' % conf) if isinstance(conf, (int, float)) else '?'}"
                            + _depth_digest_line(task.get("depth"), sep=",derinlik=")
                        )
                    suffix = ""
                    if disk.get("corrupted"):
                        suffix = f" bozuk={disk['corrupted']}(kurtarma-gerekir)"
                    lines.append(
                        "HAFIZA-DISK: " + (" | ".join(chunks) if chunks else "kayıt-yok")
                        + suffix + " (RAM boş; diskten okundu)"
                    )
        except Exception:  # pragma: no cover
            logger.warning('Suppressed exception observed at agent_core/aspasia/interface.py:858 (pass)')
    if command_gateway is not None:
        for entry in command_gateway.audit()[-3:]:
            has_content = True
            lines.append(
                f"KOMUT {entry.get('command_id')}: {entry.get('status')}"
                + (f" task={entry.get('task_id')}" if entry.get("task_id") else "")
                + (f" ({entry.get('reason')})" if entry.get("reason") else "")
            )
    return "\n".join(lines) if has_content else ""
