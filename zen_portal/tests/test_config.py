"""Tests for the 3-tier feature configuration system."""

import json
import pytest
from pathlib import Path

from zen_portal.services.config import (
    ConfigManager,
    Config,
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
    """Tests for ConfigManager unified config system."""

    def test_config_defaults(self, tmp_path: Path):
        """Fresh config has expected defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        assert manager.config.exit_behavior == ExitBehavior.ASK
        assert manager.config.defaults.working_dir is None
        assert manager.config.project.working_dir is None

    def test_save_and_load_config(self, tmp_path: Path):
        """Config persists across manager instances."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(
            exit_behavior=ExitBehavior.KILL_ALL,
            defaults=FeatureSettings(
                working_dir=tmp_path,
                model=ClaudeModel.HAIKU,
            ),
        )
        manager.save_config(config)

        # New manager should load persisted config
        manager2 = ConfigManager(config_dir=config_dir)
        assert manager2.config.exit_behavior == ExitBehavior.KILL_ALL
        assert manager2.config.defaults.working_dir == tmp_path
        assert manager2.config.defaults.model == ClaudeModel.HAIKU

    def test_project_defaults(self, tmp_path: Path):
        """Fresh project settings have expected defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        assert manager.config.project.working_dir is None
        assert manager.config.project_description == ""

    def test_save_and_load_project(self, tmp_path: Path):
        """Project settings persist across manager instances."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        manager.update_project_features(
            FeatureSettings(working_dir=tmp_path / "project"),
            description="Working on zen-portal",
        )

        # New manager should load persisted project settings
        manager2 = ConfigManager(config_dir=config_dir)
        assert manager2.config.project.working_dir == tmp_path / "project"
        assert manager2.config.project_description == "Working on zen-portal"

    def test_clear_project(self, tmp_path: Path):
        """Clearing project settings resets them."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        manager.update_project_features(FeatureSettings(working_dir=tmp_path))
        assert manager.config.project.working_dir == tmp_path

        manager.clear_project()

        assert manager.config.project.working_dir is None

    def test_resolve_features_defaults(self, tmp_path: Path):
        """Resolve fills in system defaults."""
        manager = ConfigManager(config_dir=tmp_path / "config")

        resolved = manager.resolve_features()

        # System defaults applied
        assert resolved.working_dir is not None  # Defaults to cwd
        assert resolved.session_prefix == "zen"
        # Model can remain None (Claude's default)
        assert resolved.model is None

    def test_resolve_features_defaults_level(self, tmp_path: Path):
        """Default-level settings are applied."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        config = Config(
            defaults=FeatureSettings(
                working_dir=tmp_path / "defaults-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        resolved = manager.resolve_features()

        assert resolved.working_dir == tmp_path / "defaults-level"
        assert resolved.model == ClaudeModel.SONNET

    def test_resolve_features_project_overrides_defaults(self, tmp_path: Path):
        """Project-level settings override defaults."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        # Set defaults
        config = Config(
            defaults=FeatureSettings(
                working_dir=tmp_path / "defaults-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        # Set project-level (override model only)
        manager.update_project_features(
            FeatureSettings(model=ClaudeModel.OPUS)
        )

        resolved = manager.resolve_features()

        # Defaults working_dir preserved, model overridden
        assert resolved.working_dir == tmp_path / "defaults-level"
        assert resolved.model == ClaudeModel.OPUS

    def test_resolve_features_session_overrides_all(self, tmp_path: Path):
        """Session-level settings override everything."""
        config_dir = tmp_path / "config"
        manager = ConfigManager(config_dir=config_dir)

        # Set defaults
        config = Config(
            defaults=FeatureSettings(
                working_dir=tmp_path / "defaults-level",
                model=ClaudeModel.SONNET,
            )
        )
        manager.save_config(config)

        # Set project-level
        manager.update_project_features(
            FeatureSettings(model=ClaudeModel.OPUS)
        )

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
            defaults=FeatureSettings(
                working_dir=tmp_path / "defaults-level",
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
        # Defaults values preserved
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
