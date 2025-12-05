"""Custom Textual events for Zen Portal."""

from textual.message import Message

from .session import Session


class SessionCreated(Message):
    """Fired when a new session is created."""

    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()


class SessionStateChanged(Message):
    """Fired when session state changes."""

    def __init__(self, session: Session, old_state: str) -> None:
        self.session = session
        self.old_state = old_state
        super().__init__()


class SessionOutput(Message):
    """Fired when new output is available."""

    def __init__(self, session_id: str, output: str) -> None:
        self.session_id = session_id
        self.output = output
        super().__init__()


class SessionPaused(Message):
    """Fired when a session is paused (tmux ended, worktree preserved)."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__()


class SessionKilled(Message):
    """Fired when a session is killed (tmux ended, worktree removed)."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__()


class SessionCleaned(Message):
    """Fired when a paused session's worktree is cleaned up."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__()


class SessionSelected(Message):
    """Fired when a session is selected in the list."""

    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()
