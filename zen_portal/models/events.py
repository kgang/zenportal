"""Custom Textual Message events for Zen Portal UI.

Note: Service-level events (SessionCreated, SessionPaused, etc.) are in
services/events.py and use the EventBus pattern.
"""

from textual.message import Message

from .session import Session


class SessionSelected(Message):
    """Fired when a session is selected in the list (UI event)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()
