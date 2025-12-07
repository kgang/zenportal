"""WorktreeManager: Git worktree lifecycle for sessions.

Extracted from SessionManager to provide focused worktree operations.
"""

from pathlib import Path

from ..worktree import WorktreeService, WorktreeResult
from ..config import WorktreeSettings
from ...models.session import Session, SessionFeatures, SessionState


class WorktreeManager:
    """Manages git worktree lifecycle for zen-portal sessions.

    Provides:
    - Worktree creation during session setup
    - Worktree navigation for paused sessions
    - Worktree cleanup on session kill/clean
    """

    def __init__(self, worktree_service: WorktreeService | None = None):
        self._worktree = worktree_service

    @property
    def available(self) -> bool:
        """Check if worktree operations are available."""
        return self._worktree is not None

    def setup_for_session(
        self,
        session: Session,
        features: SessionFeatures | None,
        worktree_settings: WorktreeSettings | None,
    ) -> Path:
        """Set up worktree for session if enabled.

        Args:
            session: Session to set up worktree for
            features: Session-level feature overrides
            worktree_settings: Resolved worktree settings

        Returns:
            Working directory path (worktree path if created, else original)
        """
        working_dir = session.resolved_working_dir

        use_worktree = self._should_use_worktree(features, worktree_settings)
        if not use_worktree:
            return working_dir

        # Create a WorktreeService for the session's working directory
        # This ensures worktrees are created from the correct source repo
        base_dir = None
        if worktree_settings and worktree_settings.base_dir:
            base_dir = worktree_settings.base_dir

        worktree_service = WorktreeService(source_repo=working_dir, base_dir=base_dir)
        if not worktree_service.is_git_repo():
            return working_dir

        # Determine branch and from_branch
        branch_name = features.worktree_branch if features else None
        from_branch = "main"
        if worktree_settings and worktree_settings.default_from_branch:
            from_branch = worktree_settings.default_from_branch

        env_files = None
        if worktree_settings and worktree_settings.env_files:
            env_files = worktree_settings.env_files

        # Create worktree
        worktree_name = f"{session.name}-{session.id[:8]}"
        wt_result = worktree_service.create_worktree(
            name=worktree_name,
            branch=branch_name,
            from_branch=from_branch,
            env_files=env_files,
        )

        if wt_result.success and wt_result.path:
            session.worktree_path = wt_result.path
            session.worktree_branch = wt_result.branch
            session.worktree_source_repo = working_dir  # Store source for cleanup
            session.resolved_working_dir = wt_result.path
            return wt_result.path

        return working_dir

    def _should_use_worktree(
        self,
        features: SessionFeatures | None,
        worktree_settings: WorktreeSettings | None,
    ) -> bool:
        """Determine if we should create a worktree for this session."""
        if features and features.use_worktree is not None:
            return features.use_worktree
        if worktree_settings:
            return worktree_settings.enabled
        return False

    def cleanup(self, session: Session, force: bool = True) -> bool:
        """Remove worktree for a session.

        Args:
            session: Session whose worktree should be removed
            force: Force removal even with uncommitted changes

        Returns:
            True if worktree was removed or didn't exist
        """
        if not session.worktree_path:
            return True

        # Use the source repo stored during worktree creation
        source_repo = session.worktree_source_repo
        if not source_repo:
            return True

        worktree_service = WorktreeService(source_repo=source_repo)
        if not worktree_service.is_git_repo():
            return True

        result = worktree_service.remove_worktree(session.worktree_path, force=force)
        return result.success

    def can_navigate(self, session: Session) -> bool:
        """Check if we can navigate to a session's worktree.

        Args:
            session: Session to check

        Returns:
            True if session is paused with existing worktree
        """
        if session.state != SessionState.PAUSED:
            return False
        if not session.worktree_path:
            return False
        return session.worktree_path.exists()

    def get_worktree_path(self, session: Session) -> Path | None:
        """Get the worktree path for a session if it exists.

        Args:
            session: Session to get worktree for

        Returns:
            Worktree path if exists, None otherwise
        """
        if session.worktree_path and session.worktree_path.exists():
            return session.worktree_path
        return None
