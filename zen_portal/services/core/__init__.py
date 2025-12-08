"""Core services for zen-portal.

Extracted managers from SessionManager for better separation of concerns:
- TokenManager: Claude token statistics
- StateRefresher: Session state polling
- detection: Pure state detection function

Note: WorktreeManager was consolidated into WorktreeService (Phase 2)
"""

from .token_manager import TokenManager
from .state_refresher import StateRefresher
from .detection import detect_session_state, DetectionResult, DetectionConfidence

__all__ = [
    "TokenManager",
    "StateRefresher",
    "detect_session_state",
    "DetectionResult",
    "DetectionConfidence",
]
