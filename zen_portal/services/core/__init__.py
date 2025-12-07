"""Core services for zen-portal.

Extracted managers from SessionManager for better separation of concerns:
- WorktreeManager: Git worktree lifecycle
- TokenManager: Claude token statistics
- StateRefresher: Session state polling
- detection: Pure state detection function
"""

from .worktree_manager import WorktreeManager
from .token_manager import TokenManager
from .state_refresher import StateRefresher
from .detection import detect_session_state, DetectionResult, DetectionConfidence

__all__ = [
    "WorktreeManager",
    "TokenManager",
    "StateRefresher",
    "detect_session_state",
    "DetectionResult",
    "DetectionConfidence",
]
