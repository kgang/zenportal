"""Configuration management for Zen Portal.

3-Tier Feature System:
1. Config Level (~/.config/zen-portal/config.json) - Global defaults
2. Portal Level (~/.config/zen-portal/portal.json) - Current zen-portal state, survives restarts
3. Session Level (per-session at creation) - Stored in Session dataclass

Each level can override the previous. Resolution order: session > portal > config > defaults

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
ALL_SESSION_TYPES = ["claude", "codex", "gemini", "shell", "openrouter"]


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
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSettings":
        working_dir = Path(data["working_dir"]) if data.get("working_dir") else None
        model = ClaudeModel(data["model"]) if data.get("model") else None
        worktree = WorktreeSettings.from_dict(data["worktree"]) if data.get("worktree") else None
        enabled_types = data.get("enabled_session_types")
        openrouter_proxy = ProxySettings.from_dict(data["openrouter_proxy"]) if data.get("openrouter_proxy") else None
        return cls(
            working_dir=working_dir,
            model=model,
            session_prefix=data.get("session_prefix"),
            worktree=worktree,
            enabled_session_types=enabled_types,
            openrouter_model=data.get("openrouter_model"),
            openrouter_proxy=openrouter_proxy,
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

        return FeatureSettings(
            working_dir=override.working_dir if override.working_dir is not None else self.working_dir,
            model=override.model if override.model is not None else self.model,
            session_prefix=override.session_prefix if override.session_prefix is not None else self.session_prefix,
            worktree=merged_worktree,
            enabled_session_types=override.enabled_session_types if override.enabled_session_types is not None else self.enabled_session_types,
            openrouter_model=override.openrouter_model if override.openrouter_model is not None else self.openrouter_model,
            openrouter_proxy=merged_openrouter_proxy,
        )


@dataclass
class Config:
    """Level 1: Global Zen Portal configuration.

    Stored in ~/.config/zen-portal/config.json
    These are persistent defaults that rarely change.
    """

    exit_behavior: ExitBehavior = ExitBehavior.ASK
    features: FeatureSettings = field(default_factory=FeatureSettings)

    def to_dict(self) -> dict:
        return {
            "exit_behavior": self.exit_behavior.value,
            "features": self.features.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        features = FeatureSettings.from_dict(data.get("features", {}))
        return cls(
            exit_behavior=ExitBehavior(data.get("exit_behavior", "ask")),
            features=features,
        )


@dataclass
class PortalState:
    """Level 2: Current zen-portal state.

    Stored in ~/.config/zen-portal/portal.json
    Survives restarts. Use for "current project" or temporary overrides.
    Clear explicitly when switching contexts.
    """

    features: FeatureSettings = field(default_factory=FeatureSettings)
    description: str = ""  # Optional description of current context

    def to_dict(self) -> dict:
        return {
            "features": self.features.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PortalState":
        return cls(
            features=FeatureSettings.from_dict(data.get("features", {})),
            description=data.get("description", ""),
        )


class ConfigManager:
    """Manages the 3-tier configuration system."""

    DEFAULT_SESSION_PREFIX = "zen"

    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "zen-portal"
        self._config_dir = config_dir
        self._config_file = config_dir / "config.json"
        self._portal_file = config_dir / "portal.json"
        self._config: Config | None = None
        self._portal: PortalState | None = None

    # --- Level 1: Config ---

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

    # --- Level 2: Portal State ---

    @property
    def portal(self) -> PortalState:
        if self._portal is None:
            self._portal = self._load_portal()
        return self._portal

    def _load_portal(self) -> PortalState:
        """Load portal state from disk."""
        if self._portal_file.exists():
            try:
                data = json.loads(self._portal_file.read_text())
                return PortalState.from_dict(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return PortalState()

    def save_portal(self, state: PortalState) -> None:
        """Save portal state to disk with secure permissions."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        _secure_write_json(self._portal_file, state.to_dict())
        self._portal = state

    def clear_portal(self) -> None:
        """Clear portal state (e.g., when switching projects)."""
        if self._portal_file.exists():
            self._portal_file.unlink()
        self._portal = PortalState()

    def update_portal_features(self, features: FeatureSettings, description: str = "") -> None:
        """Update portal-level feature overrides."""
        state = self.portal
        state.features = features
        if description:
            state.description = description
        self.save_portal(state)

    # --- Resolution: Merge all tiers ---

    def resolve_features(self, session_override: FeatureSettings | None = None) -> FeatureSettings:
        """Resolve features through all tiers.

        Resolution order: session > portal > config > defaults

        Args:
            session_override: Optional session-level overrides

        Returns:
            Fully resolved FeatureSettings with defaults filled in
        """
        # Start with config defaults
        resolved = self.config.features

        # Apply portal overrides
        resolved = resolved.merge_with(self.portal.features)

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

    # --- Proxy Settings ---

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
