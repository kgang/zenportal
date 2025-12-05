"""WorktreeService: Git worktree operations for isolated session workspaces."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


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

    Each session can get its own worktree, enabling parallel work
    on different branches without conflicts.
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
