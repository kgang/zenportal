"""StateRefresher: Session state polling and updates.

Extracted from SessionManager to provide focused state refresh operations.
Uses the detection module for pure state detection logic.
"""

from datetime import datetime
from typing import Callable

from ..tmux import TmuxService
from .detection import detect_session_state
from ...models.session import Session, SessionState, SessionType


class StateRefresher:
    """Polls tmux and updates session states.

    Orchestrates:
    - Polling of sessions
    - Token updates for Claude sessions

    Detection logic is delegated to the detection module.
    """

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

        # Clear revival marker if present (no grace period)
        if session.revived_at:
            session.revived_at = None

        # Use pure detection function
        result = detect_session_state(self._tmux, tmux_name)

        if result.state != session.state:
            session.state = result.state
            session.ended_at = datetime.now() if result.state != SessionState.RUNNING else None
            session.error_message = result.error_message or ""
            return True

        # Update tokens for running Claude AI sessions
        if (session.state == SessionState.RUNNING
            and session.session_type == SessionType.AI
            and getattr(session, 'provider', 'claude') == 'claude'):
            if self._on_token_update:
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

        result = detect_session_state(self._tmux, tmux_name)
        return result.state == SessionState.RUNNING
