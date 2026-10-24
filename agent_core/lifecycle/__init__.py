"""Boylamsal (longitudinal) yaşam kırılması hattı.

Not: ``agent_core/services/task_lifecycle.py`` GÖREV yaşam döngüsüdür (durum
makinesi); bu paket ise KİŞİNİN zamana yayılmış verisinden kişisel baseline,
sapma ve kırılma üretir. İkisi karıştırılmamalıdır.

Akış: ``observation_adapter`` → ``baseline_builder`` → ``deviation_detector``
→ ``cluster_analyzer`` → ``report``; tek giriş noktası ``pipeline``.
"""

from __future__ import annotations

from agent_core.lifecycle.pipeline import analyze_life_rupture
from agent_core.lifecycle.report import LifeRuptureReport

__all__ = ["LifeRuptureReport", "analyze_life_rupture"]
