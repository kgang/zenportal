"""Shared test fixtures for Zen Portal."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from zen_portal.services.tmux import TmuxService, TmuxResult
from zen_portal.services.session_manager import SessionManager
from zen_portal.services.config import ConfigManager
from zen_portal.services.worktree import WorktreeService, WorktreeResult
from zen_portal.services.state import StateService


@pytest.fixture
def mock_tmux() -> MagicMock:
    """Create a mock TmuxService."""
    tmux = MagicMock(spec=TmuxService)
    tmux.create_session.return_value = TmuxResult(success=True)
    tmux.session_exists.return_value = True
    tmux.is_pane_dead.return_value = False
    tmux.capture_pane.return_value = TmuxResult(success=True, output="Test output\n")
    tmux.kill_session.return_value = TmuxResult(success=True)
    tmux.clear_history.return_value = TmuxResult(success=True)
    return tmux


@pytest.fixture
def mock_worktree(tmp_path: Path) -> MagicMock:
    """Create a mock WorktreeService."""
    worktree = MagicMock(spec=WorktreeService)
    worktree_path = tmp_path / "worktrees" / "test-worktree"
    worktree.create_worktree.return_value = WorktreeResult(
        success=True, path=worktree_path, branch="test-branch"
    )
    worktree.remove_worktree.return_value = WorktreeResult(success=True)
    return worktree


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    """Create a ConfigManager with temp directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return ConfigManager(config_dir=config_dir)


@pytest.fixture
def state_service(tmp_path: Path) -> StateService:
    """Create a StateService with temp directory (fresh for each test)."""
    state_dir = tmp_path / ".zen_portal"
    return StateService(base_dir=state_dir)


@pytest.fixture
def session_manager(
    mock_tmux: MagicMock,
    config_manager: ConfigManager,
    state_service: StateService,
    tmp_path: Path,
) -> SessionManager:
    """Create a SessionManager with mock tmux, config, and fresh state."""
    return SessionManager(
        tmux=mock_tmux,
        config_manager=config_manager,
        state_service=state_service,
        working_dir=tmp_path,
    )


@pytest.fixture
def session_manager_with_worktree(
    mock_tmux: MagicMock,
    mock_worktree: MagicMock,
    config_manager: ConfigManager,
    state_service: StateService,
    tmp_path: Path,
) -> SessionManager:
    """Create a SessionManager with mock tmux, worktree, config, and fresh state."""
    return SessionManager(
        tmux=mock_tmux,
        config_manager=config_manager,
        worktree_service=mock_worktree,
        state_service=state_service,
        working_dir=tmp_path,
    )


@pytest.fixture
def working_dir(tmp_path: Path) -> Path:
    """Create a temporary working directory."""
    work_dir = tmp_path / "zen-work"
    work_dir.mkdir()
    return work_dir
