"""TokenManager: Token statistics tracking for Claude sessions.

Extracted from SessionManager to provide focused token operations.
"""

from ..token_parser import TokenParser
from ...models.session import Session, SessionType


class TokenManager:
    """Manages token statistics and history for Claude sessions.

    Provides:
    - Token usage statistics (input/output/cache)
    - Token history for sparkline visualization
    """

    def __init__(self, token_parser: TokenParser | None = None):
        self._parser = token_parser or TokenParser()

    def update_session(self, session: Session) -> bool:
        """Update token statistics and history for a session.

        Args:
            session: Session to update (must be Claude with session ID)

        Returns:
            True if any stats were updated
        """
        if session.session_type != SessionType.CLAUDE:
            return False
        if not session.claude_session_id:
            return False

        updated = False

        # Update token statistics
        stats = self._parser.get_session_stats(
            claude_session_id=session.claude_session_id,
            working_dir=session.resolved_working_dir,
        )
        if stats:
            session.token_stats = stats.total_usage
            updated = True

        # Update token history for sparkline
        history = self._parser.get_token_history(
            claude_session_id=session.claude_session_id,
            working_dir=session.resolved_working_dir,
        )
        if history:
            session.token_history = history
            updated = True

        return updated

    def get_stats(self, session: Session):
        """Get current token statistics for a session.

        Args:
            session: Session to get stats for

        Returns:
            TokenUsage or None if not available
        """
        if session.session_type != SessionType.CLAUDE:
            return None
        return session.token_stats

    def get_history(self, session: Session) -> list[int]:
        """Get token history for sparkline visualization.

        Args:
            session: Session to get history for

        Returns:
            List of cumulative token totals, empty if not available
        """
        if session.session_type != SessionType.CLAUDE:
            return []
        return session.token_history or []
