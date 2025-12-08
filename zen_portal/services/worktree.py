"""WorktreeService: Git worktree operations for isolated session workspaces.

Consolidated service providing both low-level git operations and high-level
session integration. Extracted from SessionManager Phase 1, consolidated
from WorktreeManager Phase 2.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorktreeResult:
    """Result of a worktree operation."""

    success: bool
    path: Path | None = None
    branch: str = ""
    error: str = ""


@dataclass
class WorktreeInfo:
    """Information about an existing worktree."""

    path: Path
    branch: str
    commit: str
    is_bare: bool = False


class WorktreeService:
    """Manages git worktrees for session isolation.

    Provides both low-level git worktree operations and high-level
    session lifecycle integration. Each session can get its own worktree,
    enabling parallel work on different branches without conflicts.

    Consolidated from WorktreeService + WorktreeManager (Phase 2).
    """

    DEFAULT_TIMEOUT = 30

    def __init__(self, source_repo: Path, base_dir: Path | None = None):
        """Initialize worktree service.

        Args:
            source_repo: Path to the git repository to create worktrees from
            base_dir: Directory where worktrees will be created
                     (default: ~/.zen-portal/worktrees)
        """
        self._source_repo = source_repo
        self._base_dir = base_dir or Path.home() / ".zen-portal" / "worktrees"

    @property
    def source_repo(self) -> Path:
        return self._source_repo

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    # =========================================================================
    # Low-level git operations
    # =========================================================================

    def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[bool, str, str]:
        """Run a git command.

        Returns:
            Tuple of (success, stdout, stderr)
        """
        cmd = ["git"] + args
        timeout = timeout or self.DEFAULT_TIMEOUT
        cwd = cwd or self._source_repo

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return False, "", "Operation timed out"
        except FileNotFoundError:
            return False, "", "git not found"
        except Exception as e:
            return False, "", str(e)

    def is_git_repo(self) -> bool:
        """Check if source_repo is a valid git repository."""
        success, _, _ = self._run_git(["rev-parse", "--git-dir"])
        return success

    def create_worktree(
        self,
        name: str,
        branch: str | None = None,
        from_branch: str = "main",
        env_files: list[str] | None = None,
    ) -> WorktreeResult:
        """Create a new worktree with a new branch.

        Args:
            name: Name for the worktree directory
            branch: Branch name to create. If None, uses worktree name as branch
            from_branch: Base branch to create the new branch from (default: main)
            env_files: Relative paths to symlink from source repo (e.g., [".env"])

        Returns:
            WorktreeResult with path and branch info on success
        """
        if not self.is_git_repo():
            return WorktreeResult(
                success=False,
                error=f"Not a git repository: {self._source_repo}",
            )

        # Ensure base directory exists
        self._base_dir.mkdir(parents=True, exist_ok=True)

        # Worktree path
        worktree_path = self._base_dir / name

        # Check if path already exists
        if worktree_path.exists():
            return WorktreeResult(
                success=False,
                error=f"Worktree path already exists: {worktree_path}",
            )

        # Determine branch name (use provided or default to worktree name)
        branch_name = branch if branch else name

        # Always create a new branch from from_branch
        # git worktree add <path> -b <new-branch> <start-point>
        args = ["worktree", "add", str(worktree_path), "-b", branch_name, from_branch]

        success, stdout, stderr = self._run_git(args)

        if success:
            # Create symlinks for env files
            if env_files:
                self._create_env_symlinks(worktree_path, env_files)

            return WorktreeResult(
                success=True,
                path=worktree_path,
                branch=branch_name,
            )
        else:
            # Parse common errors
            error = stderr
            if "already exists" in stderr.lower():
                error = f"Branch '{branch_name}' already exists"
            elif "is already checked out" in stderr.lower():
                error = f"Branch '{branch_name}' is already checked out in another worktree"

            return WorktreeResult(success=False, error=error)

    def _create_env_symlinks(
        self,
        worktree_path: Path,
        env_files: list[str],
    ) -> None:
        """Create symlinks for env files from source repo to worktree.

        Args:
            worktree_path: Path to the new worktree
            env_files: Relative paths to symlink (e.g., [".env", ".env.secrets"])
        """
        for file_path in env_files:
            source = self._source_repo / file_path
            target = worktree_path / file_path

            # Only symlink if source exists and target doesn't
            if source.is_file() and not target.exists():
                # Ensure parent directory exists
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(source)

    def remove_worktree(
        self,
        path: Path,
        force: bool = False,
    ) -> WorktreeResult:
        """Remove a worktree.

        Args:
            path: Path to the worktree to remove
            force: If True, remove even with uncommitted changes

        Returns:
            WorktreeResult indicating success/failure
        """
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(path))

        success, stdout, stderr = self._run_git(args)

        if success:
            return WorktreeResult(success=True, path=path)
        else:
            return WorktreeResult(success=False, error=stderr)

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all worktrees for the source repository.

        Returns:
            List of WorktreeInfo objects
        """
        success, stdout, stderr = self._run_git(["worktree", "list", "--porcelain"])

        if not success:
            return []

        worktrees = []
        current: dict = {}

        for line in stdout.split("\n"):
            if not line:
                if current and "path" in current:
                    worktrees.append(
                        WorktreeInfo(
                            path=Path(current["path"]),
                            branch=current.get("branch", ""),
                            commit=current.get("commit", ""),
                            is_bare=current.get("bare", False),
                        )
                    )
                current = {}
            elif line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["commit"] = line[5:]
            elif line.startswith("branch "):
                # Format: refs/heads/branch-name
                branch_ref = line[7:]
                if branch_ref.startswith("refs/heads/"):
                    current["branch"] = branch_ref[11:]
                else:
                    current["branch"] = branch_ref
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["branch"] = "(detached)"

        # Handle last entry
        if current and "path" in current:
            worktrees.append(
                WorktreeInfo(
                    path=Path(current["path"]),
                    branch=current.get("branch", ""),
                    commit=current.get("commit", ""),
                    is_bare=current.get("bare", False),
                )
            )

        return worktrees

    def worktree_exists(self, path: Path) -> bool:
        """Check if a worktree exists at the given path."""
        worktrees = self.list_worktrees()
        return any(wt.path == path for wt in worktrees)

    def get_worktree_branch(self, path: Path) -> str | None:
        """Get the branch name for a worktree path."""
        worktrees = self.list_worktrees()
        for wt in worktrees:
            if wt.path == path:
                return wt.branch
        return None

    def prune_stale(self) -> WorktreeResult:
        """Prune stale worktree references.

        This cleans up references to worktrees that were manually deleted.
        """
        success, stdout, stderr = self._run_git(["worktree", "prune"])

        if success:
            return WorktreeResult(success=True)
        else:
            return WorktreeResult(success=False, error=stderr)

    # =========================================================================
    # High-level session integration (merged from WorktreeManager)
    # =========================================================================

    def setup_for_session(
        self,
        session,  # Session type
        features,  # SessionFeatures | None
        worktree_settings,  # WorktreeSettings | None
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
        features,  # SessionFeatures | None
        worktree_settings,  # WorktreeSettings | None
    ) -> bool:
        """Determine if we should create a worktree for this session."""
        if features and features.use_worktree is not None:
            return features.use_worktree
        if worktree_settings:
            return worktree_settings.enabled
        return False

    def cleanup_session(self, session, force: bool = True) -> bool:
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

    def can_navigate_to_session(self, session) -> bool:
        """Check if we can navigate to a session's worktree.

        Args:
            session: Session to check

        Returns:
            True if session is paused with existing worktree
        """
        # Import here to avoid circular dependency
        from ..models.session import SessionState

        if session.state != SessionState.PAUSED:
            return False
        if not session.worktree_path:
            return False
        return session.worktree_path.exists()

    def get_session_worktree_path(self, session) -> Path | None:
        """Get the worktree path for a session if it exists.

        Args:
            session: Session to get worktree for

        Returns:
            Worktree path if exists, None otherwise
        """
        if session.worktree_path and session.worktree_path.exists():
            return session.worktree_path
        return None
