"""Tests for WorktreeService."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zen_portal.services.worktree import WorktreeInfo, WorktreeResult, WorktreeService


class TestWorktreeService:
    """Tests for WorktreeService."""

    @pytest.fixture
    def worktree(self, tmp_path: Path) -> WorktreeService:
        """Create a WorktreeService instance."""
        return WorktreeService(source_repo=tmp_path, base_dir=tmp_path / "worktrees")

    def test_init_default_base_dir(self, tmp_path: Path):
        """Default base_dir is ~/.zen-portal/worktrees."""
        service = WorktreeService(source_repo=tmp_path)
        assert service.base_dir == Path.home() / ".zen-portal" / "worktrees"

    def test_init_custom_base_dir(self, tmp_path: Path):
        """Custom base_dir is respected."""
        custom_dir = tmp_path / "custom"
        service = WorktreeService(source_repo=tmp_path, base_dir=custom_dir)
        assert service.base_dir == custom_dir

    def test_is_git_repo_true(self, worktree: WorktreeService):
        """is_git_repo returns True for valid repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=".git", stderr="")
            assert worktree.is_git_repo() is True

    def test_is_git_repo_false(self, worktree: WorktreeService):
        """is_git_repo returns False for non-repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="not a git repository"
            )
            assert worktree.is_git_repo() is False

    def test_create_worktree_not_git_repo(self, worktree: WorktreeService):
        """create_worktree fails if not a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="not a git repository"
            )
            result = worktree.create_worktree("test-worktree")
            assert result.success is False
            assert "not a git repository" in result.error.lower()

    def test_create_worktree_path_exists(self, worktree: WorktreeService, tmp_path: Path):
        """create_worktree fails if path already exists."""
        # Create the worktree directory first
        worktrees_dir = tmp_path / "worktrees"
        worktrees_dir.mkdir(parents=True)
        (worktrees_dir / "test-worktree").mkdir()

        with patch("subprocess.run") as mock_run:
            # is_git_repo check
            mock_run.return_value = MagicMock(returncode=0, stdout=".git", stderr="")
            result = worktree.create_worktree("test-worktree")
            assert result.success is False
            assert "already exists" in result.error.lower()

    def test_create_worktree_success(self, worktree: WorktreeService, tmp_path: Path):
        """create_worktree succeeds with valid repo and name."""
        with patch("subprocess.run") as mock_run:
            # First call: is_git_repo check
            # Second call: worktree add
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = worktree.create_worktree("test-worktree")
            assert result.success is True
            assert result.path == tmp_path / "worktrees" / "test-worktree"
            assert result.branch == "test-worktree"  # branch defaults to name

    def test_create_worktree_with_branch(self, worktree: WorktreeService, tmp_path: Path):
        """create_worktree uses specified branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = worktree.create_worktree("test-worktree", branch="my-feature")
            assert result.success is True
            assert result.branch == "my-feature"

    def test_create_worktree_with_env_symlinks(
        self, worktree: WorktreeService, tmp_path: Path
    ):
        """create_worktree creates symlinks for env files."""
        # Create source env files
        (tmp_path / ".env").write_text("SECRET=value")
        (tmp_path / ".env.secrets").write_text("MORE_SECRETS=here")

        worktree_path = tmp_path / "worktrees" / "test-worktree"

        def git_side_effect(*args, **kwargs):
            # Simulate git worktree add creating the directory
            if "worktree" in args[0] and "add" in args[0]:
                worktree_path.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=git_side_effect):
            result = worktree.create_worktree(
                "test-worktree",
                env_files=[".env", ".env.secrets"],
            )
            assert result.success is True

            # Verify symlinks were created
            env_link = worktree_path / ".env"
            secrets_link = worktree_path / ".env.secrets"

            assert env_link.is_symlink()
            assert secrets_link.is_symlink()
            assert env_link.resolve() == tmp_path / ".env"
            assert secrets_link.resolve() == tmp_path / ".env.secrets"

    def test_create_worktree_env_symlinks_skip_missing(
        self, worktree: WorktreeService, tmp_path: Path
    ):
        """create_worktree skips env files that don't exist in source."""
        # Only create one env file
        (tmp_path / ".env").write_text("SECRET=value")
        # .env.secrets does NOT exist

        worktree_path = tmp_path / "worktrees" / "test-worktree"

        def git_side_effect(*args, **kwargs):
            if "worktree" in args[0] and "add" in args[0]:
                worktree_path.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=git_side_effect):
            result = worktree.create_worktree(
                "test-worktree",
                env_files=[".env", ".env.secrets"],
            )
            assert result.success is True

            # Only existing source file gets symlinked
            assert (worktree_path / ".env").is_symlink()
            assert not (worktree_path / ".env.secrets").exists()

    def test_create_worktree_env_symlinks_nested_path(
        self, worktree: WorktreeService, tmp_path: Path
    ):
        """create_worktree creates parent dirs for nested env files."""
        # Create nested env file in source
        (tmp_path / "apps" / "api").mkdir(parents=True)
        (tmp_path / "apps" / "api" / ".env").write_text("API_SECRET=value")

        worktree_path = tmp_path / "worktrees" / "test-worktree"

        def git_side_effect(*args, **kwargs):
            if "worktree" in args[0] and "add" in args[0]:
                worktree_path.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=git_side_effect):
            result = worktree.create_worktree(
                "test-worktree",
                env_files=["apps/api/.env"],
            )
            assert result.success is True

            # Nested symlink created with parent dirs
            nested_link = worktree_path / "apps" / "api" / ".env"
            assert nested_link.is_symlink()
            assert nested_link.resolve() == tmp_path / "apps" / "api" / ".env"

    def test_create_worktree_branch_exists(self, worktree: WorktreeService, tmp_path: Path):
        """create_worktree fails if branch already exists."""
        with patch("subprocess.run") as mock_run:
            # First call: is_git_repo check succeeds
            # Second call: worktree add fails
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=".git", stderr=""),
                MagicMock(
                    returncode=128,
                    stdout="",
                    stderr="fatal: a branch named 'my-feature' already exists",
                ),
            ]
            result = worktree.create_worktree("test-worktree", branch="my-feature")
            assert result.success is False
            assert "already exists" in result.error.lower()

    def test_create_worktree_branch_checked_out(
        self, worktree: WorktreeService, tmp_path: Path
    ):
        """create_worktree fails if branch is checked out elsewhere."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=".git", stderr=""),
                MagicMock(
                    returncode=128,
                    stdout="",
                    stderr="fatal: 'my-feature' is already checked out at '/some/path'",
                ),
            ]
            result = worktree.create_worktree("test-worktree", branch="my-feature")
            assert result.success is False
            assert "already checked out" in result.error.lower()

    def test_remove_worktree_success(self, worktree: WorktreeService, tmp_path: Path):
        """remove_worktree succeeds."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = worktree.remove_worktree(tmp_path / "some-worktree")
            assert result.success is True

    def test_remove_worktree_force(self, worktree: WorktreeService, tmp_path: Path):
        """remove_worktree with force flag."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = worktree.remove_worktree(tmp_path / "some-worktree", force=True)
            assert result.success is True
            # Verify --force was passed
            call_args = mock_run.call_args[0][0]
            assert "--force" in call_args

    def test_remove_worktree_failure(self, worktree: WorktreeService, tmp_path: Path):
        """remove_worktree fails with uncommitted changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="has uncommitted changes"
            )
            result = worktree.remove_worktree(tmp_path / "dirty-worktree")
            assert result.success is False
            assert "uncommitted" in result.error.lower()

    def test_list_worktrees_success(self, worktree: WorktreeService, tmp_path: Path):
        """list_worktrees returns worktree info."""
        porcelain_output = """worktree /path/to/repo
HEAD abc123
branch refs/heads/main

worktree /path/to/repo/worktrees/feature
HEAD def456
branch refs/heads/feature
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=porcelain_output, stderr=""
            )
            worktrees = worktree.list_worktrees()
            assert len(worktrees) == 2
            assert worktrees[0].path == Path("/path/to/repo")
            assert worktrees[0].branch == "main"
            assert worktrees[1].branch == "feature"

    def test_list_worktrees_empty(self, worktree: WorktreeService):
        """list_worktrees returns empty list on failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            worktrees = worktree.list_worktrees()
            assert worktrees == []

    def test_list_worktrees_detached(self, worktree: WorktreeService):
        """list_worktrees handles detached HEAD."""
        porcelain_output = """worktree /path/to/repo
HEAD abc123
detached
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=porcelain_output, stderr=""
            )
            worktrees = worktree.list_worktrees()
            assert len(worktrees) == 1
            assert worktrees[0].branch == "(detached)"

    def test_worktree_exists_true(self, worktree: WorktreeService, tmp_path: Path):
        """worktree_exists returns True when worktree is in list."""
        porcelain_output = f"""worktree {tmp_path / "worktrees" / "test"}
HEAD abc123
branch refs/heads/test
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=porcelain_output, stderr=""
            )
            assert worktree.worktree_exists(tmp_path / "worktrees" / "test") is True

    def test_worktree_exists_false(self, worktree: WorktreeService, tmp_path: Path):
        """worktree_exists returns False when worktree not in list."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            assert worktree.worktree_exists(tmp_path / "nonexistent") is False

    def test_get_worktree_branch(self, worktree: WorktreeService, tmp_path: Path):
        """get_worktree_branch returns branch name."""
        test_path = tmp_path / "worktrees" / "test"
        porcelain_output = f"""worktree {test_path}
HEAD abc123
branch refs/heads/my-branch
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=porcelain_output, stderr=""
            )
            assert worktree.get_worktree_branch(test_path) == "my-branch"

    def test_get_worktree_branch_not_found(self, worktree: WorktreeService, tmp_path: Path):
        """get_worktree_branch returns None when not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            assert worktree.get_worktree_branch(tmp_path / "nonexistent") is None

    def test_prune_stale_success(self, worktree: WorktreeService):
        """prune_stale succeeds."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = worktree.prune_stale()
            assert result.success is True

    def test_prune_stale_failure(self, worktree: WorktreeService):
        """prune_stale handles errors."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="some error"
            )
            result = worktree.prune_stale()
            assert result.success is False

    def test_git_timeout(self, worktree: WorktreeService):
        """Git commands handle timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=30)
            result = worktree.create_worktree("test")
            # is_git_repo returns False on timeout
            assert result.success is False

    def test_git_not_found(self, worktree: WorktreeService):
        """Git commands handle missing git."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = worktree.create_worktree("test")
            assert result.success is False


class TestWorktreeResult:
    """Tests for WorktreeResult dataclass."""

    def test_default_values(self):
        """WorktreeResult has sensible defaults."""
        result = WorktreeResult(success=True)
        assert result.path is None
        assert result.branch == ""
        assert result.error == ""

    def test_with_all_values(self, tmp_path: Path):
        """WorktreeResult accepts all values."""
        result = WorktreeResult(
            success=True,
            path=tmp_path,
            branch="feature",
            error="",
        )
        assert result.success is True
        assert result.path == tmp_path
        assert result.branch == "feature"


class TestWorktreeInfo:
    """Tests for WorktreeInfo dataclass."""

    def test_default_values(self, tmp_path: Path):
        """WorktreeInfo has sensible defaults."""
        info = WorktreeInfo(path=tmp_path, branch="main", commit="abc123")
        assert info.is_bare is False

    def test_bare_worktree(self, tmp_path: Path):
        """WorktreeInfo tracks bare repos."""
        info = WorktreeInfo(path=tmp_path, branch="", commit="abc123", is_bare=True)
        assert info.is_bare is True
