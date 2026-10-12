"""Ajan canlılık işaretçisi (liveness beacon) sözleşmesi.

[AUDIT 2026-10-07 · Madde 3] Bu worker'ın DENETİM ÖNCESİ hâli, deponun
kendi [RÖNTGEN 2026-09-23] ilkesini ihlal ediyordu: 30 saniyede bir
koşulsuz ``tracker.set_ready(agent_id)`` çağırarak hiçbir ajan çalışmadan
"Ready" uyduruyor, üstelik gerçek koşuların yazdığı Active/Done/Error
durumlarını eziyordu. Bu dosya o davranışın GERİ GELMESİNİ engeller.

Örtülen sözleşmeler:
  1. İşaretçi ajan DURUM KANALINA yazmaz (``pineal:agent:status``).
  2. İşaretçi hiçbir zaman "Ready" (ve başka bir operasyonel durum) basmaz.
  3. Yayınlanan mesaj rolünü açıkça etiketler (``executes_analysis: false``).
  4. Redis erişilemezse işaretçi YAŞAR ve bunu mesajda açıkça belirtir.
  5. Durum sözlüğü, tracker'daki ``AgentStatus`` ile çatallanmaz.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from agent_core.workers import agent_worker
from agent_core.workers.agent_worker import (
    AGENT_STATUS_CHANNEL,
    BEACON_CHANNEL,
    BEACON_ROLE,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_READY,
    STATUS_WAIT,
    build_liveness_message,
    publish_liveness,
    run_worker,
)

# ─────────────────────────────────────────────────────────────────────────
# Yardımcı: yayınları kaydeden sahte veri yolu
# ─────────────────────────────────────────────────────────────────────────


class RecordingBus:
    """``publish`` çağrılarını kaydeder; istenirse hata fırlatır."""

    def __init__(self, *, fail: bool = False, connection_state: str = "connected"):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail
        self._connection_state = connection_state

    def connection_state(self) -> str:
        return self._connection_state

    async def publish(self, channel: str, message: dict) -> int:
        if self.fail:
            raise RuntimeError("redis erişilemiyor (test)")
        self.calls.append((channel, message))
        return 1

    @property
    def channels(self) -> list[str]:
        return [channel for channel, _ in self.calls]

    @property
    def messages(self) -> list[dict]:
        return [message for _, message in self.calls]


# ─────────────────────────────────────────────────────────────────────────
# 1) Mesaj içeriği
# ─────────────────────────────────────────────────────────────────────────


def test_liveness_message_declares_its_role_honestly():
    message = build_liveness_message("mirror_truth")

    assert message["type"] == "agent_beacon_liveness"
    assert message["agent_id"] == "mirror_truth"
    assert message["timestamp"]
    assert message["beacon"]["role"] == BEACON_ROLE
    # Kritik dürüstlük etiketi: bu süreç analiz YÜRÜTMEZ.
    assert message["beacon"]["executes_analysis"] is False
    assert message["beacon"]["alive"] is True


def test_liveness_message_carries_no_operational_status_claim():
    """Mesajda `status` alanı OLMAZ: ajanın durumu bu sürecin bileceği iş değil."""
    message = build_liveness_message("depth_analyst")
    assert "status" not in message
    assert "status" not in message["beacon"]

    flat = repr(message)
    for fabricated in (STATUS_READY, STATUS_ACTIVE, STATUS_DONE):
        # "Ready"/"Active"/"Done" hiçbir yerde operasyonel iddia olarak geçmez
        assert fabricated not in flat, f"mesaj operasyonel durum iddiası taşıyor: {fabricated}"


def test_liveness_message_reports_measured_links():
    message = build_liveness_message(
        "osint_investigator", redis_link=False, backend_link=True, alive=False
    )
    assert message["beacon"]["redis_link"] is False
    assert message["beacon"]["backend_link"] is True
    assert message["beacon"]["alive"] is False


# ─────────────────────────────────────────────────────────────────────────
# 2) Kanal ayrımı — asla ajan durum kanalına yazmaz
# ─────────────────────────────────────────────────────────────────────────


def test_publish_uses_only_the_beacon_channel():
    bus = RecordingBus()
    asyncio.run(publish_liveness(bus, "mirror_truth", redis_link=True, backend_link=True))

    assert bus.calls, "hiç yayın yapılmadı"
    assert set(bus.channels) == {BEACON_CHANNEL}
    assert AGENT_STATUS_CHANNEL not in bus.channels


def test_worker_never_writes_agent_status_channel():
    """[AUDIT] Eski kod buradan `set_ready` ile duruma yazıyordu — ezme riski."""
    bus = RecordingBus()
    asyncio.run(
        run_worker(
            "autonomous_verifier",
            bus=bus,
            heartbeat_interval=0,
            max_heartbeats=3,
            backend_url="",  # ağ sondası kapalı
        )
    )

    assert len(bus.calls) == 3, f"beklenen 3 yayın, gelen: {len(bus.calls)}"
    assert set(bus.channels) == {BEACON_CHANNEL}
    assert AGENT_STATUS_CHANNEL not in bus.channels, "işaretçi ajan durum kanalına yazdı!"


def test_worker_never_publishes_a_ready_status():
    """Her yayında sahte 'Ready' basan eski davranışın regresyon koruması."""
    bus = RecordingBus()
    asyncio.run(
        run_worker("human_behavior", bus=bus, heartbeat_interval=0, max_heartbeats=5, backend_url="")
    )

    for message in bus.messages:
        assert "status" not in message
        assert message["beacon"]["executes_analysis"] is False
        assert message["beacon"]["alive"] is True


def test_worker_does_not_touch_the_status_tracker(monkeypatch):
    """Tracker'a hiç dokunulmadığının doğrudan kanıtı.

    Tracker sınıfına kurulan bu casus, ``set_ready`` çağrılırsa testi
    KIRAR — çünkü bu modülün varlık sebebi tam da o çağrıyı önlemektir.
    """
    touched: list[str] = []

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003
        touched.append(args[1] if len(args) > 1 else "?")
        raise AssertionError("işaretçi ajan durumunu değiştirdi!")

    from agent_core.services.agent_status_tracker import AgentStatusTracker

    for name in ("set_ready", "set_active", "set_done", "set_error", "update_status"):
        monkeypatch.setattr(AgentStatusTracker, name, spy)

    bus = RecordingBus()
    asyncio.run(
        run_worker("pattern_interrupt", bus=bus, heartbeat_interval=0, max_heartbeats=2, backend_url="")
    )

    assert touched == [], f"işaretçi tracker'ı değiştirdi: {touched}"
    assert len(bus.calls) == 2


# ─────────────────────────────────────────────────────────────────────────
# 3) Dayanıklılık
# ─────────────────────────────────────────────────────────────────────────


def test_worker_survives_redis_failure_and_reports_it():
    """Redis erişilemezse işaretçi yaşar ve `redis_link: false` YAZAR (uydurmaz)."""
    bus = RecordingBus(fail=True, connection_state="disconnected")

    # Yayın hata fırsa fırlatır; işaretçi bunu yutup yoluna devam etmeli,
    # çünkü canlılık işaretçisinin işi "yaşadığını loglamak"tır.
    async def scenario():
        task = asyncio.create_task(
            run_worker("mirror_truth", bus=bus, heartbeat_interval=0, max_heartbeats=3, backend_url="")
        )
        await asyncio.sleep(0)
        # Redis yükseltmesi döngüyü kırarsa, en azından çökmediğini kanıtla.
        try:
            await asyncio.wait_for(task, timeout=2)
        except (TimeoutError, RuntimeError):
            task.cancel()

    asyncio.run(scenario())


def test_worker_reports_redis_link_false_when_not_connected():
    bus = RecordingBus(connection_state="disconnected")
    asyncio.run(
        run_worker("resonance_calculator", bus=bus, heartbeat_interval=0, max_heartbeats=1, backend_url="")
    )
    # bus enjekte edildiği için bağlantı durumu olduğu gibi taşınır
    assert bus.messages[0]["beacon"]["redis_link"] is None or bus.messages[0]["beacon"]["redis_link"] is False


def test_worker_publishes_offline_on_cancellation():
    """Kapanışta `alive: false` yayınlanır: sessiz kaybolma değil."""
    bus = RecordingBus()

    async def scenario():
        task = asyncio.create_task(
            run_worker(
                "authenticity_auditor",
                bus=bus,
                heartbeat_interval=0.01,
                backend_url="",
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert bus.messages, "kapanışta hiç yayın yapılmadı"
    assert bus.messages[-1]["beacon"]["alive"] is False


# ─────────────────────────────────────────────────────────────────────────
# 4) Sözlük çatallanması / statik dürüstlük
# ─────────────────────────────────────────────────────────────────────────


def test_status_constants_match_the_tracker_enum():
    """Kopya sözlük bayatlamasın: tracker'daki enum ile birebir aynı olmalı."""
    from agent_core.services.agent_status_tracker import AgentStatus

    assert STATUS_WAIT == AgentStatus.WAIT.value
    assert STATUS_READY == AgentStatus.READY.value
    assert STATUS_ACTIVE == AgentStatus.ACTIVE.value
    assert STATUS_DONE == AgentStatus.DONE.value
    assert STATUS_ERROR == AgentStatus.ERROR.value


def test_module_code_contains_no_status_fabrication():
    """Kaynak düzeyinde durum yazma ÇAĞRISI kalmadığının kanıtı.

    Düz metin taraması yetersiz: bu modülün docstring'i, eski kusurlu kodu
    ibret olsun diye ALINTILIYOR ("await tracker.set_ready(...)"). Bu yüzden
    kaynak AST ile ayrıştırılır ve yalnızca GERÇEK çağrılar incelenir;
    docstring/yorum içeriği yok sayılır.
    """
    import ast

    source = Path(agent_worker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    forbidden = {
        "set_ready",
        "set_active",
        "set_done",
        "set_error",
        "set_wait",
        "update_status",
        "publish_agent_status",
    }
    offenders = sorted(called_attributes & forbidden)
    assert not offenders, f"işaretçi kaynağında durum yazma çağrısı bulundu: {offenders}"


def test_module_docstring_states_it_does_not_execute_analysis():
    """Modülün ne OLMADIĞI belgelenmek zorunda: 'analiz yürütmez'."""
    doc = agent_worker.__doc__ or ""
    lowered = doc.lower()
    assert "analiz yürütmez" in lowered
    # Rol, makinece okunabilir sabitle aynı sözcüklerle geçmeli.
    assert BEACON_ROLE.replace("_", " ") in lowered


# ─────────────────────────────────────────────────────────────────────────
# 5) CLI
# ─────────────────────────────────────────────────────────────────────────


def test_cli_accepts_agent_id(monkeypatch):
    captured: dict = {}

    async def fake_run_worker(agent_id, **kwargs):
        captured["agent_id"] = agent_id
        captured.update(kwargs)

    import sys

    monkeypatch.setattr(agent_worker, "run_worker", fake_run_worker)
    monkeypatch.setattr(sys, "argv", ["agent_worker", "--agent-id", "depth_analyst"])

    agent_worker.main()

    assert captured["agent_id"] == "depth_analyst"
    assert captured["heartbeat_interval"] == 30.0


# ─────────────────────────────────────────────────────────────────────────
# 6) E-GÖZ2-1 — degraded_mode sözleşmesi (ölçülen düşüş beyan edilir)
# ─────────────────────────────────────────────────────────────────────────


def test_degraded_mode_true_only_on_measured_redis_failure():
    """`degraded_mode` yalnız ÖLÇÜLEN `redis_link is False` iken `True`."""
    assert build_liveness_message("a", redis_link=False)["beacon"]["degraded_mode"] is True
    assert build_liveness_message("a", redis_link=True)["beacon"]["degraded_mode"] is False


def test_degraded_mode_not_fabricated_when_unmeasured():
    """Ölçüm yokken `False` yazmak 'her şey yolunda' uydurması olur → `None`."""
    assert build_liveness_message("a")["beacon"]["degraded_mode"] is None
    assert build_liveness_message("a", redis_link=None)["beacon"]["degraded_mode"] is None


def test_publish_carries_degraded_flag_on_the_wire():
    """Yayın yolunda bayrak düşmez: False bağlantı → telde `degraded_mode: true`."""
    bus = RecordingBus()
    asyncio.run(publish_liveness(bus, "mirror_truth", redis_link=False, backend_link=True))
    assert bus.messages[0]["beacon"]["degraded_mode"] is True

    bus = RecordingBus()
    asyncio.run(publish_liveness(bus, "mirror_truth", redis_link=True, backend_link=True))
    assert bus.messages[0]["beacon"]["degraded_mode"] is False


# ─────────────────────────────────────────────────────────────────────────
# 7) E-GÖZ1-1 — sessiz yutma YOK (tek izinli dal: Windows sinyal kaydı)
# ─────────────────────────────────────────────────────────────────────────


def test_no_silent_except_pass_outside_the_windows_branch():
    """Worker'da logsuz `except: pass` YOK; tek istisna platform dalıdır.

    Bekçi (``scripts/audit_regression.py`` E-GÖZ1-1) aynı kuralı AST ile ölçer;
    bu test kuralı worker sözleşmesinin parçası olarak kilitler: biri sessiz
    bir kol eklerse İKİ yerden kırmızı yanar.
    """
    import ast as _ast

    source = Path(agent_worker.__file__).read_text(encoding="utf-8")
    tree = _ast.parse(source)

    offenders: list[str] = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.ExceptHandler):
            continue
        if not (len(node.body) == 1 and isinstance(node.body[0], _ast.Pass)):
            continue
        handler_type = node.type.id if isinstance(node.type, _ast.Name) else "<bare>"
        if handler_type == "NotImplementedError":
            continue  # izinli: Windows'ta sinyal kaydı (platform dalı)
        offenders.append(f"satır {node.lineno}: sessiz `except {handler_type}: pass`")

    assert not offenders, "sessiz yutma geri gelmiş: " + "; ".join(offenders)


def test_shutdown_publish_failure_is_logged_not_swallowed(caplog):
    """Kapanış kolundaki yayın arızası `WARNING` bırakır (E-GÖZ1-6 kilidi)."""
    import logging

    class _ShutdownFailingBus(RecordingBus):
        """Kalp atışları tutar, yalnız kapanış (`alive: false`) yayını düşer."""

        async def publish(self, channel: str, message: dict) -> int:
            if message.get("beacon", {}).get("alive") is False:
                raise RuntimeError("kapanış yayını düştü (test)")
            return await super().publish(channel, message)

    bus = _ShutdownFailingBus()

    async def scenario():
        task = asyncio.create_task(
            run_worker("mirror_truth", bus=bus, heartbeat_interval=999, backend_url="")
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    with caplog.at_level(logging.WARNING, logger="agent_worker"):
        asyncio.run(scenario())

    assert any(
        "kapanış bildirimi yayınlanamadı" in record.message for record in caplog.records
    ), "kapanış arızası loglanmadı — sessiz yutma geri gelmiş"
