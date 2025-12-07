"""StateRefresher: Session state polling and updates.

Extracted from SessionManager to provide focused state refresh operations.
"""

from datetime import datetime
from typing import Callable

from ..tmux import TmuxService
from ...models.session import Session, SessionState, SessionType


class StateRefresher:
    """Polls tmux and updates session states.

    Provides:
    - State detection (running → completed/failed)
    - Exit code handling
    - Grace period after revival
    """

    # Grace period after revival before checking state (seconds)
    REVIVAL_GRACE_PERIOD = 5.0

    def __init__(
        self,
        tmux: TmuxService,
        get_tmux_name: Callable[[str], str | None],
        on_token_update: Callable[[Session], None] | None = None,
    ):
        """Initialize state refresher.

        Args:
            tmux: Tmux service for session operations
            get_tmux_name: Function to get tmux name from session ID
            on_token_update: Optional callback for Claude token updates
        """
        self._tmux = tmux
        self._get_tmux_name = get_tmux_name
        self._on_token_update = on_token_update

    def refresh(self, sessions: dict[str, Session]) -> list[Session]:
        """Refresh states for all sessions.

        Args:
            sessions: Dict of session ID → Session

        Returns:
            List of sessions whose state changed
        """
        changed = []
        for session in sessions.values():
            if self._refresh_single(session):
                changed.append(session)
        return changed

    def _refresh_single(self, session: Session) -> bool:
        """Refresh state for a single session.

        Args:
            session: Session to refresh

        Returns:
            True if state changed
        """
        if session.state != SessionState.RUNNING:
            return False

        tmux_name = self._get_tmux_name(session.id)
        if not tmux_name:
            return False

        # Check if tmux session still exists
        if not self._tmux.session_exists(tmux_name):
            session.state = SessionState.COMPLETED
            session.ended_at = datetime.now()
            session.revived_at = None
            return True

        # Grace period check after revival
        if session.revived_at:
            grace_elapsed = (datetime.now() - session.revived_at).total_seconds()
            if grace_elapsed < self.REVIVAL_GRACE_PERIOD:
                return False
            session.revived_at = None

        # Check if pane is dead (process exited)
        if self._tmux.is_pane_dead(tmux_name):
            exit_status = self._tmux.get_pane_exit_status(tmux_name)
            if exit_status is not None and exit_status != 0:
                session.state = SessionState.FAILED
                session.error_message = f"Process exited with code {exit_status}"
            else:
                session.state = SessionState.COMPLETED
            session.ended_at = datetime.now()
            return True

        # Update tokens for running Claude sessions
        if session.session_type == SessionType.CLAUDE and self._on_token_update:
            self._on_token_update(session)

        return False

    def is_session_alive(self, session: Session) -> bool:
        """Check if a session's tmux process is still alive.

        Args:
            session: Session to check

        Returns:
            True if tmux session exists and pane is not dead
        """
        tmux_name = self._get_tmux_name(session.id)
        if not tmux_name:
            return False

        if not self._tmux.session_exists(tmux_name):
            return False

        return not self._tmux.is_pane_dead(tmux_name)
