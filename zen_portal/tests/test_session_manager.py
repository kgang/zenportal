"""Tests for SessionManager."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from zen_portal.services.session_manager import SessionManager, SessionLimitError
from zen_portal.services.tmux import TmuxResult
from zen_portal.services.worktree import WorktreeResult
from zen_portal.models.session import SessionState, SessionFeatures


class TestSessionManager:
    """Tests for SessionManager."""

    def test_create_session_with_name(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Create a session with just a name."""
        session = session_manager.create_session("my-task")

        assert session.name == "my-task"
        assert session.prompt == ""
        assert session.state == SessionState.GROWING
        mock_tmux.create_session.assert_called_once()

    def test_create_session_with_prompt(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Create a session with name and prompt."""
        session = session_manager.create_session("fix-bug", "fix the auth bug")

        assert session.name == "fix-bug"
        assert session.prompt == "fix the auth bug"
        assert session.state == SessionState.GROWING

    def test_create_session_tmux_failure(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session state is WILTED when tmux fails."""
        mock_tmux.create_session.return_value = TmuxResult(
            success=False, error="tmux error"
        )

        session = session_manager.create_session("test")
        assert session.state == SessionState.WILTED

    def test_create_session_max_sessions(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Raise SessionLimitError when max sessions reached."""
        for i in range(SessionManager.MAX_SESSIONS):
            session_manager.create_session(f"session-{i}")

        with pytest.raises(SessionLimitError) as exc_info:
            session_manager.create_session("one-too-many")

        assert "Maximum sessions" in str(exc_info.value)

    def test_kill_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Kill a session (removes worktree)."""
        session = session_manager.create_session("test")

        result = session_manager.kill_session(session.id)

        assert result is True
        assert session.state == SessionState.KILLED
        assert session.ended_at is not None
        mock_tmux.kill_session.assert_called_once()

    def test_kill_nonexistent_session(self, session_manager: SessionManager):
        """Return False when killing nonexistent session."""
        result = session_manager.kill_session("nonexistent-id")
        assert result is False

    def test_get_output(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Get output from a session."""
        session = session_manager.create_session("test")

        output = session_manager.get_output(session.id)

        assert "Test output" in output
        mock_tmux.capture_pane.assert_called()

    def test_get_output_nonexistent(self, session_manager: SessionManager):
        """Return empty string for nonexistent session."""
        output = session_manager.get_output("nonexistent-id")
        assert output == ""

    def test_refresh_states_bloomed(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session becomes BLOOMED when tmux session ends."""
        session = session_manager.create_session("test")
        mock_tmux.session_exists.return_value = False

        session_manager.refresh_states()

        assert session.state == SessionState.BLOOMED
        assert session.ended_at is not None

    def test_refresh_states_still_growing(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session stays GROWING when tmux session exists."""
        session = session_manager.create_session("test")
        mock_tmux.session_exists.return_value = True

        session_manager.refresh_states()

        assert session.state == SessionState.GROWING

    def test_sessions_sorted_newest_first(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Sessions are returned sorted by creation time, newest first."""
        s1 = session_manager.create_session("first")
        s2 = session_manager.create_session("second")
        s3 = session_manager.create_session("third")

        sessions = session_manager.sessions

        assert sessions[0].id == s3.id
        assert sessions[1].id == s2.id
        assert sessions[2].id == s1.id

    def test_remove_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Remove a session entirely."""
        session = session_manager.create_session("test")

        result = session_manager.remove_session(session.id)

        assert result is True
        assert session_manager.get_session(session.id) is None

    def test_get_tmux_session_name(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Get the tmux session name for a session."""
        session = session_manager.create_session("test")

        tmux_name = session_manager.get_tmux_session_name(session.id)

        assert tmux_name is not None
        assert tmux_name.startswith("zen-")
        assert session.id[:8] in tmux_name

    def test_session_claude_session_id_empty_initially(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """New sessions start without claude_session_id (discovered later)."""
        session = session_manager.create_session("test")

        # Session ID is empty initially - Claude Code generates it
        # and we discover it when needed for revival
        assert session.claude_session_id == ""

    def test_revive_bloomed_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Revive a bloomed session."""
        session = session_manager.create_session("test")
        session.state = SessionState.BLOOMED
        mock_tmux.session_exists.return_value = False

        result = session_manager.revive_session(session.id)

        assert result is True
        assert session.state == SessionState.GROWING
        assert session.ended_at is None

    def test_revive_running_session_fails(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Cannot revive an already running session."""
        session = session_manager.create_session("test")
        assert session.state == SessionState.GROWING

        result = session_manager.revive_session(session.id)

        assert result is False

    def test_revive_nonexistent_session(self, session_manager: SessionManager):
        """Cannot revive nonexistent session."""
        result = session_manager.revive_session("nonexistent-id")
        assert result is False


class TestSessionManagerDangerousMode:
    """Tests for dangerous mode flag."""

    def test_create_session_with_dangerous_mode(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Create session with dangerously_skip_permissions enabled."""
        features = SessionFeatures(dangerously_skip_permissions=True)
        session = session_manager.create_session("test", features=features)

        assert session.dangerously_skip_permissions is True

    def test_create_session_without_dangerous_mode(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Create session without dangerous mode (default)."""
        session = session_manager.create_session("test")

        assert session.dangerously_skip_permissions is False

    def test_dangerous_mode_passed_to_command(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Dangerous mode flag is passed to claude command."""
        features = SessionFeatures(dangerously_skip_permissions=True)
        session_manager.create_session("test", features=features)

        # Check that create_session was called with command containing the flag
        call_args = mock_tmux.create_session.call_args
        command = call_args[1]["command"]
        # Command is wrapped in bash -c, so check the joined string
        command_str = " ".join(command)
        assert "--dangerously-skip-permissions" in command_str


class TestSessionManagerWithWorktree:
    """Tests for SessionManager worktree integration."""

    def test_create_session_with_worktree_enabled(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
        tmp_path: Path,
    ):
        """Create session with worktree when use_worktree is enabled."""
        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        assert session.worktree_path is not None
        assert session.worktree_branch == "test-branch"
        mock_worktree.create_worktree.assert_called_once()

    def test_create_session_with_worktree_branch(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
        tmp_path: Path,
    ):
        """Create session with specific worktree branch."""
        features = SessionFeatures(use_worktree=True, worktree_branch="my-feature")
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        mock_worktree.create_worktree.assert_called_once()
        call_kwargs = mock_worktree.create_worktree.call_args[1]
        assert call_kwargs["branch"] == "my-feature"

    def test_create_session_without_worktree(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
    ):
        """Create session without worktree (default)."""
        session = session_manager_with_worktree.create_session("test")

        assert session.worktree_path is None
        assert session.worktree_branch is None
        mock_worktree.create_worktree.assert_not_called()

    def test_create_session_worktree_failure_graceful_degradation(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
        tmp_path: Path,
    ):
        """Session creation succeeds even if worktree fails (graceful degradation)."""
        mock_worktree.create_worktree.return_value = WorktreeResult(
            success=False, error="branch already exists"
        )

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        # Session should still be created successfully
        assert session.state == SessionState.GROWING
        assert session.worktree_path is None  # Falls back to regular working dir
        mock_tmux.create_session.assert_called_once()

    def test_kill_session_cleans_worktree(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
        tmp_path: Path,
    ):
        """Kill session cleans up worktree."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_worktree.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        session_manager_with_worktree.kill_session(session.id)

        mock_worktree.remove_worktree.assert_called_once_with(worktree_path, force=True)

    def test_kill_session_without_worktree(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
    ):
        """Kill session doesn't clean worktree when none exists."""
        session = session_manager_with_worktree.create_session("test")

        session_manager_with_worktree.kill_session(session.id)

        mock_worktree.remove_worktree.assert_not_called()

    def test_session_tracks_resolved_working_dir_with_worktree(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
        tmp_path: Path,
    ):
        """Session's resolved_working_dir is updated to worktree path."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_worktree.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        assert session.resolved_working_dir == worktree_path

    def test_session_explicit_use_worktree_false(
        self,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        mock_worktree: MagicMock,
    ):
        """Session can explicitly disable worktree even if config enables it."""
        features = SessionFeatures(use_worktree=False)
        session = session_manager_with_worktree.create_session(
            "test", features=features
        )

        mock_worktree.create_worktree.assert_not_called()
        assert session.worktree_path is None
