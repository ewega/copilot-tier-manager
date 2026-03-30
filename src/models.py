"""Shared data models for copilot-tier-manager."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserChange:
    username: str
    entra_user_id: str
    pru_usage: float
    old_tier: Optional[str]
    new_tier: str
    action: str  # "moved_up", "moved_down", "unchanged", "new"


@dataclass
class SyncResult:
    total_users: int = 0
    moved_up: list[UserChange] = field(default_factory=list)
    moved_down: list[UserChange] = field(default_factory=list)
    unchanged: int = 0
    new_users: list[UserChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
