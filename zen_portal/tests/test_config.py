"""Tests for the 3-tier feature configuration system."""

import json
import pytest
from pathlib import Path

from zen_portal.services.config import (
    ConfigManager,
    Config,
    PortalState,
    FeatureSettings,
    ClaudeModel,
    ExitBehavior,
)


class TestFeatureSettings:
    """Tests for FeatureSettings."""

    def test_to_dict_empty(self):
        """Empty settings produce empty dict."""
        settings = FeatureSettings()
        assert settings.to_dict() == {}

    def test_to_dict_with_values(self, tmp_path: Path):
        """Settings serialize correctly."""
        settings = FeatureSettings(
            working_dir=tmp_path,
            model=ClaudeModel.OPUS,
            session_prefix="test",
        )
        result = settings.to_dict()
        assert result["working_dir"] == str(tmp_path)
        assert result["model"] == "opus"
        assert result["session_prefix"] == "test"

    def test_from_dict_empty(self):
        """Empty dict produces empty settings."""
        settings = FeatureSettings.from_dict({})
        assert settings.working_dir is None
        assert settings.model is None
        assert settings.session_prefix is None

    def test_from_dict_with_values(self, tmp_path: Path):
        """Settings deserialize correctly."""
        data = {
            "working_dir": str(tmp_path),
            "model": "sonnet",
            "session_prefix": "zen",
        }
        settings = FeatureSettings.from_dict(data)
        assert settings.working_dir == tmp_path
        assert settings.model == ClaudeModel.SONNET
        assert settings.session_prefix == "zen"

    def test_merge_with_override(self, tmp_path: Path):
        """Override values take precedence."""
        base = FeatureSettings(
            working_dir=tmp_path / "base",
            model=ClaudeModel.SONNET,
            session_prefix="base",
        )
        override = FeatureSettings(
            model=ClaudeModel.OPUS,
        )

        merged = base.merge_with(override)

        # Override model wins
        assert merged.model == ClaudeModel.OPUS
        # Base values preserved when not overridden
        assert merged.working_dir == tmp_path / "base"
        assert merged.session_prefix == "base"

    def test_merge_with_empty_override(self, tmp_path: Path):
        """Empty override preserves all base values."""
        base = FeatureSettings(
            working_dir=tmp_path,
            model=ClaudeModel.SONNET,
            session_prefix="test",
        )
        override = FeatureSettings()

        merged = base.merge_with(override)

        assert merged.working_dir == tmp_path
        assert merged.model == ClaudeModel.SONNET
        assert merged.session_prefix == "test"

    def test_enabled_session_types_to_dict(self):
        """Session types serialize correctly."""
        settings = FeatureSettings(enabled_session_types=["claude", "shell"])
        result = settings.to_dict()
        assert result["enabled_session_types"] == ["claude", "shell"]

    def test_enabled_session_types_from_dict(self):
        """Session types deserialize correctly."""
        data = {"enabled_session_types": ["claude", "codex"]}
        settings = FeatureSettings.from_dict(data)
        assert settings.enabled_session_types == ["claude", "codex"]

    def test_enabled_session_types_none_means_all(self):
        """None means all types enabled (default behavior)."""
        settings = FeatureSettings()
        assert settings.enabled_session_types is None
        assert "enabled_session_types" not in settings.to_dict()

    def test_enabled_session_types_merge(self):
        """Session types merge correctly."""
        base = FeatureSettings(enabled_session_types=["claude", "shell"])
        override = FeatureSettings(enabled_session_types=["claude"])
        merged = base.merge_with(override)
        assert merged.enabled_session_types == ["claude"]


class TestConfigManager:
    """Tests for ConfigManager 3-tier system."""

    def test_config_defaults(self, tmp_path: Path):
        """Fresh config has expected defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        assert manager.config.exit_behavior == ExitBehavior.ASK
        assert manager.config.features.working_dir is None

    def test_save_and_load_config(self, tmp_path: Path):
        """Config persists across manager instances."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(
            exit_behavior=ExitBehavior.KILL_ALL,
            features=FeatureSettings(
                working_dir=tmp_path,
                model=ClaudeModel.HAIKU,
            ),
        )
        manager.save_config(config)

        # New manager should load persisted config
        manager2 = ConfigManager(config_dir=config_dir)
        assert manager2.config.exit_behavior == ExitBehavior.KILL_ALL
        assert manager2.config.features.working_dir == tmp_path
        assert manager2.config.features.model == ClaudeModel.HAIKU

    def test_portal_defaults(self, tmp_path: Path):
        """Fresh portal state has expected defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        assert manager.portal.features.working_dir is None
        assert manager.portal.description == ""

    def test_save_and_load_portal(self, tmp_path: Path):
        """Portal state persists across manager instances."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        state = PortalState(
            features=FeatureSettings(working_dir=tmp_path / "project"),
            description="Working on zen-portal",
        )
        manager.save_portal(state)

        # New manager should load persisted portal state
        manager2 = ConfigManager(config_dir=config_dir)
        assert manager2.portal.features.working_dir == tmp_path / "project"
        assert manager2.portal.description == "Working on zen-portal"

    def test_clear_portal(self, tmp_path: Path):
        """Clearing portal state removes file and resets."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        state = PortalState(
            features=FeatureSettings(working_dir=tmp_path),
        )
        manager.save_portal(state)
        assert manager.portal.features.working_dir == tmp_path

        manager.clear_portal()

        assert manager.portal.features.working_dir is None
        assert not (config_dir / "portal.json").exists()

    def test_resolve_features_defaults(self, tmp_path: Path):
        """Resolve fills in system defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        resolved = manager.resolve_features()

        # System defaults applied
        assert resolved.working_dir is not None  # Defaults to cwd
        assert resolved.session_prefix == "zen"
        # Model can remain None (Claude's default)
        assert resolved.model is None

    def test_resolve_features_config_level(self, tmp_path: Path):
        """Config-level settings are applied."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(
            features=FeatureSettings(
                working_dir=tmp_path / "config-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        resolved = manager.resolve_features()

        assert resolved.working_dir == tmp_path / "config-level"
        assert resolved.model == ClaudeModel.SONNET

    def test_resolve_features_portal_overrides_config(self, tmp_path: Path):
        """Portal-level settings override config."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        # Set config-level
        config = Config(
            features=FeatureSettings(
                working_dir=tmp_path / "config-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        # Set portal-level (override model only)
        portal = PortalState(
            features=FeatureSettings(model=ClaudeModel.OPUS)
        )
        manager.save_portal(portal)

        resolved = manager.resolve_features()

        # Config working_dir preserved, model overridden
        assert resolved.working_dir == tmp_path / "config-level"
        assert resolved.model == ClaudeModel.OPUS

    def test_resolve_features_session_overrides_all(self, tmp_path: Path):
        """Session-level settings override everything."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        # Set config-level
        config = Config(
            features=FeatureSettings(
                working_dir=tmp_path / "config-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        # Set portal-level
        portal = PortalState(
            features=FeatureSettings(model=ClaudeModel.OPUS)
        )
        manager.save_portal(portal)

        # Session-level override
        session_override = FeatureSettings(
            working_dir=tmp_path / "session-level",
            model=ClaudeModel.HAIKU,
        )

        resolved = manager.resolve_features(session_override)

        # Session overrides win
        assert resolved.working_dir == tmp_path / "session-level"
        assert resolved.model == ClaudeModel.HAIKU

    def test_resolve_features_partial_session_override(self, tmp_path: Path):
        """Session can override just some settings."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(
            features=FeatureSettings(
                working_dir=tmp_path / "config-level",
                model=ClaudeModel.SONNET,
                session_prefix="custom",
            )
        )
        manager.save_config(config)

        # Session only overrides working_dir
        session_override = FeatureSettings(
            working_dir=tmp_path / "session-level",
        )

        resolved = manager.resolve_features(session_override)

        # Session working_dir wins
        assert resolved.working_dir == tmp_path / "session-level"
        # Config values preserved
        assert resolved.model == ClaudeModel.SONNET
        assert resolved.session_prefix == "custom"


class TestConfigManagerBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_save_calls_save_config(self, tmp_path: Path):
        """Deprecated save() method still works."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(exit_behavior=ExitBehavior.KEEP_ALL)
        manager.save(config)  # Deprecated

        # Should work
        manager2 = ConfigManager(config_dir=config_dir)
        assert manager2.config.exit_behavior == ExitBehavior.KEEP_ALL
