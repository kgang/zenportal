"""Exception hierarchy for Zenportal.

Zen principle: Transparent failures with sympathetic error messages.
"""


class ZenError(Exception):
    """Base exception for all Zenportal errors.

    All domain-specific exceptions inherit from this base class,
    enabling consistent error handling across the application.
    """

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message} ({self.suggestion})"
        return self.message


class SessionError(ZenError):
    """Session operation failed."""

    pass


class SessionNotFoundError(SessionError):
    """Session with given ID does not exist."""

    pass


class SessionStateError(SessionError):
    """Session is in invalid state for operation."""

    pass


class ConfigError(ZenError):
    """Configuration is invalid or missing."""

    pass


class ConfigValidationError(ConfigError):
    """Configuration value failed validation."""

    pass


class WorktreeError(ZenError):
    """Git worktree operation failed."""

    pass


class WorktreeExistsError(WorktreeError):
    """Worktree already exists at path."""

    pass


class WorktreeNotFoundError(WorktreeError):
    """Worktree does not exist."""

    pass


class ValidationError(ZenError):
    """Input validation failed."""

    pass


class TmuxError(ZenError):
    """Tmux operation failed."""

    pass


class TmuxSessionNotFoundError(TmuxError):
    """Tmux session does not exist."""

    pass


class DiscoveryError(ZenError):
    """Service discovery failed."""

    pass
