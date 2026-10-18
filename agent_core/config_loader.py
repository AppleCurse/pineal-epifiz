"""Karar konfigürasyonu yükleyicisi — eşikler kod içine GÖMÜLMEZ.

``config/decision_config.yaml`` bir kez okunur ve tipli iki modele dönüşür:
``DecisionConfig`` (global karar eşikleri) ve ``AgentThresholds`` (ajan bazlı
ağırlık/timeout). ``get_agent_config(agent_name)`` ajan adına göre ayar döner,
tanımsız ajan güvenli varsayılana düşer.

Dosya yoksa/bozuksa varsayılanlar kullanılır ve durum raporlanır — sessiz
"her şey yolunda" izlenimi verilmez.

Tüketici: ``task_executor``, ``decision_engine``, ``uncertainty_engine``.
Test: ``tests/unit/test_config_contract.py``.
"""

from pathlib import Path
from typing import Any, Dict, List
import yaml
from dataclasses import dataclass, field
from functools import lru_cache

@dataclass
class AgentThresholds:
    """Agent-specific thresholds and weights."""
    min_data_score: float = 0.60
    min_llm_confidence: float = 0.65
    graceful_degradation: bool = True
    field_weights: Dict[str, float] = field(default_factory=dict)
    empty_list_penalty: float = 0.1
    # [BOSS-8] Ajan başına duvar saati sınırı (saniye). Görev sınırı 300s iken
    # tek bir ajanın LLM zinciri (3 model x 3 taşıma x 45s = 405s) bütçenin
    # tamamını yiyebiliyordu; görev iptal edilip BAŞTAN koşuyordu (3x maliyet).
    timeout_seconds: float = 0.0  # 0 = sınır yok (eski davranış)

@dataclass
class DecisionConfig:
    """Global decision configuration."""
    version: str
    global_defaults: Dict[str, Any]
    critical_agents: List[str]
    agents: Dict[str, AgentThresholds]

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, config_path: str = "config/decision_config.yaml") -> "DecisionConfig":
        """Load decision config from YAML."""
        # Check relative to current working directory or absolute
        path = Path(config_path)
        if not path.is_absolute():
            # Try to resolve relative to project root
            # Assume this file is in agent_core, so project root is its parent
            project_root = Path(__file__).parent.parent
            path = project_root / config_path
            
        if not path.exists():
            # Try just relative path from pwd as fallback
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"Decision config not found: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
            
        pipeline_cfg = raw.get("pipeline", {})
        default_cfg = pipeline_cfg.get("default", {})
        critical_agents = pipeline_cfg.get("critical_agents", [])
        
        agents_dict = raw.get("agents", {})
        agents = {}
        for name, config_data in agents_dict.items():
            agents[name] = AgentThresholds(
                min_data_score=config_data.get("min_data_score", default_cfg.get("min_data_score", 0.60)),
                min_llm_confidence=config_data.get("min_llm_confidence", default_cfg.get("min_llm_confidence", 0.65)),
                graceful_degradation=config_data.get("graceful_degradation", default_cfg.get("graceful_degradation", True)),
                field_weights=config_data.get("field_weights", {}),
                empty_list_penalty=config_data.get("empty_list_penalty", 0.1),
                timeout_seconds=float(
                    config_data.get(
                        "timeout_seconds", default_cfg.get("agent_timeout_seconds", 0.0)
                    ) or 0.0
                ),
            )
        
        return cls(
            version=raw.get("version", "1.0"),
            global_defaults=default_cfg,
            critical_agents=critical_agents,
            agents=agents
        )

    def get_agent_config(self, agent_name: str) -> AgentThresholds:
        """Get config for specific agent, fallback to defaults."""
        if agent_name in self.agents:
            return self.agents[agent_name]
        
        # Return default config
        return AgentThresholds(
            min_data_score=self.global_defaults.get("min_data_score", 0.60),
            min_llm_confidence=self.global_defaults.get("min_llm_confidence", 0.65),
            graceful_degradation=self.global_defaults.get("graceful_degradation", True),
            timeout_seconds=float(self.global_defaults.get("agent_timeout_seconds", 0.0) or 0.0),
        )
