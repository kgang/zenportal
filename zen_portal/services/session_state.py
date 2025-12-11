"""SessionStateService: Thread-safe session state persistence."""

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..models.session import Session, SessionState, SessionType
from ..models.session import Session
from .config import ClaudeModel
from .state import SessionRecord, PortalState


logger = logging.getLogger(__name__)


class SessionStateService:
    """Handles session persistence with thread-safe operations."""

    STATE_FILE = "state.json"
    HISTORY_DIR = "history"

    def __init__(self, base_dir: Path):
        """Initialize state service.

        Args:
            base_dir: Base directory for state files (~/.zen_portal)
        """
        self._base_dir = base_dir
        self._state_file = base_dir / self.STATE_FILE
        self._history_dir = base_dir / self.HISTORY_DIR
        self._lock = threading.RLock()  # Reentrant lock for nested calls

    @contextmanager
    def _transaction(self):
        """Context manager for state transactions."""
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> PortalState:
        """Load state from disk with lock.

        Returns empty state if file doesn't exist or is corrupted.
        """
        with self._transaction():
            if not self._state_file.exists():
                return PortalState()

            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                return PortalState.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to load state file, using empty state: {e}")
                return PortalState()

    def save(
        self,
        sessions: list[Session],
        session_order: list[str] | None = None,
        selected_session_id: str | None = None,
    ) -> bool:
        """Save state to disk atomically with lock.

        Uses temp file + rename for atomic writes.

        Args:
            sessions: List of sessions to persist
            session_order: Optional custom display order
            selected_session_id: Optional cursor position (session ID)

        Returns:
            True on success, False on failure
        """
        with self._transaction():
            self._ensure_dirs()

            records = [self._session_to_record(s) for s in sessions]
            state = PortalState(
                sessions=records,
                session_order=session_order or [],
                selected_session_id=selected_session_id,
            )
            state.last_updated = datetime.now().isoformat()

            # Write to temp file first
            temp_file = self._state_file.with_suffix(".tmp")
            try:
                with open(temp_file, "w") as f:
                    json.dump(state.to_dict(), f, indent=2)

                # Atomic rename
                temp_file.rename(self._state_file)
                return True
            except OSError as e:
                logger.error(f"Failed to save state: {e}")
                # Clean up temp file if it exists
                if temp_file.exists():
                    temp_file.unlink()
                return False

    def append_history(self, session: Session, event: str = "update") -> None:
        """Append a session event to today's history log.

        History is stored as JSONL (one JSON object per line) for easy
        streaming reads and appends.

        Args:
            session: Session to log
            event: Event type (created, updated, ended, cleaned)
        """
        with self._transaction():
            self._ensure_dirs()

            today = datetime.now().strftime("%Y-%m-%d")
            history_file = self._history_dir / f"{today}.jsonl"

            record = self._session_to_record(session)
            entry = {
                "timestamp": datetime.now().isoformat(),
                "event": event,
                "session": record.to_dict(),
            }

            try:
                with open(history_file, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except OSError as e:
                logger.warning(f"Failed to append session history: {e}")

    def _session_to_record(self, session: Session) -> SessionRecord:
        """Convert a Session to a persistable record."""
        external_name = None
        if hasattr(session, "_external_tmux_name"):
            external_name = session._external_tmux_name

        # Extract token stats if available
        input_tokens = 0
        output_tokens = 0
        cache_tokens = 0
        if session.token_stats:
            input_tokens = session.token_stats.input_tokens
            output_tokens = session.token_stats.output_tokens
            cache_tokens = session.token_stats.cache_tokens

        return SessionRecord(
            id=session.id,
            name=session.name,
            session_type=session.session_type.value,
            provider=session.provider,
            state=session.state.value,
            created_at=session.created_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            claude_session_id=session.claude_session_id,
            worktree_path=str(session.worktree_path) if session.worktree_path else None,
            worktree_branch=session.worktree_branch,
            working_dir=str(session.resolved_working_dir) if session.resolved_working_dir else None,
            model=session.resolved_model.value if session.resolved_model else None,
            external_tmux_name=external_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_tokens=cache_tokens,
            message_count=session.message_count,
            uses_proxy=session.uses_proxy,
            token_history=session.token_history,
        )

    def session_from_record(
        self,
        record: SessionRecord,
        tmux_name_func: callable,
        tmux_exists_func: callable,
        is_pane_dead_func: callable,
    ) -> Session | None:
        """Reconstruct a Session from a persisted record.

        Args:
            record: SessionRecord to restore
            tmux_name_func: Function to compute tmux name from session ID
            tmux_exists_func: Function to check if tmux session exists
            is_pane_dead_func: Function to check if tmux pane is dead

        Returns:
            Session if it should be restored, None otherwise
        """
        # Parse state
        try:
            state = SessionState(record.state)
        except ValueError:
            state = SessionState.COMPLETED

        # Parse session type
        try:
            session_type = SessionType(record.session_type)
        except ValueError:
            session_type = SessionType.AI

        # Parse timestamps
        try:
            created_at = datetime.fromisoformat(record.created_at)
        except ValueError:
            created_at = datetime.now()

        ended_at = None
        if record.ended_at:
            try:
                ended_at = datetime.fromisoformat(record.ended_at)
            except ValueError:
                pass

        # Determine tmux name for this session
        if record.external_tmux_name:
            tmux_name = record.external_tmux_name
        else:
            tmux_name = tmux_name_func(record.id)

        # Check if tmux session still exists
        tmux_exists = tmux_exists_func(tmux_name)
        tmux_dead = tmux_exists and is_pane_dead_func(tmux_name)

        # Check if worktree still exists
        worktree_exists = (
            record.worktree_path
            and Path(record.worktree_path).exists()
        )

        # Decide whether to restore this session
        # Restore if: tmux exists (alive or dead) OR worktree exists OR paused
        # Paused sessions are always restored (user explicitly preserved them)
        if not tmux_exists and not worktree_exists and state != SessionState.PAUSED:
            return None

        # Reconstruct session
        session = Session(
            name=record.name,
            claude_session_id=record.claude_session_id,
            session_type=session_type,
            provider=record.provider,
            created_at=created_at,
            ended_at=ended_at,
            resolved_working_dir=Path(record.working_dir) if record.working_dir else None,
            worktree_path=Path(record.worktree_path) if record.worktree_path else None,
            worktree_branch=record.worktree_branch,
            uses_proxy=record.uses_proxy,
            message_count=record.message_count,
            token_history=record.token_history,
        )

        # Override the auto-generated ID with the persisted one
        session.id = record.id

        # Set tmux name (computed or external)
        session.tmux_name = tmux_name
        if record.external_tmux_name:
            session._external_tmux_name = record.external_tmux_name

        # Set model if available
        if record.model:
            try:
                session.resolved_model = ClaudeModel(record.model)
            except ValueError:
                pass

        # Update state based on current tmux status
        if tmux_exists and not tmux_dead:
            session.state = SessionState.RUNNING
        elif state == SessionState.PAUSED:
            # Keep paused state if worktree exists
            session.state = SessionState.PAUSED if worktree_exists else SessionState.COMPLETED
        elif state == SessionState.KILLED:
            session.state = SessionState.KILLED
        else:
            session.state = SessionState.COMPLETED

        return session

    @property
    def base_dir(self) -> Path:
        """Get the base directory path."""
        return self._base_dir
