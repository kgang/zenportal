"""Data models for new session modal."""

from dataclasses import dataclass
from enum import Enum

from .session import SessionFeatures
from ..services.discovery import ClaudeSessionInfo, ExternalTmuxSession


class NewSessionType(Enum):
    """Type of session to create in new session modal."""

    AI = "ai"  # AI session (with provider selection)
    SHELL = "shell"  # Shell session


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
    session_type: NewSessionType = NewSessionType.AI
    provider: AIProvider = AIProvider.CLAUDE  # AI provider for AI sessions
    # For ATTACH sessions
    tmux_session: ExternalTmuxSession | None = None
    # For RESUME sessions
    claude_session: ClaudeSessionInfo | None = None
