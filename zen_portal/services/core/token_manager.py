"""TokenManager: Token statistics tracking for Claude sessions.

Extracted from SessionManager to provide focused token operations.
"""

from ..token_parser import TokenParser
from ..discovery import DiscoveryService
from ...models.session import Session, SessionType


class TokenManager:
    """Manages token statistics and history for Claude sessions.

    Provides:
    - Token usage statistics (input/output/cache)
    - Token history for sparkline visualization
    - Auto-discovery of Claude session IDs
    """

    def __init__(self, token_parser: TokenParser | None = None):
        self._parser = token_parser or TokenParser()
        self._discovery = DiscoveryService()

    def update_session(self, session: Session) -> bool:
        """Update token statistics and history for a session.

        Args:
            session: Session to update (must be Claude type)

        Returns:
            True if any stats were updated
        """
        if session.session_type != SessionType.CLAUDE:
            return False

        # Auto-discover claude_session_id if missing
        if not session.claude_session_id and session.resolved_working_dir:
            discovered_id = self._discover_session_id(session)
            if discovered_id:
                session.claude_session_id = discovered_id

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
            # Extended metrics from SessionTokenStats
            session.message_count = stats.message_count
            session.first_message_at = stats.first_message_at
            session.last_message_at = stats.last_message_at
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

    def _discover_session_id(self, session: Session) -> str | None:
        """Discover Claude session ID from JSONL files.

        Looks for the most recent session file in the project directory
        that was modified after the session was created.

        Args:
            session: Session to discover ID for

        Returns:
            Discovered session ID or None
        """
        if not session.resolved_working_dir:
            return None

        # Find Claude sessions for this working directory
        sessions = self._discovery.list_claude_sessions(
            project_path=session.resolved_working_dir,
            limit=5,
        )

        if not sessions:
            return None

        # Find the most recent session that was modified after this session started
        # This helps match the correct session when multiple exist
        for claude_session in sessions:
            if claude_session.modified_at >= session.created_at:
                return claude_session.session_id

        # Fallback to most recent if none match the time window
        return sessions[0].session_id if sessions else None
