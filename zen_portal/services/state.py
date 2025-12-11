"""State persistence dataclasses for zen-portal.

Provides data structures for session persistence.
State management is now handled directly by SessionManager.

These dataclasses are used for serialization/deserialization:
- SessionRecord: Minimal record of a session for persistence
- PortalState: Complete portal state structure

The actual persistence logic (save/load) has been merged into SessionManager.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class SessionRecord:
    """Minimal record of a session for persistence."""

    id: str
    name: str
    session_type: str  # "ai" | "shell"
    state: str  # SessionState value
    created_at: str  # ISO format
    ended_at: str | None = None
    # AI provider (for AI sessions)
    provider: str = "claude"  # "claude" | "codex" | "gemini" | "openrouter"
    # Claude-specific
    claude_session_id: str = ""
    # Worktree info
    worktree_path: str | None = None
    worktree_branch: str | None = None
    # Resolved config
    working_dir: str | None = None
    model: str | None = None
    # External tmux session name (for adopted sessions)
    external_tmux_name: str | None = None
    # Token tracking (persisted from session)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    message_count: int = 0  # Number of API turns
    # Proxy billing flag (for cost tracking)
    uses_proxy: bool = False
    # Token history for sparkline (cumulative totals over time)
    token_history: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        """Create from dictionary."""
        # Handle migration from old session_type values
        session_type = data.get("session_type", "ai")
        provider = data.get("provider", "claude")

        # Migrate old session types to new format
        if session_type in ("claude", "codex", "gemini", "openrouter"):
            provider = session_type
            session_type = "ai"
        elif session_type == "shell":
            session_type = "shell"

        return cls(
            id=data["id"],
            name=data["name"],
            session_type=session_type,
            provider=provider,
            state=data.get("state", "bloomed"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            ended_at=data.get("ended_at"),
            claude_session_id=data.get("claude_session_id", ""),
            worktree_path=data.get("worktree_path"),
            worktree_branch=data.get("worktree_branch"),
            working_dir=data.get("working_dir"),
            model=data.get("model"),
            external_tmux_name=data.get("external_tmux_name"),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_tokens=data.get("cache_tokens", 0),
            message_count=data.get("message_count", 0),
            uses_proxy=data.get("uses_proxy", False),
            token_history=data.get("token_history", []),
        )


@dataclass
class PortalState:
    """Complete portal state for persistence."""

    version: int = 1  # Schema version for future migrations
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    sessions: list[SessionRecord] = field(default_factory=list)
    session_order: list[str] = field(default_factory=list)  # Custom display order
    selected_session_id: str | None = None  # Cursor position (session ID)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "version": self.version,
            "last_updated": self.last_updated,
            "sessions": [s.to_dict() for s in self.sessions],
        }
        if self.session_order:
            result["session_order"] = self.session_order
        if self.selected_session_id:
            result["selected_session_id"] = self.selected_session_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortalState":
        """Create from dictionary."""
        return cls(
            version=data.get("version", 1),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
            sessions=[
                SessionRecord.from_dict(s) for s in data.get("sessions", [])
            ],
            session_order=data.get("session_order", []),
            selected_session_id=data.get("selected_session_id"),
        )
