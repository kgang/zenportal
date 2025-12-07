"""State detection: Pure function for detecting session state.

Separates detection logic from polling/refresh orchestration.
"""

from dataclasses import dataclass
from enum import Enum

from ..tmux import TmuxService
from ...models.session import SessionState


class DetectionConfidence(Enum):
    """Confidence level of state detection."""

    LOW = "low"  # Single check, might change
    MEDIUM = "medium"  # Consistent over short period
    HIGH = "high"  # Stable state confirmed


@dataclass
class DetectionResult:
    """Result of a state detection pass."""

    state: SessionState
    confidence: DetectionConfidence
    exit_code: int | None = None
    error_message: str | None = None


def detect_session_state(
    tmux: TmuxService,
    tmux_name: str,
) -> DetectionResult:
    """Detect session state from tmux.

    Pure function - no side effects, just facts about the current state.

    Args:
        tmux: Tmux service for querying session state
        tmux_name: Name of the tmux session

    Returns:
        DetectionResult with state, confidence, and optional details
    """
    # Session doesn't exist at all
    if not tmux.session_exists(tmux_name):
        return DetectionResult(
            state=SessionState.COMPLETED,
            confidence=DetectionConfidence.HIGH,
        )

    # Session exists but pane is dead (process exited)
    if tmux.is_pane_dead(tmux_name):
        exit_code = tmux.get_pane_exit_status(tmux_name)
        if exit_code is not None and exit_code != 0:
            return DetectionResult(
                state=SessionState.FAILED,
                confidence=DetectionConfidence.HIGH,
                exit_code=exit_code,
                error_message=f"Process exited with code {exit_code}",
            )
        return DetectionResult(
            state=SessionState.COMPLETED,
            confidence=DetectionConfidence.HIGH,
            exit_code=exit_code,
        )

    # Session exists and pane is alive
    return DetectionResult(
        state=SessionState.RUNNING,
        confidence=DetectionConfidence.MEDIUM,
    )
