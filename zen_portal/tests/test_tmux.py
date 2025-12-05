"""Tests for TmuxService."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from zen_portal.services.tmux import TmuxService, TmuxResult


class TestTmuxService:
    """Tests for TmuxService."""

    @pytest.fixture
    def tmux(self) -> TmuxService:
        """Create a TmuxService instance."""
        return TmuxService()

    @pytest.fixture
    def tmux_with_socket(self, tmp_path: Path) -> TmuxService:
        """Create a TmuxService with dedicated socket."""
        socket_path = tmp_path / "test.sock"
        return TmuxService(socket_path=socket_path)

    def test_base_cmd_default(self, tmux: TmuxService):
        """Default base command is just 'tmux'."""
        assert tmux._base_cmd() == ["tmux"]

    def test_base_cmd_with_socket(self, tmux_with_socket: TmuxService, tmp_path: Path):
        """With socket, base command includes -S flag."""
        socket_path = tmp_path / "test.sock"
        cmd = tmux_with_socket._base_cmd()
        assert cmd == ["tmux", "-S", str(socket_path)]

    def test_session_exists_true(self, tmux: TmuxService):
        """session_exists returns True when tmux reports session exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert tmux.session_exists("test-session") is True

    def test_session_exists_false(self, tmux: TmuxService):
        """session_exists returns False when tmux reports session doesn't exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert tmux.session_exists("test-session") is False

    def test_create_session_success(self, tmux: TmuxService, tmp_path: Path):
        """create_session returns success when tmux succeeds."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=tmp_path,
            )
            assert result.success is True
            assert result.error == ""

    def test_create_session_failure(self, tmux: TmuxService, tmp_path: Path):
        """create_session returns failure when tmux fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="duplicate session: test",
            )
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=tmp_path,
            )
            assert result.success is False
            assert "duplicate" in result.error

    def test_create_session_timeout(self, tmux: TmuxService, tmp_path: Path):
        """create_session handles timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=5)
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=tmp_path,
            )
            assert result.success is False
            assert "timed out" in result.error.lower()

    def test_create_session_tmux_not_found(self, tmux: TmuxService, tmp_path: Path):
        """create_session handles missing tmux."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=tmp_path,
            )
            assert result.success is False
            assert "not found" in result.error.lower()

    def test_kill_session_success(self, tmux: TmuxService):
        """kill_session returns success when tmux succeeds."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = tmux.kill_session("test")
            assert result.success is True

    def test_capture_pane_success(self, tmux: TmuxService):
        """capture_pane returns output when successful."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Line 1\nLine 2\nLine 3\n",
                stderr="",
            )
            result = tmux.capture_pane("test", lines=100)
            assert result.success is True
            assert "Line 1" in result.output

    def test_list_sessions_success(self, tmux: TmuxService):
        """list_sessions returns session names."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="zen-abc123\nzen-def456\n",
                stderr="",
            )
            sessions = tmux.list_sessions()
            assert len(sessions) == 2
            assert "zen-abc123" in sessions
            assert "zen-def456" in sessions

    def test_list_sessions_empty(self, tmux: TmuxService):
        """list_sessions returns empty list when no sessions."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            sessions = tmux.list_sessions()
            assert sessions == []

    def test_send_keys_items_literals(self, tmux: TmuxService):
        """send_keys handles KeyItem list with literals."""
        from zen_portal.screens.insert_modal import KeyItem

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            items = [
                KeyItem(value="h", display="h"),
                KeyItem(value="i", display="i"),
            ]
            result = tmux.send_keys("test", items)
            assert result.success is True
            # Should batch literals into single call with -l flag
            calls = mock_run.call_args_list
            # Find the send-keys call
            send_keys_calls = [c for c in calls if "send-keys" in c[0][0]]
            assert len(send_keys_calls) == 1
            assert "-l" in send_keys_calls[0][0][0]
            assert "hi" in send_keys_calls[0][0][0]

    def test_send_keys_items_special(self, tmux: TmuxService):
        """send_keys handles KeyItem list with special keys."""
        from zen_portal.screens.insert_modal import KeyItem

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            items = [
                KeyItem(value="Up", display="↑", is_special=True),
            ]
            result = tmux.send_keys("test", items)
            assert result.success is True
            # Special keys should NOT use -l flag
            calls = mock_run.call_args_list
            send_keys_calls = [c for c in calls if "send-keys" in c[0][0]]
            assert len(send_keys_calls) == 1
            assert "-l" not in send_keys_calls[0][0][0]
            assert "Up" in send_keys_calls[0][0][0]

    def test_send_keys_items_mixed(self, tmux: TmuxService):
        """send_keys handles mixed literals and special keys."""
        from zen_portal.screens.insert_modal import KeyItem

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            items = [
                KeyItem(value="h", display="h"),
                KeyItem(value="i", display="i"),
                KeyItem(value="Down", display="↓", is_special=True),
                KeyItem(value="!", display="!"),
            ]
            result = tmux.send_keys("test", items)
            assert result.success is True
            # Should be: "hi" (literal), Down (special), "!" (literal)
            calls = mock_run.call_args_list
            send_keys_calls = [c for c in calls if "send-keys" in c[0][0]]
            assert len(send_keys_calls) == 3

    def test_cleanup_dead_zen_sessions(self, tmux: TmuxService):
        """cleanup_dead_zen_sessions kills sessions with matching prefix and dead panes."""
        with patch.object(tmux, "list_sessions") as mock_list:
            with patch.object(tmux, "is_pane_dead") as mock_dead:
                with patch.object(tmux, "clear_history") as mock_clear:
                    with patch.object(tmux, "kill_session") as mock_kill:
                        # Mix of zen- sessions (some dead, some alive) and non-zen sessions
                        mock_list.return_value = [
                            "zen-abc123",  # dead
                            "zen-def456",  # alive
                            "other-session",  # non-zen, dead
                            "zen-ghi789",  # dead
                        ]
                        mock_dead.side_effect = lambda name: name in [
                            "zen-abc123",
                            "other-session",
                            "zen-ghi789",
                        ]
                        mock_kill.return_value = TmuxResult(success=True)

                        count = tmux.cleanup_dead_zen_sessions()

                        # Should only kill zen- sessions with dead panes
                        assert count == 2
                        assert mock_kill.call_count == 2
                        mock_kill.assert_any_call("zen-abc123")
                        mock_kill.assert_any_call("zen-ghi789")
                        # Should clear history before killing
                        assert mock_clear.call_count == 2

    def test_cleanup_dead_zen_sessions_custom_prefix(self, tmux: TmuxService):
        """cleanup_dead_zen_sessions respects custom prefix."""
        with patch.object(tmux, "list_sessions") as mock_list:
            with patch.object(tmux, "is_pane_dead") as mock_dead:
                with patch.object(tmux, "clear_history"):
                    with patch.object(tmux, "kill_session") as mock_kill:
                        mock_list.return_value = ["custom-abc", "zen-def", "custom-ghi"]
                        mock_dead.return_value = True  # All dead
                        mock_kill.return_value = TmuxResult(success=True)

                        count = tmux.cleanup_dead_zen_sessions(prefix="custom-")

                        assert count == 2
                        mock_kill.assert_any_call("custom-abc")
                        mock_kill.assert_any_call("custom-ghi")
