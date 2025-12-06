"""Data models for new session modal."""

from dataclasses import dataclass
from enum import Enum

from .session import SessionFeatures
from ..services.discovery import ClaudeSessionInfo, ExternalTmuxSession


class NewSessionType(Enum):
    """Type of session to create in new session modal."""

    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    SHELL = "shell"
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
    features: SessionFeatures | None = None
    session_type: NewSessionType = NewSessionType.CLAUDE
    # For ATTACH sessions
    tmux_session: ExternalTmuxSession | None = None
    # For RESUME sessions
    claude_session: ClaudeSessionInfo | None = None
