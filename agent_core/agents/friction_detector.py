"""Sürtünme lensi — hedefin sınırları, hassasiyetleri ve tükenme noktaları.

``TargetPsycheProfiler`` omurgasına bağlı ince kabuk; ayrıştırma, kanıt
disiplini ve model çağrısı ortak profiler'dadır. Çıkış
``FrictionProfile``'dır ve mesaj üretiminde "dokunulmaz sınır" listesi olarak
kullanılır (bkz. ``pattern_interrupt``).

Bu lens ASLA teşhis koymaz: yalnız gözlenen ifadeyi/davranışı raporlar.
Test: ``tests/unit/test_friction_detector.py``.
"""

import logging
from typing import Dict, Any
from agent_core.domain.memory_models import FrictionProfile
from agent_core.agents.target_psyche_profiler import TargetPsycheProfiler

logger = logging.getLogger(__name__)

class FrictionDetectorAgent(TargetPsycheProfiler):
    """
    Hedefin sınırlarını, hassasiyetlerini, yorulma/şikayet noktalarını
    ve mesafeli durduğu durumları saygılı ve kanıta dayalı analiz eden ajan.
    (TargetPsycheProfiler omurgasına bağlı sürtünme lensi).
    """

    async def execute(self, payload: Dict[str, Any]) -> FrictionProfile:
        return await self.profile_frictions(payload)

