"""Unit tests for the tier classification engine."""
import pytest
import tempfile
import os
from pathlib import Path

from src.tier_engine import TierEngine, TierConfig


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary tiers.yaml for testing."""
    config = """
tiers:
  basic-adopter:
    min_pru: 0
    max_pru: 299
    entra_group_id: "group-basic"
    copilot_plan: "business"
  growing-user:
    min_pru: 300
    max_pru: 699
    entra_group_id: "group-growing"
    copilot_plan: "business"
    overage_enabled: true
  power-user:
    min_pru: 700
    max_pru: 999
    entra_group_id: "group-power"
    copilot_plan: "enterprise"
  advanced-user:
    min_pru: 1000
    max_pru: null
    entra_group_id: "group-advanced"
    copilot_plan: "enterprise"
    overage_enabled: true
"""
    config_path = tmp_path / "tiers.yaml"
    config_path.write_text(config)
    return str(config_path)


@pytest.fixture
def engine(config_file):
    return TierEngine(config_path=config_file)


class TestTierClassification:
    """Test tier threshold classification logic."""

    def test_zero_usage_is_basic(self, engine):
        assert engine.classify(0).name == "basic-adopter"

    def test_below_300_is_basic(self, engine):
        assert engine.classify(150).name == "basic-adopter"

    def test_at_299_is_basic(self, engine):
        assert engine.classify(299).name == "basic-adopter"

    def test_at_300_is_growing(self, engine):
        assert engine.classify(300).name == "growing-user"

    def test_mid_growing_range(self, engine):
        assert engine.classify(500).name == "growing-user"

    def test_at_699_is_growing(self, engine):
        assert engine.classify(699).name == "growing-user"

    def test_at_700_is_power(self, engine):
        assert engine.classify(700).name == "power-user"

    def test_mid_power_range(self, engine):
        assert engine.classify(850).name == "power-user"

    def test_at_999_is_power(self, engine):
        assert engine.classify(999).name == "power-user"

    def test_at_1000_is_advanced(self, engine):
        assert engine.classify(1000).name == "advanced-user"

    def test_high_usage_is_advanced(self, engine):
        assert engine.classify(5000).name == "advanced-user"

    def test_float_usage_truncated(self, engine):
        """Float usage should be truncated to int for classification."""
        assert engine.classify(299.9).name == "basic-adopter"
        assert engine.classify(300.1).name == "growing-user"


class TestTierBoundaryEdges:
    """Test exact boundary values."""

    @pytest.mark.parametrize("pru,expected_tier", [
        (0, "basic-adopter"),
        (299, "basic-adopter"),
        (300, "growing-user"),
        (699, "growing-user"),
        (700, "power-user"),
        (999, "power-user"),
        (1000, "advanced-user"),
    ])
    def test_boundaries(self, engine, pru, expected_tier):
        assert engine.classify(pru).name == expected_tier


class TestTierMovement:
    """Test tier change detection scenarios."""

    def test_no_movement_same_tier(self, engine):
        """User at 150 PRU classified same as user at 200 PRU."""
        assert engine.classify(150).name == engine.classify(200).name

    def test_movement_up(self, engine):
        """User going from 250 to 350 moves from basic to growing."""
        old = engine.classify(250)
        new = engine.classify(350)
        assert old.name == "basic-adopter"
        assert new.name == "growing-user"
        assert new.min_pru > old.min_pru

    def test_movement_down(self, engine):
        """User going from 800 to 400 moves from power to growing."""
        old = engine.classify(800)
        new = engine.classify(400)
        assert old.name == "power-user"
        assert new.name == "growing-user"
        assert new.min_pru < old.min_pru


class TestConfigLoading:
    """Test YAML config loading."""

    def test_loads_4_tiers(self, engine):
        assert len(engine.tiers) == 4

    def test_tiers_sorted_by_min_pru(self, engine):
        for i in range(len(engine.tiers) - 1):
            assert engine.tiers[i].min_pru <= engine.tiers[i + 1].min_pru

    def test_lookup_by_name(self, engine):
        tier = engine.get_tier_by_name("power-user")
        assert tier is not None
        assert tier.copilot_plan == "enterprise"

    def test_lookup_by_group_id(self, engine):
        tier = engine.get_tier_by_group_id("group-advanced")
        assert tier is not None
        assert tier.name == "advanced-user"

    def test_lookup_nonexistent_returns_none(self, engine):
        assert engine.get_tier_by_name("nonexistent") is None

    def test_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            TierEngine(config_path="/nonexistent/path.yaml")

    def test_duplicate_group_ids_raises(self, tmp_path):
        """Duplicate group IDs in config should raise ValueError."""
        config = """
tiers:
  tier-a:
    min_pru: 0
    max_pru: 299
    entra_group_id: "same-group-id"
    copilot_plan: "business"
  tier-b:
    min_pru: 300
    max_pru: 699
    entra_group_id: "same-group-id"
    copilot_plan: "business"
"""
        config_path = tmp_path / "bad_tiers.yaml"
        config_path.write_text(config)
        with pytest.raises(ValueError, match="Duplicate entra_group_id"):
            TierEngine(config_path=str(config_path))

    def test_overage_flag(self, engine):
        growing = engine.get_tier_by_name("growing-user")
        basic = engine.get_tier_by_name("basic-adopter")
        assert growing.overage_enabled is True
        assert basic.overage_enabled is False
