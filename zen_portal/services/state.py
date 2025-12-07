"""State persistence service for zen-portal.

Provides persistent state storage under ~/.zen_portal/, inspired by:
- Git's .git directory structure (simple, file-based)
- GitHub Actions workflow state (run history, artifacts)

Directory structure:
    ~/.zen_portal/
    ├── state.json       # Current session state (survives restarts)
    └── history/         # Session history logs
        └── YYYY-MM-DD.jsonl

Design principles:
- Minimalist: Only persist what's necessary
- Atomic: Use temp files + rename for safe writes
- Human-readable: JSON with pretty formatting
- Recoverable: History enables debugging/analytics
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionRecord:
    """Minimal record of a session for persistence."""

    id: str
    name: str
    session_type: str  # "claude" | "shell" | "codex"
    state: str  # SessionState value
    created_at: str  # ISO format
    ended_at: str | None = None
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
    # Proxy billing flag (for cost tracking)
    uses_proxy: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            session_type=data.get("session_type", "claude"),
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
            uses_proxy=data.get("uses_proxy", False),
        )


@dataclass
class PortalState:
    """Complete portal state for persistence."""

    version: int = 1  # Schema version for future migrations
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    sessions: list[SessionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortalState":
        """Create from dictionary."""
        return cls(
            version=data.get("version", 1),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
            sessions=[
                SessionRecord.from_dict(s) for s in data.get("sessions", [])
            ],
        )


class StateService:
    """Manages persistent state for zen-portal.

    State is stored in ~/.zen_portal/ with atomic writes to prevent corruption.
    Inspired by Git's approach: simple files, human-readable, recoverable.
    """

    STATE_FILE = "state.json"
    HISTORY_DIR = "history"

    def __init__(self, base_dir: Path | None = None):
        """Initialize state service.

        Args:
            base_dir: Override base directory (default: ~/.zen_portal)
        """
        if base_dir:
            self._base_dir = base_dir
        else:
            self._base_dir = Path.home() / ".zen_portal"

        self._state_file = self._base_dir / self.STATE_FILE
        self._history_dir = self._base_dir / self.HISTORY_DIR

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> PortalState:
        """Load state from disk.

        Returns empty state if file doesn't exist or is corrupted.
        """
        if not self._state_file.exists():
            return PortalState()

        try:
            with open(self._state_file) as f:
                data = json.load(f)
            return PortalState.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted state - return empty
            return PortalState()

    def save_state(self, state: PortalState) -> bool:
        """Save state to disk atomically.

        Uses temp file + rename for atomic writes (like Git).
        Returns True on success.
        """
        self._ensure_dirs()

        # Update timestamp
        state.last_updated = datetime.now().isoformat()

        # Write to temp file first
        temp_file = self._state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(state.to_dict(), f, indent=2)

            # Atomic rename
            temp_file.rename(self._state_file)
            return True
        except OSError:
            # Clean up temp file if it exists
            if temp_file.exists():
                temp_file.unlink()
            return False

    def append_history(self, record: SessionRecord, event: str = "update") -> None:
        """Append a session event to today's history log.

        History is stored as JSONL (one JSON object per line) for easy
        streaming reads and appends. Inspired by GitHub Actions logs.

        Args:
            record: Session record to log
            event: Event type (created, updated, ended, cleaned)
        """
        self._ensure_dirs()

        today = datetime.now().strftime("%Y-%m-%d")
        history_file = self._history_dir / f"{today}.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "session": record.to_dict(),
        }

        try:
            with open(history_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # History is optional, don't fail on errors

    def clear_state(self) -> bool:
        """Clear all session state (but preserve history).

        Returns True on success.
        """
        if self._state_file.exists():
            try:
                self._state_file.unlink()
                return True
            except OSError:
                return False
        return True

    def get_history_days(self) -> list[str]:
        """Get list of days with history (YYYY-MM-DD format)."""
        if not self._history_dir.exists():
            return []

        days = []
        for file in self._history_dir.glob("*.jsonl"):
            day = file.stem
            if len(day) == 10:  # YYYY-MM-DD
                days.append(day)

        return sorted(days, reverse=True)

    def read_history(self, day: str) -> list[dict[str, Any]]:
        """Read history entries for a specific day.

        Args:
            day: Date in YYYY-MM-DD format

        Returns:
            List of history entries
        """
        history_file = self._history_dir / f"{day}.jsonl"
        if not history_file.exists():
            return []

        entries = []
        try:
            with open(history_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            pass

        return entries

    def prune_history(self, keep_days: int = 30) -> int:
        """Remove history files older than keep_days.

        Args:
            keep_days: Number of days to keep

        Returns:
            Number of files pruned
        """
        if not self._history_dir.exists():
            return 0

        cutoff = datetime.now().strftime("%Y-%m-%d")
        # Calculate cutoff date
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        cutoff = cutoff_date.strftime("%Y-%m-%d")

        pruned = 0
        for file in self._history_dir.glob("*.jsonl"):
            if file.stem < cutoff:
                try:
                    file.unlink()
                    pruned += 1
                except OSError:
                    pass

        return pruned

    @property
    def base_dir(self) -> Path:
        """Get the base directory path."""
        return self._base_dir
