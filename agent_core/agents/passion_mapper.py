"""Tutku lensi — hedefin neşe, yaratıcılık ve entelektüel ilgi alanları.

``TargetPsycheProfiler`` omurgasına bağlı ince kabuk; çıktı ``PassionProfile``.
Yalnız somut paylaşımlardan/dilden kanıt toplar, ilgi uydurmaz; boş kanıt
durumunda liste boş kalır ve neden yazılır.

Ortak köprü önerisi (``AuthenticBridge``) bu profilden beslenir.
"""

import logging
from typing import Dict, Any
from agent_core.domain.memory_models import PassionProfile
from agent_core.agents.target_psyche_profiler import TargetPsycheProfiler

logger = logging.getLogger(__name__)

class PassionMapperAgent(TargetPsycheProfiler):
    """
    Hedefin neşe, yaratıcılık, tutku ve entelektüel ilgi alanlarını 
    somut paylaşımlarından ve dilinden haritalandıran ajan.
    (TargetPsycheProfiler omurgasına bağlı tutku lensi).
    """

    async def execute(self, payload: Dict[str, Any]) -> PassionProfile:
        return await self.profile_passions(payload)
