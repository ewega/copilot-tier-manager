"""Tier classification engine — config-driven PRU thresholds."""
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class TierConfig:
    name: str
    min_pru: int
    max_pru: Optional[int]  # None = unlimited
    entra_group_id: str
    copilot_plan: str
    overage_enabled: bool = False
    description: str = ""


class TierEngine:
    """Classifies users into tiers based on PRU consumption."""

    def __init__(self, config_path: str = "config/tiers.yaml"):
        self.tiers = self._load_config(config_path)

    def _load_config(self, config_path: str) -> list[TierConfig]:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        tiers = []
        for name, cfg in data.get("tiers", {}).items():
            tiers.append(TierConfig(
                name=name,
                min_pru=cfg.get("min_pru", 0),
                max_pru=cfg.get("max_pru"),
                entra_group_id=cfg.get("entra_group_id", ""),
                copilot_plan=cfg.get("copilot_plan", "business"),
                overage_enabled=cfg.get("overage_enabled", False),
                description=cfg.get("description", ""),
            ))
        # Validate unique group IDs
        group_ids = [t.entra_group_id for t in tiers if t.entra_group_id]
        duplicates = [gid for gid in group_ids if group_ids.count(gid) > 1]
        if duplicates:
            raise ValueError(
                f"Duplicate entra_group_id values in config: {set(duplicates)}. "
                "Each tier must have a unique Entra ID group."
            )
        # Sort by min_pru ascending
        tiers.sort(key=lambda t: t.min_pru)
        return tiers

    def classify(self, pru_usage: float) -> TierConfig:
        """Classify a user into a tier based on their PRU usage."""
        pru = int(pru_usage)
        for tier in reversed(self.tiers):
            if pru >= tier.min_pru:
                return tier
        return self.tiers[0]  # Default to lowest tier

    def get_tier_by_name(self, name: str) -> Optional[TierConfig]:
        """Look up a tier by name."""
        for tier in self.tiers:
            if tier.name == name:
                return tier
        return None

    def get_tier_by_group_id(self, group_id: str) -> Optional[TierConfig]:
        """Look up a tier by its Entra ID group ID."""
        for tier in self.tiers:
            if tier.entra_group_id == group_id:
                return tier
        return None
