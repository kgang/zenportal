"""Configuration management for Zen Portal.

Single-file configuration system with hierarchical keys:
- ~/.config/zen-portal/config.json contains both defaults and current project settings
- Session-level overrides are applied at runtime (stored in Session dataclass)

Resolution order: session > project > defaults

Security notes:
- Config files may contain API keys; saved with mode 0600
- Prefer environment variables for sensitive credentials
- Values are validated before use in shell commands (see SessionCommandBuilder)
"""

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


def _secure_write_json(path: Path, data: dict) -> None:
    """Write JSON to file with restricted permissions (0600).

    This ensures config files containing potential secrets
    are only readable by the owner.
    """
    content = json.dumps(data, indent=2)
    # Write to temp file first, then rename for atomicity
    temp_path = path.with_suffix(".tmp")
    try:
        # Create with restricted permissions from the start
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)
        # Atomic rename
        temp_path.rename(path)
    except Exception:
        # Fallback: write normally then chmod
        path.write_text(content)
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except OSError:
            pass  # Best effort on systems that don't support chmod


class ExitBehavior(Enum):
    """What to do with tmux sessions on exit."""

    ASK = "ask"  # Ask every time
    KILL_ALL = "kill_all"  # Kill all zen sessions
    KILL_DEAD = "kill_dead"  # Kill only dead panes
    KEEP_ALL = "keep_all"  # Keep everything running


class ClaudeModel(Enum):
    """Claude model selection."""

    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"


# All available session types for configuration
ALL_SESSION_TYPES = ["ai", "shell"]

# All available AI providers
ALL_AI_PROVIDERS = ["claude", "codex", "gemini", "openrouter"]


@dataclass
class ProxySettings:
    """Settings for routing Claude sessions through y-router (OpenRouter proxy).

    Routes Claude Code through y-router for pay-per-token via OpenRouter API.

    Security notes:
    - Credentials stored in plain text; prefer environment variables
    - Config files saved with 0600 permissions
    - Values validated in SessionCommandBuilder before shell use
    """

    enabled: bool = False
    # Proxy URL (defaults to http://localhost:8787)
    base_url: str = ""
    # OpenRouter API key (or OPENROUTER_API_KEY env var)
    api_key: str = ""
    # Model override (e.g., "anthropic/claude-sonnet-4")
    default_model: str = ""

    @property
    def effective_base_url(self) -> str:
        """Get base URL with default."""
        return self.base_url or "http://localhost:8787"

    def to_dict(self, redact_secrets: bool = False) -> dict:
        """Serialize to dict.

        Args:
            redact_secrets: If True, redact sensitive fields
        """
        result: dict = {"enabled": self.enabled}
        if self.base_url:
            result["base_url"] = self.base_url
        if self.api_key:
            if redact_secrets:
                result["api_key"] = f"***{self.api_key[-4:]}" if len(self.api_key) >= 4 else "***"
            else:
                result["api_key"] = self.api_key
        if self.default_model:
            result["default_model"] = self.default_model
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ProxySettings":
        return cls(
            enabled=data.get("enabled", False),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            default_model=data.get("default_model", ""),
        )

    def merge_with(self, override: "ProxySettings") -> "ProxySettings":
        """Return new settings with override values taking precedence."""
        return ProxySettings(
            enabled=override.enabled if override.enabled else self.enabled,
            base_url=override.base_url if override.base_url else self.base_url,
            api_key=override.api_key if override.api_key else self.api_key,
            default_model=override.default_model if override.default_model else self.default_model,
        )

    @property
    def has_credentials(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key or os.environ.get("OPENROUTER_API_KEY"))


# Backwards compatibility alias
OpenRouterProxySettings = ProxySettings


class ZenAIProvider(Enum):
    """AI provider for Zen AI queries."""

    CLAUDE = "claude"  # Use claude -p subprocess
    OPENROUTER = "openrouter"  # Direct OpenRouter API


class ZenAIModel(Enum):
    """Quick model selection for Zen AI."""

    HAIKU = "haiku"  # Fast, cheap - good for whispers
    SONNET = "sonnet"  # Balanced - good for prompts
    OPUS = "opus"  # Deep - for complex questions


@dataclass
class ZenAIConfig:
    """Configuration for Zen AI feature.

    Provides lightweight AI queries without creating tmux sessions.
    """

    enabled: bool = False
    model: ZenAIModel = ZenAIModel.HAIKU
    provider: ZenAIProvider = ZenAIProvider.CLAUDE
    # Custom OpenRouter model (overrides model enum)
    openrouter_model: str = ""

    def to_dict(self) -> dict:
        result: dict = {"enabled": self.enabled}
        if self.model != ZenAIModel.HAIKU:
            result["model"] = self.model.value
        if self.provider != ZenAIProvider.CLAUDE:
            result["provider"] = self.provider.value
        if self.openrouter_model:
            result["openrouter_model"] = self.openrouter_model
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ZenAIConfig":
        model = ZenAIModel.HAIKU
        if data.get("model"):
            try:
                model = ZenAIModel(data["model"])
            except ValueError:
                pass

        provider = ZenAIProvider.CLAUDE
        if data.get("provider"):
            try:
                provider = ZenAIProvider(data["provider"])
            except ValueError:
                pass

        return cls(
            enabled=data.get("enabled", False),
            model=model,
            provider=provider,
            openrouter_model=data.get("openrouter_model", ""),
        )

    @property
    def effective_model(self) -> str:
        """Get the model to use for OpenRouter queries."""
        if self.openrouter_model:
            return self.openrouter_model
        # Default OpenRouter model IDs
        model_map = {
            ZenAIModel.HAIKU: "anthropic/claude-3-haiku",
            ZenAIModel.SONNET: "anthropic/claude-sonnet-4-20250514",
            ZenAIModel.OPUS: "anthropic/claude-opus-4-20250514",
        }
        return model_map.get(self.model, model_map[ZenAIModel.HAIKU])


@dataclass
class WorktreeSettings:
    """Settings for git worktree integration.

    When enabled, each session gets its own isolated worktree,
    allowing parallel work on different branches.
    """

    enabled: bool = False
    base_dir: Path | None = None  # Default: ~/.zen-portal/worktrees
    source_repo: Path | None = None  # Default: resolved working_dir
    auto_cleanup: bool = True  # Remove worktree when session is pruned
    default_from_branch: str = "main"  # Base branch for new worktrees
    env_files: list[str] | None = None  # Relative paths to symlink (e.g., [".env", ".env.secrets"])

    def to_dict(self) -> dict:
        result: dict = {"enabled": self.enabled}
        if self.base_dir is not None:
            result["base_dir"] = str(self.base_dir)
        if self.source_repo is not None:
            result["source_repo"] = str(self.source_repo)
        result["auto_cleanup"] = self.auto_cleanup
        result["default_from_branch"] = self.default_from_branch
        if self.env_files is not None:
            result["env_files"] = self.env_files
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "WorktreeSettings":
        base_dir = Path(data["base_dir"]) if data.get("base_dir") else None
        source_repo = Path(data["source_repo"]) if data.get("source_repo") else None
        return cls(
            enabled=data.get("enabled", False),
            base_dir=base_dir,
            source_repo=source_repo,
            auto_cleanup=data.get("auto_cleanup", True),
            default_from_branch=data.get("default_from_branch", "main"),
            env_files=data.get("env_files"),
        )

    def merge_with(self, override: "WorktreeSettings") -> "WorktreeSettings":
        """Return new settings with override values taking precedence.

        Note: enabled=False in override is meaningful, so we check if override
        has any non-default values set.
        """
        return WorktreeSettings(
            enabled=override.enabled if override.enabled else self.enabled,
            base_dir=override.base_dir if override.base_dir is not None else self.base_dir,
            source_repo=override.source_repo if override.source_repo is not None else self.source_repo,
            auto_cleanup=override.auto_cleanup,
            default_from_branch=override.default_from_branch if override.default_from_branch != "main" else self.default_from_branch,
            env_files=override.env_files if override.env_files is not None else self.env_files,
        )


@dataclass
class FeatureSettings:
    """Settings that can be overridden at any tier.

    These are the "features" that flow through config -> portal -> session.
    """

    working_dir: Path | None = None  # Where Claude Code starts
    model: ClaudeModel | None = None  # Claude model to use
    session_prefix: str | None = None  # Prefix for tmux sessions
    worktree: WorktreeSettings | None = None  # Git worktree settings
    # Session types to show in the new session modal
    # None means all types enabled (default), empty list means none
    enabled_session_types: list[str] | None = None
    # OpenRouter default model for orchat sessions (e.g., "anthropic/claude-3.5-sonnet")
    openrouter_model: str | None = None
    # Proxy settings for routing Claude sessions through y-router or CLIProxyAPI
    openrouter_proxy: ProxySettings | None = None
    # Zen AI settings for inline AI queries
    zen_ai: ZenAIConfig | None = None

    def to_dict(self) -> dict:
        result = {}
        if self.working_dir is not None:
            result["working_dir"] = str(self.working_dir)
        if self.model is not None:
            result["model"] = self.model.value
        if self.session_prefix is not None:
            result["session_prefix"] = self.session_prefix
        if self.worktree is not None:
            result["worktree"] = self.worktree.to_dict()
        if self.enabled_session_types is not None:
            result["enabled_session_types"] = self.enabled_session_types
        if self.openrouter_model is not None:
            result["openrouter_model"] = self.openrouter_model
        if self.openrouter_proxy is not None:
            result["openrouter_proxy"] = self.openrouter_proxy.to_dict()
        if self.zen_ai is not None:
            result["zen_ai"] = self.zen_ai.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSettings":
        working_dir = Path(data["working_dir"]) if data.get("working_dir") else None
        model = ClaudeModel(data["model"]) if data.get("model") else None
        worktree = WorktreeSettings.from_dict(data["worktree"]) if data.get("worktree") else None
        enabled_types = data.get("enabled_session_types")
        openrouter_proxy = ProxySettings.from_dict(data["openrouter_proxy"]) if data.get("openrouter_proxy") else None
        zen_ai = ZenAIConfig.from_dict(data["zen_ai"]) if data.get("zen_ai") else None
        return cls(
            working_dir=working_dir,
            model=model,
            session_prefix=data.get("session_prefix"),
            worktree=worktree,
            enabled_session_types=enabled_types,
            openrouter_model=data.get("openrouter_model"),
            openrouter_proxy=openrouter_proxy,
            zen_ai=zen_ai,
        )

    def merge_with(self, override: "FeatureSettings") -> "FeatureSettings":
        """Return new settings with override values taking precedence."""
        # Merge worktree settings if both exist
        merged_worktree = self.worktree
        if override.worktree is not None:
            if self.worktree is not None:
                merged_worktree = self.worktree.merge_with(override.worktree)
            else:
                merged_worktree = override.worktree

        # Merge openrouter_proxy settings if both exist
        merged_openrouter_proxy = self.openrouter_proxy
        if override.openrouter_proxy is not None:
            if self.openrouter_proxy is not None:
                merged_openrouter_proxy = self.openrouter_proxy.merge_with(override.openrouter_proxy)
            else:
                merged_openrouter_proxy = override.openrouter_proxy

        # Zen AI: override takes precedence if set
        merged_zen_ai = override.zen_ai if override.zen_ai is not None else self.zen_ai

        return FeatureSettings(
            working_dir=override.working_dir if override.working_dir is not None else self.working_dir,
            model=override.model if override.model is not None else self.model,
            session_prefix=override.session_prefix if override.session_prefix is not None else self.session_prefix,
            worktree=merged_worktree,
            enabled_session_types=override.enabled_session_types if override.enabled_session_types is not None else self.enabled_session_types,
            openrouter_model=override.openrouter_model if override.openrouter_model is not None else self.openrouter_model,
            openrouter_proxy=merged_openrouter_proxy,
            zen_ai=merged_zen_ai,
        )


@dataclass
class Config:
    """Unified Zen Portal configuration.

    Stored in ~/.config/zen-portal/config.json
    Contains both global defaults and current project settings.
    """

    exit_behavior: ExitBehavior = ExitBehavior.ASK
    defaults: FeatureSettings = field(default_factory=FeatureSettings)
    project: FeatureSettings = field(default_factory=FeatureSettings)
    project_description: str = ""  # Optional description of current project

    def to_dict(self) -> dict:
        result = {
            "exit_behavior": self.exit_behavior.value,
            "defaults": self.defaults.to_dict(),
        }
        # Only save project settings if they have values
        project_dict = self.project.to_dict()
        if project_dict:
            result["project"] = project_dict
        if self.project_description:
            result["project_description"] = self.project_description
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        defaults = FeatureSettings.from_dict(data.get("defaults", {}) or data.get("features", {}))
        project = FeatureSettings.from_dict(data.get("project", {}))
        return cls(
            exit_behavior=ExitBehavior(data.get("exit_behavior", "ask")),
            defaults=defaults,
            project=project,
            project_description=data.get("project_description", ""),
        )


class ConfigManager:
    """Manages unified configuration with defaults and project settings."""

    DEFAULT_SESSION_PREFIX = "zen"

    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "zen-portal"
        self._config_dir = config_dir
        self._config_file = config_dir / "config.json"
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> Config:
        """Load config from disk."""
        if self._config_file.exists():
            try:
                data = json.loads(self._config_file.read_text())
                return Config.from_dict(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return Config()

    def save_config(self, config: Config) -> None:
        """Save config to disk with secure permissions."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        _secure_write_json(self._config_file, config.to_dict())
        self._config = config

    def update_exit_behavior(self, behavior: ExitBehavior) -> None:
        """Update exit behavior setting."""
        config = self.config
        config.exit_behavior = behavior
        self.save_config(config)

    def update_project_features(self, features: FeatureSettings, description: str = "") -> None:
        """Update project-level feature overrides."""
        config = self.config
        config.project = features
        if description:
            config.project_description = description
        self.save_config(config)

    def clear_project(self) -> None:
        """Clear project settings (e.g., when switching projects)."""
        config = self.config
        config.project = FeatureSettings()
        config.project_description = ""
        self.save_config(config)

    def resolve_features(self, session_override: FeatureSettings | None = None) -> FeatureSettings:
        """Resolve features through all tiers.

        Resolution order: session > project > defaults

        Args:
            session_override: Optional session-level overrides

        Returns:
            Fully resolved FeatureSettings with defaults filled in
        """
        # Start with defaults
        resolved = self.config.defaults

        # Apply project overrides
        resolved = resolved.merge_with(self.config.project)

        # Apply session overrides
        if session_override:
            resolved = resolved.merge_with(session_override)

        # Fill in system defaults for any remaining None values
        if resolved.working_dir is None:
            resolved.working_dir = Path.cwd()
        if resolved.session_prefix is None:
            resolved.session_prefix = self.DEFAULT_SESSION_PREFIX
        # model can remain None (use Claude's default)

        return resolved

    def get_proxy_settings(self) -> ProxySettings | None:
        """Get resolved proxy settings from config.

        Returns proxy settings if configured, None otherwise.
        """
        features = self.resolve_features()
        return features.openrouter_proxy

    # --- Backward compatibility ---

    def save(self, config: Config) -> None:
        """Deprecated: use save_config instead."""
        self.save_config(config)

    @property
    def portal(self):
        """Backward compatibility: portal is now the project section."""
        from dataclasses import dataclass, field

        @dataclass
        class _PortalCompat:
            features: FeatureSettings = field(default_factory=FeatureSettings)
            description: str = ""

        config = self.config
        return _PortalCompat(features=config.project, description=config.project_description)

    def save_portal(self, state) -> None:
        """Backward compatibility: save portal state as project settings."""
        self.update_project_features(state.features, state.description)

    def clear_portal(self) -> None:
        """Backward compatibility: clear portal is now clear project."""
        self.clear_project()

    def update_portal_features(self, features: FeatureSettings, description: str = "") -> None:
        """Backward compatibility: update portal features is now update project features."""
        self.update_project_features(features, description)
