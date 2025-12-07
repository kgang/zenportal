"""Unified git operations for zen-portal.

Consolidates git subprocess calls from context_parser.py and session_info.py
into a single service for consistency and maintainability.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitInfo:
    """Git repository information."""

    branch: str
    commit: str  # Short commit hash
    dirty: bool  # Has uncommitted changes

    @property
    def display(self) -> str:
        """Format as 'branch* commit' for display."""
        dirty_marker = "*" if self.dirty else ""
        commit_short = self.commit[:7] if self.commit else ""
        return f"{self.branch}{dirty_marker} {commit_short}".strip()


class GitService:
    """Centralized git operations for zen-portal.

    All methods are static and accept a working directory.
    Operations fail gracefully, returning None or empty strings.
    """

    TIMEOUT = 5  # seconds for git commands

    @staticmethod
    def get_branch(cwd: Path) -> str | None:
        """Get current git branch name.

        Args:
            cwd: Working directory (must be in a git repo)

        Returns:
            Branch name or None if not a git repo
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def get_commit(cwd: Path, short: bool = True) -> str | None:
        """Get current commit hash.

        Args:
            cwd: Working directory
            short: If True, return abbreviated hash (7 chars)

        Returns:
            Commit hash or None if not a git repo
        """
        cmd = ["git", "rev-parse"]
        if short:
            cmd.append("--short")
        cmd.append("HEAD")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def is_dirty(cwd: Path) -> bool:
        """Check if working directory has uncommitted changes.

        Args:
            cwd: Working directory

        Returns:
            True if there are uncommitted changes, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode == 0:
                return bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, OSError):
            pass
        return False

    @staticmethod
    def get_status(cwd: Path, limit: int = 20) -> str | None:
        """Get git status --short output.

        Args:
            cwd: Working directory
            limit: Maximum number of lines to return

        Returns:
            Status output (truncated) or None if not a git repo
        """
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode == 0:
                status = result.stdout.strip()
                if not status:
                    return ""
                lines = status.split("\n")[:limit]
                if len(lines) == limit:
                    lines.append("...")
                return "\n".join(lines)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def get_log(cwd: Path, count: int = 5) -> str | None:
        """Get recent git commits in oneline format.

        Args:
            cwd: Working directory
            count: Number of commits to return

        Returns:
            Log output or None if not a git repo
        """
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", f"-{count}"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def get_repo_name(cwd: Path) -> str | None:
        """Get repository name from remote origin URL.

        Handles both HTTPS and SSH URL formats:
        - https://github.com/user/repo.git
        - git@github.com:user/repo.git

        Args:
            cwd: Working directory

        Returns:
            Repository name or None if no remote origin
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            if result.returncode != 0:
                return None

            url = result.stdout.strip()
            # Extract repo name from URL (handles both HTTPS and SSH)
            name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name or None
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    @staticmethod
    def get_info(cwd: Path) -> GitInfo | None:
        """Get comprehensive git info for a directory.

        Combines branch, commit, and dirty state into a single object.

        Args:
            cwd: Working directory

        Returns:
            GitInfo object or None if not a git repo
        """
        branch = GitService.get_branch(cwd)
        if branch is None:
            return None

        commit = GitService.get_commit(cwd, short=True) or ""
        dirty = GitService.is_dirty(cwd)

        return GitInfo(branch=branch, commit=commit, dirty=dirty)

    @staticmethod
    def is_git_repo(cwd: Path) -> bool:
        """Check if directory is inside a git repository.

        Args:
            cwd: Directory to check

        Returns:
            True if inside a git repo, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=GitService.TIMEOUT,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
