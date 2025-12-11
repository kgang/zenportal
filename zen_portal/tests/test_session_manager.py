"""Tests for SessionManager."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from zen_portal.services.session_manager import SessionManager
from zen_portal.services.tmux import TmuxResult
from zen_portal.services.worktree import WorktreeResult
from zen_portal.services.events import (
    EventBus,
    SessionCreatedEvent,
    SessionPausedEvent,
    SessionKilledEvent,
    SessionCleanedEvent,
)
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
        assert session.state == SessionState.RUNNING
        mock_tmux.create_session.assert_called_once()

    def test_create_session_with_prompt(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Create a session with name and prompt."""
        session = session_manager.create_session("fix-bug", "fix the auth bug")

        assert session.name == "fix-bug"
        assert session.prompt == "fix the auth bug"
        assert session.state == SessionState.RUNNING

    def test_create_session_tmux_failure(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session state is FAILED when tmux fails."""
        mock_tmux.create_session.return_value = TmuxResult(
            success=False, error="tmux error"
        )

        session = session_manager.create_session("test")
        assert session.state == SessionState.FAILED

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

    def test_refresh_states_completed(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session becomes COMPLETED when tmux session ends."""
        session = session_manager.create_session("test")
        mock_tmux.session_exists.return_value = False

        session_manager.refresh_states()

        assert session.state == SessionState.COMPLETED
        assert session.ended_at is not None

    def test_refresh_states_still_running(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Session stays RUNNING when tmux session exists."""
        session = session_manager.create_session("test")
        mock_tmux.session_exists.return_value = True

        session_manager.refresh_states()

        assert session.state == SessionState.RUNNING

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

    def test_rename_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Rename a session."""
        session = session_manager.create_session("original")

        result = session_manager.rename_session(session.id, "renamed")

        assert result is True
        assert session.name == "renamed"

    def test_rename_session_empty_name_fails(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Rename with empty name should fail."""
        session = session_manager.create_session("original")

        result = session_manager.rename_session(session.id, "  ")

        assert result is False
        assert session.name == "original"

    def test_rename_nonexistent_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Rename a nonexistent session should fail."""
        result = session_manager.rename_session("nonexistent", "new")

        assert result is False

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

    def test_revive_completed_session(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Revive a completed session."""
        session = session_manager.create_session("test")
        session.state = SessionState.COMPLETED
        mock_tmux.session_exists.return_value = False

        result = session_manager.revive_session(session.id)

        assert result is True
        assert session.state == SessionState.RUNNING
        assert session.ended_at is None

    def test_revive_running_session_fails(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Cannot revive an already running session."""
        session = session_manager.create_session("test")
        assert session.state == SessionState.RUNNING

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
    """Tests for SessionManager worktree integration.

    These tests patch WorktreeService at the class level since worktree
    operations now create services dynamically based on session working directory.
    """

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_create_session_with_worktree_enabled(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Create session with worktree when use_worktree is enabled."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )

        features = SessionFeatures(use_worktree=True, working_dir=tmp_path)
        session = session_manager_with_worktree.create_session("test", features=features)

        assert session.worktree_path == worktree_path
        assert session.worktree_branch == "test-branch"
        assert session.worktree_source_repo == tmp_path  # Source repo stored
        mock_instance.create_worktree.assert_called_once()

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_create_session_with_worktree_branch(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Create session with specific worktree branch."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="my-feature"
        )

        features = SessionFeatures(use_worktree=True, worktree_branch="my-feature")
        session = session_manager_with_worktree.create_session("test", features=features)

        mock_instance.create_worktree.assert_called_once()
        call_kwargs = mock_instance.create_worktree.call_args[1]
        assert call_kwargs["branch"] == "my-feature"

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_create_session_without_worktree(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
    ):
        """Create session without worktree (default)."""
        session = session_manager_with_worktree.create_session("test")

        assert session.worktree_path is None
        assert session.worktree_branch is None
        # WorktreeService should not be instantiated when use_worktree is not set
        mock_worktree_class.assert_not_called()

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_create_session_worktree_failure_graceful_degradation(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Session creation succeeds even if worktree fails (graceful degradation)."""
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=False, error="branch already exists"
        )

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session("test", features=features)

        # Session should still be created successfully
        assert session.state == SessionState.RUNNING
        assert session.worktree_path is None  # Falls back to regular working dir
        mock_tmux.create_session.assert_called_once()

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_kill_session_cleans_worktree(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Kill session cleans up worktree."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )
        mock_instance.remove_worktree.return_value = WorktreeResult(success=True)

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session("test", features=features)

        session_manager_with_worktree.kill_session(session.id)

        mock_instance.remove_worktree.assert_called_once_with(worktree_path, force=True)

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_kill_session_without_worktree(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
    ):
        """Kill session doesn't clean worktree when none exists."""
        session = session_manager_with_worktree.create_session("test")

        session_manager_with_worktree.kill_session(session.id)

        # WorktreeService not instantiated for cleanup when no worktree exists
        mock_worktree_class.assert_not_called()

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_session_tracks_resolved_working_dir_with_worktree(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Session's resolved_working_dir is updated to worktree path."""
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )

        features = SessionFeatures(use_worktree=True)
        session = session_manager_with_worktree.create_session("test", features=features)

        assert session.resolved_working_dir == worktree_path

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_session_explicit_use_worktree_false(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
    ):
        """Session can explicitly disable worktree even if config enables it."""
        features = SessionFeatures(use_worktree=False)
        session = session_manager_with_worktree.create_session("test", features=features)

        mock_worktree_class.assert_not_called()
        assert session.worktree_path is None

    @patch("zen_portal.services.worktree.WorktreeService")
    def test_worktree_uses_session_working_dir(
        self,
        mock_worktree_class: MagicMock,
        session_manager_with_worktree: SessionManager,
        mock_tmux: MagicMock,
        tmp_path: Path,
    ):
        """Worktree is created from session's working directory, not app startup dir."""
        custom_dir = tmp_path / "my-project"
        custom_dir.mkdir()
        worktree_path = tmp_path / "worktrees" / "test-worktree"
        mock_instance = mock_worktree_class.return_value
        mock_instance.is_git_repo.return_value = True
        mock_instance.create_worktree.return_value = WorktreeResult(
            success=True, path=worktree_path, branch="test-branch"
        )

        features = SessionFeatures(use_worktree=True, working_dir=custom_dir)
        session = session_manager_with_worktree.create_session("test", features=features)

        # WorktreeService should be created with the session's working directory
        mock_worktree_class.assert_called_once()
        call_kwargs = mock_worktree_class.call_args[1]
        assert call_kwargs["source_repo"] == custom_dir
        assert session.worktree_source_repo == custom_dir


class TestSessionManagerEventBus:
    """Tests for SessionManager EventBus integration."""

    @pytest.fixture(autouse=True)
    def reset_event_bus(self):
        """Reset EventBus before each test."""
        EventBus.reset()
        yield
        EventBus.reset()

    def test_create_session_emits_created_event(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Creating a session emits SessionCreatedEvent."""
        received = []
        EventBus.get().subscribe(SessionCreatedEvent, received.append)

        session = session_manager.create_session("test-session")

        assert len(received) == 1
        event = received[0]
        assert event.session_id == session.id
        assert event.session_name == "test-session"
        assert event.session_type == "ai"

    def test_pause_session_emits_paused_event(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Pausing a session emits SessionPausedEvent."""
        session = session_manager.create_session("test")
        received = []
        EventBus.get().subscribe(SessionPausedEvent, received.append)

        session_manager.pause_session(session.id)

        assert len(received) == 1
        assert received[0].session_id == session.id

    def test_kill_session_emits_killed_event(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Killing a session emits SessionKilledEvent."""
        session = session_manager.create_session("test")
        received = []
        EventBus.get().subscribe(SessionKilledEvent, received.append)

        session_manager.kill_session(session.id)

        assert len(received) == 1
        assert received[0].session_id == session.id

    def test_clean_session_emits_cleaned_event(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Cleaning a session emits SessionCleanedEvent."""
        session = session_manager.create_session("test")
        session_manager.pause_session(session.id)  # Must be non-active to clean
        received = []
        EventBus.get().subscribe(SessionCleanedEvent, received.append)

        session_manager.clean_session(session.id)

        assert len(received) == 1
        assert received[0].session_id == session.id

    def test_custom_event_bus_injection(
        self, mock_tmux: MagicMock, config_manager, tmp_path: Path
    ):
        """SessionManager accepts custom EventBus via DI."""
        custom_bus = EventBus()
        received = []
        custom_bus.subscribe(SessionCreatedEvent, received.append)

        state_dir = tmp_path / ".zen_portal"
        manager = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
            event_bus=custom_bus,
        )

        manager.create_session("test")

        assert len(received) == 1


class TestSessionManagerCursorPersistence:
    """Tests for cursor position (selected session) persistence."""

    def test_selected_session_id_initially_none(
        self, session_manager: SessionManager
    ):
        """Selected session is None when no sessions exist."""
        assert session_manager.selected_session_id is None

    def test_set_selected_session_persists(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Setting selected session persists to state."""
        session = session_manager.create_session("test")

        session_manager.set_selected_session(session.id)

        assert session_manager.selected_session_id == session.id

    def test_selected_session_survives_reload(
        self, mock_tmux: MagicMock, config_manager, tmp_path: Path
    ):
        """Selected session ID is restored after creating new SessionManager."""
        state_dir = tmp_path / ".zen_portal"

        # Create first manager and set selection
        manager1 = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )
        session = manager1.create_session("test-session")
        manager1.set_selected_session(session.id)

        # Create second manager (simulates app restart)
        manager2 = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )

        assert manager2.selected_session_id == session.id

    def test_selected_session_cleared_if_session_deleted(
        self, mock_tmux: MagicMock, config_manager, tmp_path: Path
    ):
        """Selected session ID is cleared if session no longer exists on reload."""
        state_dir = tmp_path / ".zen_portal"

        # Create manager and set selection
        manager1 = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )
        session = manager1.create_session("test")
        manager1.set_selected_session(session.id)

        # Simulate session no longer existing (tmux gone, no worktree)
        mock_tmux.session_exists.return_value = False

        # Create second manager - session won't be restored
        manager2 = SessionManager(
            tmux=mock_tmux,
            config_manager=config_manager,
            base_dir=state_dir,
            working_dir=tmp_path,
        )

        # Selected ID should be None since session doesn't exist
        assert manager2.selected_session_id is None

    def test_set_selected_session_to_none(
        self, session_manager: SessionManager, mock_tmux: MagicMock
    ):
        """Can set selected session to None."""
        session = session_manager.create_session("test")
        session_manager.set_selected_session(session.id)

        session_manager.set_selected_session(None)

        assert session_manager.selected_session_id is None
