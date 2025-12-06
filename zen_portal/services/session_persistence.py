"""Session persistence: loading and saving session state."""

from datetime import datetime
from pathlib import Path

from ..models.session import Session, SessionState, SessionType
from .state import StateService, PortalState, SessionRecord


class SessionPersistence:
    """Handles loading and saving session state to disk."""

    def __init__(
        self,
        state_service: StateService,
        tmux_name_func,
        tmux_session_exists_func,
        tmux_is_pane_dead_func,
    ):
        """Initialize persistence handler.

        Args:
            state_service: Service for reading/writing state files
            tmux_name_func: Function to generate tmux name from session ID
            tmux_session_exists_func: Function to check if tmux session exists
            tmux_is_pane_dead_func: Function to check if tmux pane is dead
        """
        self._state = state_service
        self._tmux_name = tmux_name_func
        self._tmux_session_exists = tmux_session_exists_func
        self._tmux_is_pane_dead = tmux_is_pane_dead_func

    def load_persisted_sessions(self) -> dict[str, Session]:
        """Load sessions from persisted state on startup.

        Only restores sessions that still have valid tmux sessions or worktrees.
        Dead sessions without resources are discarded.

        Returns:
            Dictionary mapping session ID to Session
        """
        state = self._state.load_state()
        sessions = {}

        for record in state.sessions:
            session = self._session_from_record(record)
            if session:
                sessions[session.id] = session

        return sessions

    def _session_from_record(self, record: SessionRecord) -> Session | None:
        """Reconstruct a Session from a persisted record.

        Returns None if the session should not be restored (no valid resources).
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
            session_type = SessionType.CLAUDE

        # Parse created_at
        try:
            created_at = datetime.fromisoformat(record.created_at)
        except ValueError:
            created_at = datetime.now()

        # Parse ended_at
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
            tmux_name = self._tmux_name(record.id)

        # Check if tmux session still exists
        tmux_exists = self._tmux_session_exists(tmux_name)
        tmux_dead = tmux_exists and self._tmux_is_pane_dead(tmux_name)

        # Check if worktree still exists
        worktree_exists = (
            record.worktree_path
            and Path(record.worktree_path).exists()
        )

        # Decide whether to restore this session
        # Restore if: tmux exists (alive or dead) OR worktree exists
        if not tmux_exists and not worktree_exists:
            return None

        # Reconstruct session
        session = Session(
            name=record.name,
            claude_session_id=record.claude_session_id,
            session_type=session_type,
            created_at=created_at,
            ended_at=ended_at,
            resolved_working_dir=Path(record.working_dir) if record.working_dir else None,
            worktree_path=Path(record.worktree_path) if record.worktree_path else None,
            worktree_branch=record.worktree_branch,
        )

        # Override the auto-generated ID with the persisted one
        session.id = record.id

        # Set external tmux name if applicable
        if record.external_tmux_name:
            session._external_tmux_name = record.external_tmux_name

        # Set model if available
        if record.model:
            from .config import ClaudeModel
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

    def session_to_record(self, session: Session) -> SessionRecord:
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
        )

    def save_state(self, sessions: dict[str, Session]) -> bool:
        """Persist current session state to disk.

        Returns True on success.
        """
        records = [self.session_to_record(s) for s in sessions.values()]
        state = PortalState(sessions=records)
        return self._state.save_state(state)

    def append_history(self, session: Session, event: str) -> None:
        """Append a session event to history log."""
        record = self.session_to_record(session)
        self._state.append_history(record, event)
