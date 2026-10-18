"""Bilişsel lens — hedefin düşünce kalıbı, tonu ve iletişim üslubu.

``TargetPsycheProfiler`` omurgasına bağlanan İNCE kabuk: işin tamamı ortak
profiler'da (tek gerçek kaynak, tek prompt sözleşmesi), burada yalnız hangi
lensin koşulacağı seçilir. ``execute`` girdisi tam payload'dır, çıktısı
``CognitiveStyle`` pydantic modelidir.

Omurgayı kopyalayıp ayrı bir prompt yazmak yasaktır: üç lens (tutku, sürtünme,
biliş) aynı kanıt dilbilgisini paylaşmak zorundadır.
Test: ``tests/unit/test_cognitive_profiler.py``.
"""

import logging
from typing import Dict, Any
from agent_core.domain.memory_models import CognitiveStyle
from agent_core.agents.target_psyche_profiler import TargetPsycheProfiler

logger = logging.getLogger(__name__)

class CognitiveProfilerAgent(TargetPsycheProfiler):
    """
    Hedefin dilbilimsel tonunu, iletişim üslubunu, karmaşıklık düzeyini
    ve sosyal yaklaşımını metinlerinden analiz eden ajan.
    (TargetPsycheProfiler omurgasına bağlı bilişsel lens).
    """

    async def execute(self, payload: Dict[str, Any]) -> CognitiveStyle:
        return await self.profile_cognitive(payload)

