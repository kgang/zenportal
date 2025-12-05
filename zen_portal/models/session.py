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


class SessionType(Enum):
    """Type of session."""

    CLAUDE = "claude"  # Claude Code session
    CODEX = "codex"  # OpenAI Codex CLI
    GEMINI = "gemini"  # Google Gemini CLI
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
    session_type: SessionType = SessionType.CLAUDE  # Type of session
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
    # Dangerous mode
    dangerously_skip_permissions: bool = False
    # Revive tracking - prevents immediate COMPLETED detection after revive
    revived_at: datetime | None = None

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
        """State indicator glyphs.

        ● active (filled, present)
        ○ complete (open, released)
        ◐ paused (half, suspended)
        · ended (small, minimal)
        """
        glyphs = {
            SessionState.RUNNING: "●",
            SessionState.COMPLETED: "○",
            SessionState.FAILED: "·",
            SessionState.PAUSED: "◐",
            SessionState.KILLED: "·",
        }
        return glyphs.get(self.state, "?")

    @property
    def display_name(self) -> str:
        """Name for display in UI."""
        text = self.name or self.prompt or "claude"
        first_line = text.split("\n")[0].strip()
        if len(first_line) <= 30:
            return first_line
        return first_line[:27] + "..."

    @property
    def is_active(self) -> bool:
        return self.state == SessionState.RUNNING
