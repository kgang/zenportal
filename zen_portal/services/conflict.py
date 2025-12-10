"""Conflict detection for session creation.

Pre-creation warnings to prevent failures and improve UX.
"""

from dataclasses import dataclass
from enum import Enum

from ..models.session import Session, SessionType


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""

    INFO = "info"  # FYI, no action needed
    WARNING = "warning"  # Proceed with caution
    ERROR = "error"  # Cannot proceed


@dataclass
class SessionConflict:
    """A detected conflict before session creation."""

    type: str
    severity: ConflictSeverity
    message: str
    suggestion: str | None = None


def detect_conflicts(
    name: str,
    session_type: SessionType,
    existing: list[Session],
) -> list[SessionConflict]:
    """Detect potential conflicts before session creation.

    Args:
        name: Proposed session name
        session_type: Type of session to create
        existing: List of existing sessions

    Returns:
        List of detected conflicts (may be empty)
    """
    conflicts = []

    # Name collision (warning - tmux allows duplicates but confusing)
    if any(s.name == name for s in existing):
        conflicts.append(
            SessionConflict(
                type="name_collision",
                severity=ConflictSeverity.WARNING,
                message=f"'{name}' already exists",
                suggestion="consider a unique name",
            )
        )

    return conflicts


def has_blocking_conflict(conflicts: list[SessionConflict]) -> bool:
    """Check if any conflict prevents creation."""
    return any(c.severity == ConflictSeverity.ERROR for c in conflicts)


def get_conflict_summary(conflicts: list[SessionConflict]) -> str | None:
    """Get a single-line summary of conflicts for display.

    Returns:
        Summary string or None if no conflicts
    """
    if not conflicts:
        return None

    # Prioritize: error > warning > info
    for severity in (ConflictSeverity.ERROR, ConflictSeverity.WARNING, ConflictSeverity.INFO):
        for c in conflicts:
            if c.severity == severity:
                return c.message

    return None
