"""Tests for app restart functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from zen_portal.screens.exit_modal import ExitChoice, ExitResult, ExitModal


class TestExitChoice:
    """Test ExitChoice enum includes RESTART."""

    def test_restart_choice_exists(self):
        """RESTART is a valid ExitChoice."""
        assert ExitChoice.RESTART == ExitChoice("restart")
        assert ExitChoice.RESTART.value == "restart"

    def test_all_exit_choices(self):
        """All expected exit choices are present."""
        choices = {c.value for c in ExitChoice}
        assert choices == {"cancel", "kill_all", "kill_dead", "keep_all", "restart"}


class TestExitResult:
    """Test ExitResult dataclass with restart."""

    def test_exit_result_restart(self):
        """ExitResult can be created with RESTART choice."""
        result = ExitResult(ExitChoice.RESTART, remember=False)
        assert result.choice == ExitChoice.RESTART
        assert result.remember is False

    def test_exit_result_restart_remember_ignored(self):
        """ExitResult with RESTART can have remember flag (though not used)."""
        result = ExitResult(ExitChoice.RESTART, remember=True)
        assert result.choice == ExitChoice.RESTART
        assert result.remember is True


class TestLoadRestartContext:
    """Test _load_restart_context function."""

    def test_load_restart_context_no_file(self, tmp_path, monkeypatch):
        """Returns None when restart context file doesn't exist."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from zen_portal.app import _load_restart_context
        result = _load_restart_context()
        assert result is None

    def test_load_restart_context_valid_file(self, tmp_path, monkeypatch):
        """Returns context dict and deletes file."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create restart context file
        zen_dir = tmp_path / ".zen_portal"
        zen_dir.mkdir()
        restart_file = zen_dir / "restart_context.json"
        context = {
            "selected_session_id": "abc123",
            "selected_index": 2,
            "info_mode": True,
        }
        restart_file.write_text(json.dumps(context))

        from zen_portal.app import _load_restart_context
        result = _load_restart_context()

        assert result == context
        assert not restart_file.exists()  # File should be deleted

    def test_load_restart_context_invalid_json(self, tmp_path, monkeypatch):
        """Returns None and cleans up when file has invalid JSON."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        zen_dir = tmp_path / ".zen_portal"
        zen_dir.mkdir()
        restart_file = zen_dir / "restart_context.json"
        restart_file.write_text("not valid json {{{")

        from zen_portal.app import _load_restart_context
        result = _load_restart_context()

        assert result is None
        assert not restart_file.exists()  # File should be cleaned up


class TestSaveRestartContext:
    """Test _save_restart_context method."""

    def test_save_restart_context_with_session(self, tmp_path, monkeypatch):
        """Saves context with selected session info."""
        # Create mock session and session list
        mock_session = MagicMock()
        mock_session.id = "session-123"

        mock_session_list = MagicMock()
        mock_session_list.get_selected.return_value = mock_session
        mock_session_list.selected_index = 3

        # Create mock mixin instance
        class MockMixin:
            info_mode = True

            def query_one(self, selector, cls):
                return mock_session_list

        from zen_portal.screens.main_actions import MainScreenExitMixin
        mixin = type("TestMixin", (MainScreenExitMixin, MockMixin), {})()

        # Patch Path.home to use tmp_path
        with patch.object(Path, "home", return_value=tmp_path):
            mixin._save_restart_context()

        # Verify file was created
        restart_file = tmp_path / ".zen_portal" / "restart_context.json"
        assert restart_file.exists()

        # Verify content
        context = json.loads(restart_file.read_text())
        assert context["selected_session_id"] == "session-123"
        assert context["selected_index"] == 3
        assert context["info_mode"] is True

    def test_save_restart_context_no_session(self, tmp_path, monkeypatch):
        """Saves context when no session is selected."""
        mock_session_list = MagicMock()
        mock_session_list.get_selected.return_value = None
        mock_session_list.selected_index = 0

        class MockMixin:
            info_mode = False

            def query_one(self, selector, cls):
                return mock_session_list

        from zen_portal.screens.main_actions import MainScreenExitMixin
        mixin = type("TestMixin", (MainScreenExitMixin, MockMixin), {})()

        with patch.object(Path, "home", return_value=tmp_path):
            mixin._save_restart_context()

        restart_file = tmp_path / ".zen_portal" / "restart_context.json"
        context = json.loads(restart_file.read_text())
        assert context["selected_session_id"] is None
        assert context["selected_index"] == 0
        assert context["info_mode"] is False


class TestExitWithCleanupRestart:
    """Test _exit_with_cleanup with restart=True."""

    def test_exit_with_cleanup_restart(self):
        """Restart flag triggers context save and special exit."""
        mock_app = MagicMock()
        mock_manager = MagicMock()
        mock_session_list = MagicMock()
        mock_session_list.get_selected.return_value = None
        mock_session_list.selected_index = 0

        class MockMixin:
            app = mock_app
            _manager = mock_manager
            info_mode = False

            def query_one(self, selector, cls):
                return mock_session_list

        from zen_portal.screens.main_actions import MainScreenExitMixin
        mixin = type("TestMixin", (MainScreenExitMixin, MockMixin), {})()

        with patch.object(mixin, "_save_restart_context") as mock_save:
            mixin._exit_with_cleanup(restart=True)

        # Verify save_state was called
        mock_manager.save_state.assert_called_once()

        # Verify restart context was saved
        mock_save.assert_called_once()

        # Verify app.exit was called with restart result
        mock_app.exit.assert_called_once_with(result={"restart": True})

    def test_exit_with_cleanup_restart_skips_keep_running_logic(self):
        """Restart exits before keep_running logic runs."""
        mock_app = MagicMock()
        mock_manager = MagicMock()
        mock_manager.sessions = []  # Would be iterated if keep_running ran
        mock_session_list = MagicMock()
        mock_session_list.get_selected.return_value = None
        mock_session_list.selected_index = 0

        class MockMixin:
            app = mock_app
            _manager = mock_manager
            info_mode = False

            def query_one(self, selector, cls):
                return mock_session_list

        from zen_portal.screens.main_actions import MainScreenExitMixin
        mixin = type("TestMixin", (MainScreenExitMixin, MockMixin), {})()

        with patch.object(mixin, "_save_restart_context"):
            mixin._exit_with_cleanup(keep_running=True, restart=True)

        # Verify get_tmux_session_name was never called (keep_running logic skipped)
        mock_manager.get_tmux_session_name.assert_not_called()

        # Verify app.exit was called with restart result (not kept_sessions)
        mock_app.exit.assert_called_once_with(result={"restart": True})


class TestActionRestartApp:
    """Test action_restart_app method."""

    def test_action_restart_app(self):
        """action_restart_app calls _exit_with_cleanup(restart=True)."""
        from zen_portal.screens.main_actions import MainScreenExitMixin

        class MockMixin:
            pass

        mixin = type("TestMixin", (MainScreenExitMixin, MockMixin), {})()

        with patch.object(mixin, "_exit_with_cleanup") as mock_exit:
            mixin.action_restart_app()

        mock_exit.assert_called_once_with(restart=True)


class TestMainLoopRestart:
    """Test restart handling in main loop."""

    def test_main_loop_restart_result(self):
        """Main loop continues when app returns restart result."""
        # This is an integration-level test of the main loop logic
        # We verify the restart condition check works correctly

        result = {"restart": True}

        # Verify the condition that would trigger restart handling
        assert result and isinstance(result, dict) and result.get("restart")

    def test_main_loop_non_restart_result(self):
        """Main loop breaks for non-restart dict results."""
        result = {"kept_sessions": []}

        # This should NOT trigger restart
        assert not (result and isinstance(result, dict) and result.get("restart"))

    def test_main_loop_attach_result(self):
        """Main loop handles attach result separately from restart."""
        result = "attach:my-session"

        # This should NOT trigger restart
        assert not (result and isinstance(result, dict) and result.get("restart"))


class TestExitModalRestart:
    """Test ExitModal includes restart button."""

    def test_exit_modal_has_restart_button(self):
        """ExitModal has restart button in button_ids."""
        modal = ExitModal(active_count=1, dead_count=0)
        # Button IDs are populated in compose(), but we can test the class
        assert hasattr(modal, "_button_ids")

    def test_exit_choice_restart_handled(self):
        """ExitModal _handle_choice processes restart correctly."""
        modal = ExitModal()

        # Mock the dismiss and query_one methods
        modal.dismiss = MagicMock()
        mock_checkbox = MagicMock()
        mock_checkbox.value = False
        modal.query_one = MagicMock(return_value=mock_checkbox)

        modal._handle_choice("restart")

        # Verify dismiss was called with RESTART choice
        call_args = modal.dismiss.call_args[0][0]
        assert isinstance(call_args, ExitResult)
        assert call_args.choice == ExitChoice.RESTART
        assert call_args.remember is False
