"""Tests for state persistence dataclasses and SessionManager state functionality."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from zen_portal.services.state import (
    PortalState,
    SessionRecord,
)
from zen_portal.services.session_manager import SessionManager
from zen_portal.services.tmux import TmuxService, TmuxResult
from zen_portal.services.config import ConfigManager


class TestSessionRecord:
    """Tests for SessionRecord dataclass."""

    def test_to_dict_minimal(self):
        """to_dict includes required fields."""
        record = SessionRecord(
            id="abc123",
            name="test-session",
            session_type="claude",
            state="growing",
            created_at="2025-01-01T00:00:00",
        )
        d = record.to_dict()
        assert d["id"] == "abc123"
        assert d["name"] == "test-session"
        assert d["session_type"] == "claude"
        assert d["state"] == "growing"

    def test_to_dict_omits_none(self):
        """to_dict omits None values."""
        record = SessionRecord(
            id="abc123",
            name="test",
            session_type="shell",
            state="bloomed",
            created_at="2025-01-01T00:00:00",
            worktree_path=None,
        )
        d = record.to_dict()
        assert "worktree_path" not in d

    def test_from_dict_minimal(self):
        """from_dict handles minimal data."""
        data = {
            "id": "abc123",
            "name": "test",
        }
        record = SessionRecord.from_dict(data)
        assert record.id == "abc123"
        assert record.name == "test"
        assert record.session_type == "ai"  # default
        assert record.provider == "claude"  # default provider

    def test_from_dict_full(self):
        """from_dict handles full data."""
        data = {
            "id": "abc123",
            "name": "test",
            "session_type": "shell",
            "state": "paused",
            "created_at": "2025-01-01T00:00:00",
            "ended_at": "2025-01-01T01:00:00",
            "worktree_path": "/path/to/worktree",
            "claude_session_id": "claude-123",
        }
        record = SessionRecord.from_dict(data)
        assert record.session_type == "shell"
        assert record.state == "paused"
        assert record.worktree_path == "/path/to/worktree"


class TestPortalState:
    """Tests for PortalState dataclass."""

    def test_to_dict(self):
        """to_dict includes version and sessions."""
        record = SessionRecord(
            id="abc",
            name="test",
            session_type="claude",
            state="growing",
            created_at="2025-01-01T00:00:00",
        )
        state = PortalState(sessions=[record])
        d = state.to_dict()
        assert d["version"] == 1
        assert len(d["sessions"]) == 1
        assert "last_updated" in d

    def test_from_dict(self):
        """from_dict reconstructs state."""
        data = {
            "version": 1,
            "last_updated": "2025-01-01T00:00:00",
            "sessions": [
                {"id": "abc", "name": "test"},
            ],
        }
        state = PortalState.from_dict(data)
        assert state.version == 1
        assert len(state.sessions) == 1
        assert state.sessions[0].id == "abc"


class TestSessionManagerState:
    """Tests for SessionManager state persistence."""

    @pytest.fixture
    def state_dir(self, tmp_path: Path) -> Path:
        """Create a temporary state directory."""
        return tmp_path / ".zen_portal"

    @pytest.fixture
    def mock_tmux(self) -> MagicMock:
        """Create a mock TmuxService."""
        tmux = MagicMock(spec=TmuxService)
        tmux.create_session.return_value = TmuxResult(success=True)
        tmux.session_exists.return_value = False
        tmux.is_pane_dead.return_value = False
        return tmux

    @pytest.fixture
    def config_manager(self, tmp_path: Path) -> ConfigManager:
        """Create a ConfigManager with temp directory."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        return ConfigManager(config_dir=config_dir)

    @pytest.fixture
    def manager(self, mock_tmux: MagicMock, config_manager: ConfigManager, state_dir: Path, tmp_path: Path) -> SessionManager:
        """Create a SessionManager with temp state directory."""
        return SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )

    def test_load_state_empty(self, manager: SessionManager):
        """SessionManager loads empty state when no file exists."""
        # Manager loads state on init, so just check it's empty
        assert len(manager.sessions) == 0

    def test_save_and_load_state(self, manager: SessionManager, state_dir: Path, mock_tmux: MagicMock, config_manager: ConfigManager, tmp_path: Path):
        """save_state persists and reload restores."""
        # Create a session
        session = manager.create_session(name="test-session")

        assert manager.save_state()
        assert (state_dir / "state.json").exists()

        # Session will be restored if tmux session exists
        mock_tmux.session_exists.return_value = True

        # Create a new manager to test loading
        manager2 = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )
        assert len(manager2.sessions) == 1
        loaded_session = manager2.sessions[0]
        assert loaded_session.name == "test-session"

    def test_save_state_atomic(self, manager: SessionManager, state_dir: Path):
        """save_state uses atomic writes (no .tmp file left behind)."""
        manager.save_state()

        # No temp file should remain
        assert not (state_dir / "state.json.tmp").exists()

    def test_load_state_corrupted(self, state_dir: Path, mock_tmux: MagicMock, config_manager: ConfigManager, tmp_path: Path):
        """SessionManager handles corrupted JSON gracefully."""
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "state.json").write_text("not valid json {{{")

        # Should load without error, with empty state
        manager = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )
        assert len(manager.sessions) == 0

    def test_append_history(self, manager: SessionManager, state_dir: Path):
        """Creating a session appends to history."""
        manager.create_session(name="test")

        history_dir = state_dir / "history"
        assert history_dir.exists()

        today = datetime.now().strftime("%Y-%m-%d")
        history_file = history_dir / f"{today}.jsonl"
        assert history_file.exists()

        # Check content
        lines = history_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["event"] == "created"
        assert entry["session"]["name"] == "test"
