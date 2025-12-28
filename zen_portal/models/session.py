"""Session model for Zen Portal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from ..services.config import ClaudeModel
    from ..services.token_parser import TokenUsage


@dataclass
class SessionTokenMetrics:
    """Token tracking metrics for Claude sessions.

    Extracted from Session to separate concerns - these fields are
    only relevant for Claude AI sessions with token tracking enabled.
    """

    # Core token usage (populated from Claude JSONL parsing)
    token_stats: TokenUsage | None = None
    # Extended token metrics (from SessionTokenStats)
    message_count: int = 0  # Number of API turns
    first_message_at: datetime | None = None  # Session start time (from Claude)
    last_message_at: datetime | None = None  # Last activity time (from Claude)
    # Token history for sparkline visualization (cumulative totals over time)
    token_history: list[int] = field(default_factory=list)
    # Proxy tracking - whether session uses OpenRouter billing (pay-per-token)
    uses_proxy: bool = False
    # Proxy warning (set when proxy validation finds issues)
    proxy_warning: str = ""


class SessionType(Enum):
    """Type of session."""

    AI = "ai"  # AI session (with provider: claude, codex, gemini, openrouter)
    SHELL = "shell"  # Plain shell session


class SessionState(Enum):
    """State of a Claude session."""

    RUNNING = "running"  # Active tmux session
    COMPLETED = "completed"  # Completed normally
    FAILED = "failed"  # Failed to start (tmux error)
    PAUSED = "paused"  # Manually paused (worktree preserved)
    KILLED = "killed"  # Manually killed (worktree removed)


@dataclass
class SessionFeatures:
    """Level 3: Session-specific feature overrides.

    These override both config and portal settings for this specific session.
    Stored per-session, not persisted to disk.
    """

    working_dir: Path | None = None
    model: ClaudeModel | None = None
    # Worktree overrides
    use_worktree: bool | None = None  # Override config/portal worktree.enabled
    worktree_branch: str | None = None  # Specific branch name for this session
    # Dangerous mode - skip permission checks
    dangerously_skip_permissions: bool = False

    def has_overrides(self) -> bool:
        """Return True if any overrides are set."""
        return (
            self.working_dir is not None
            or self.model is not None
            or self.use_worktree is not None
            or self.worktree_branch is not None
            or self.dangerously_skip_permissions
        )


@dataclass
class Session:
    """A Claude Code session running in tmux."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""  # Display name
    prompt: str = ""  # Initial prompt (if any)
    claude_session_id: str = ""  # Claude Code session ID for --resume
    state: SessionState = SessionState.RUNNING
    session_type: SessionType = SessionType.AI  # Type of session (AI or SHELL)
    provider: str = "claude"  # AI provider: claude, codex, gemini, openrouter (for AI sessions)
    created_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    # Level 3: Session-specific feature overrides
    features: SessionFeatures = field(default_factory=SessionFeatures)
    # Resolved values at creation time (for display)
    resolved_working_dir: Path | None = None
    resolved_model: ClaudeModel | None = None
    # Worktree tracking (if created)
    worktree_path: Path | None = None  # Path to worktree directory
    worktree_branch: str | None = None  # Branch name in worktree
    worktree_source_repo: Path | None = None  # Source repo worktree was created from
    # Dangerous mode
    dangerously_skip_permissions: bool = False
    # Revive tracking - prevents immediate COMPLETED detection after revive
    revived_at: datetime | None = None
    # Error tracking for failed sessions
    error_message: str = ""
    # Token metrics for Claude sessions (None for non-Claude or shell sessions)
    token_metrics: SessionTokenMetrics | None = None
    # tmux session name (e.g., "zen-a1b2c3d4")
    tmux_name: str = ""

    # Convenience properties for backward compatibility with token_metrics fields
    @property
    def token_stats(self) -> TokenUsage | None:
        """Get token_stats from token_metrics (backward compatibility)."""
        return self.token_metrics.token_stats if self.token_metrics else None

    @property
    def message_count(self) -> int:
        """Get message_count from token_metrics (backward compatibility)."""
        return self.token_metrics.message_count if self.token_metrics else 0

    @property
    def first_message_at(self) -> datetime | None:
        """Get first_message_at from token_metrics (backward compatibility)."""
        return self.token_metrics.first_message_at if self.token_metrics else None

    @property
    def last_message_at(self) -> datetime | None:
        """Get last_message_at from token_metrics (backward compatibility)."""
        return self.token_metrics.last_message_at if self.token_metrics else None

    @property
    def token_history(self) -> list[int]:
        """Get token_history from token_metrics (backward compatibility)."""
        return self.token_metrics.token_history if self.token_metrics else []

    @property
    def uses_proxy(self) -> bool:
        """Get uses_proxy from token_metrics (backward compatibility)."""
        return self.token_metrics.uses_proxy if self.token_metrics else False

    @property
    def proxy_warning(self) -> str:
        """Get proxy_warning from token_metrics (backward compatibility)."""
        return self.token_metrics.proxy_warning if self.token_metrics else ""

    def __post_init__(self):
        # Don't auto-generate claude_session_id - let Claude Code generate it
        # We'll discover it later when needed for revival
        pass

    @property
    def age_seconds(self) -> int:
        return int((datetime.now() - self.created_at).total_seconds())

    @property
    def age_display(self) -> str:
        """Poetic, human-friendly time display."""
        seconds = self.age_seconds
        if seconds < 30:
            return "now"
        elif seconds < 90:
            return "1m"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 7200:
            return "1h"
        else:
            hours = seconds // 3600
            return f"{hours}h"

    @property
    def status_glyph(self) -> str:
        """Binary state indicator: running or not.

        ▪ running (filled, present)
        ▫ not running (empty, released)
        """
        return "▪" if self.state == SessionState.RUNNING else "▫"

    @property
    def display_name(self) -> str:
        """Name for display in UI.

        Falls back to session type if no name or prompt available.
        """
        text = self.name or self.prompt or self.session_type.value
        first_line = text.split("\n")[0].strip()
        if len(first_line) <= 30:
            return first_line
        return first_line[:27] + "..."

    @property
    def is_active(self) -> bool:
        """Return True if session is currently running."""
        return self.state == SessionState.RUNNING

    @property
    def should_display(self) -> bool:
        """Return True if session should be visible in the list.

        All states except those that have been explicitly cleaned are visible.
        This includes RUNNING, COMPLETED, FAILED, PAUSED, and KILLED sessions.
        Sessions are only hidden after explicit cleanup via the 'd' key.
        """
        return True  # All sessions visible until explicitly cleaned
