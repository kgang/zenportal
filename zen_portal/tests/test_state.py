"""Tests for StateService."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from zen_portal.services.state import (
    StateService,
    PortalState,
    SessionRecord,
)


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
        assert record.session_type == "claude"  # default

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


class TestStateService:
    """Tests for StateService."""

    @pytest.fixture
    def state_dir(self, tmp_path: Path) -> Path:
        """Create a temporary state directory."""
        return tmp_path / ".zen_portal"

    @pytest.fixture
    def service(self, state_dir: Path) -> StateService:
        """Create a StateService with temp directory."""
        return StateService(base_dir=state_dir)

    def test_load_state_empty(self, service: StateService):
        """load_state returns empty state when no file exists."""
        state = service.load_state()
        assert state.version == 1
        assert state.sessions == []

    def test_save_and_load_state(self, service: StateService, state_dir: Path):
        """save_state persists and load_state restores."""
        record = SessionRecord(
            id="test-id",
            name="test-session",
            session_type="claude",
            state="growing",
            created_at=datetime.now().isoformat(),
        )
        state = PortalState(sessions=[record])

        assert service.save_state(state)
        assert (state_dir / "state.json").exists()

        loaded = service.load_state()
        assert len(loaded.sessions) == 1
        assert loaded.sessions[0].id == "test-id"

    def test_save_state_atomic(self, service: StateService, state_dir: Path):
        """save_state uses atomic writes (no .tmp file left behind)."""
        state = PortalState(sessions=[])
        service.save_state(state)

        # No temp file should remain
        assert not (state_dir / "state.json.tmp").exists()

    def test_load_state_corrupted(self, service: StateService, state_dir: Path):
        """load_state handles corrupted JSON gracefully."""
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "state.json").write_text("not valid json {{{")

        state = service.load_state()
        assert state.sessions == []  # Empty state on corruption

    def test_append_history(self, service: StateService, state_dir: Path):
        """append_history creates daily JSONL files."""
        record = SessionRecord(
            id="test-id",
            name="test",
            session_type="claude",
            state="growing",
            created_at=datetime.now().isoformat(),
        )
        service.append_history(record, "created")

        history_dir = state_dir / "history"
        assert history_dir.exists()

        today = datetime.now().strftime("%Y-%m-%d")
        history_file = history_dir / f"{today}.jsonl"
        assert history_file.exists()

        # Check content
        lines = history_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "created"
        assert entry["session"]["id"] == "test-id"

    def test_get_history_days(self, service: StateService, state_dir: Path):
        """get_history_days returns sorted list of days."""
        history_dir = state_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        # Create some history files
        (history_dir / "2025-01-01.jsonl").write_text("{}\n")
        (history_dir / "2025-01-03.jsonl").write_text("{}\n")
        (history_dir / "2025-01-02.jsonl").write_text("{}\n")

        days = service.get_history_days()
        assert days == ["2025-01-03", "2025-01-02", "2025-01-01"]

    def test_clear_state(self, service: StateService, state_dir: Path):
        """clear_state removes state file."""
        state = PortalState(sessions=[])
        service.save_state(state)
        assert (state_dir / "state.json").exists()

        assert service.clear_state()
        assert not (state_dir / "state.json").exists()

    def test_prune_history(self, service: StateService, state_dir: Path):
        """prune_history removes old history files."""
        history_dir = state_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        # Create old and new history files
        (history_dir / "2020-01-01.jsonl").write_text("{}\n")  # Old
        (history_dir / "2020-01-15.jsonl").write_text("{}\n")  # Old
        today = datetime.now().strftime("%Y-%m-%d")
        (history_dir / f"{today}.jsonl").write_text("{}\n")  # New

        pruned = service.prune_history(keep_days=30)
        assert pruned == 2

        # Today's file should remain
        assert (history_dir / f"{today}.jsonl").exists()
        assert not (history_dir / "2020-01-01.jsonl").exists()
