"""Two-phase asynchronous 7-Pillar orchestrator."""

import asyncio
import logging

from agent_core.domain.pillar_models import FrequencyReport, SeismosReport, VoidReport
from agent_core.domain.pillar_wave2_models import FullPillarBundle, GravityReport, PulseReport, StrataReport

from .frequency_engine import FrequencyEngine
from .gravity_engine import GravityEngine
from .key_engine import KeyEngine
from .pulse_engine import PulseEngine
from .seismos_engine import SeismosEngine
from .strata_engine import StrataEngine
from .void_engine import VoidEngine

logger = logging.getLogger(__name__)


class PillarComponentError(RuntimeError):
    """A deterministic pillar component failed; never convert this to success-like output."""

    def __init__(self, component: str, cause: Exception):
        super().__init__(f"{component} failed: {type(cause).__name__}: {cause}")
        self.component = component
        self.cause = cause


class PillarOrchestrator:
    def __init__(self, frequency=None, seismos=None, void=None, strata=None, gravity=None, pulse=None, key=None):
        self.frequency = frequency or FrequencyEngine()
        self.seismos = seismos or SeismosEngine()
        self.void = void or VoidEngine()
        self.strata = strata or StrataEngine()
        self.gravity = gravity or GravityEngine()
        self.pulse = pulse or PulseEngine()
        self.key = key or KeyEngine()

    async def run(self, data):
        specs = [
            (self.frequency, FrequencyReport, "FREQUENCY"),
            (self.seismos, SeismosReport, "SEISMOS"),
            (self.void, VoidReport, "VOID"),
            (self.strata, StrataReport, "STRATA"),
            (self.gravity, GravityReport, "GRAVITY"),
            (self.pulse, PulseReport, "PULSE"),
        ]

        async def run_component(engine, _model, name):
            try:
                return await engine.analyze(data)
            except Exception as e:
                logger.exception("%s component failed", name)
                raise PillarComponentError(name, e) from e

        # Insufficient input is represented by each engine's typed
        # INSUFFICIENT_DATA report. Exceptions are actual failures and must
        # reach PinealExecutor's critical 7-pillar policy.
        f, s, v, st, g, p = await asyncio.gather(*(run_component(*x) for x in specs))
        try:
            k = await self.key.analyze(freq=f, seismos=s, void=v, strata=st, gravity=g, pulse=p)
        except Exception as e:
            logger.exception("KEY component failed")
            raise PillarComponentError("KEY", e) from e
        return FullPillarBundle(
            frequency=f, seismos=s, void=v, strata=st, gravity=g, pulse=p, key=k
        ).as_snapshot_fields()
