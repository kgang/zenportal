"""Data models for new session modal."""

from dataclasses import dataclass
from enum import Enum

from .session import SessionFeatures, SessionType
from ..services.discovery import ClaudeSessionInfo, ExternalTmuxSession

# Backwards compatibility alias - use SessionType directly
NewSessionType = SessionType


class AIProvider(Enum):
    """AI provider for AI sessions."""

    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class ResultType(Enum):
    """Type of result from the modal."""

    NEW = "new"
    ATTACH = "attach"
    RESUME = "resume"


@dataclass
class NewSessionResult:
    """Result from new session modal."""

    result_type: ResultType
    # For NEW sessions
    name: str = ""
    prompt: str = ""
    system_prompt: str = ""  # Claude --system-prompt argument
    features: SessionFeatures | None = None
    session_type: SessionType = SessionType.AI
    provider: AIProvider = AIProvider.CLAUDE  # AI provider for AI sessions
    # For ATTACH sessions
    tmux_session: ExternalTmuxSession | None = None
    # For RESUME sessions
    claude_session: ClaudeSessionInfo | None = None
