"""TmuxService: Low-level tmux operations."""

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass
class TmuxResult:
    """Result of a tmux operation."""

    success: bool
    output: str = ""
    error: str = ""


class TmuxService:
    """Low-level tmux operations. No business logic."""

    DEFAULT_TIMEOUT = 5
    DEFAULT_HISTORY_LIMIT = 10000  # Lines of scrollback (lower = less memory)

    def __init__(self, socket_path: Path | None = None, history_limit: int | None = None):
        """Initialize with optional dedicated socket and history limit."""
        self._socket = socket_path
        self._timeout = self.DEFAULT_TIMEOUT
        self._history_limit = history_limit or self.DEFAULT_HISTORY_LIMIT

    def _base_cmd(self) -> list[str]:
        """Base tmux command with optional socket."""
        if self._socket:
            return ["tmux", "-S", str(self._socket)]
        return ["tmux"]

    def _run(
        self,
        args: list[str],
        timeout: int | None = None,
    ) -> TmuxResult:
        """Run a tmux command with proper error handling."""
        cmd = self._base_cmd() + args
        timeout = timeout or self._timeout

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return TmuxResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return TmuxResult(success=False, error="Operation timed out")
        except FileNotFoundError:
            return TmuxResult(success=False, error="tmux not found")
        except Exception as e:
            return TmuxResult(success=False, error=str(e))

    def session_exists(self, name: str) -> bool:
        """Check if a tmux session exists."""
        result = self._run(["has-session", "-t", name])
        return result.success

    def create_session(
        self,
        name: str,
        command: list[str],
        working_dir: Path,
    ) -> TmuxResult:
        """Create a new detached tmux session running a command.

        Sets history-limit BEFORE session creation to ensure scrollback works
        properly. The history-limit is fixed at pane creation time and cannot
        be changed for existing panes.
        """
        # Validate working directory exists
        if not working_dir.exists():
            return TmuxResult(
                success=False,
                error=f"Working directory does not exist: {working_dir}",
            )

        # Use chained commands to set history-limit before creating session.
        # This is critical: history-limit is fixed at pane creation time.
        # Format: tmux set -g history-limit N \; new-session ...
        args = [
            "set-option", "-g", "history-limit", str(self._history_limit),
            ";",  # Chain next command
            "new-session",
            "-d",  # Detached
            "-s", name,
            "-c", str(working_dir),
        ] + command

        result = self._run(args)

        # Configure session options after creation
        if result.success:
            # Keep session alive after command exits (for viewing output)
            self._run(["set-option", "-t", name, "remain-on-exit", "on"])

        return result

    def configure_session(self, name: str) -> TmuxResult:
        """Configure session options for zen-portal management.

        Sets remain-on-exit for viewing output after process exits.
        Note: history-limit cannot be changed for existing panes.
        """
        return self._run(["set-option", "-t", name, "remain-on-exit", "on"])

    def kill_session(self, name: str) -> TmuxResult:
        """Kill a tmux session."""
        return self._run(["kill-session", "-t", name])

    def capture_pane(self, name: str, lines: int = 100) -> TmuxResult:
        """Capture output from a session's pane."""
        args = [
            "capture-pane",
            "-t", name,
            "-p",  # Print to stdout
            "-S", f"-{lines}",  # Last N lines
        ]
        return self._run(args)

    def send_keys(self, name: str, keys: list, enter: bool = False) -> TmuxResult:
        """Send keys to a session.

        Args:
            name: tmux session name
            keys: List of KeyItem objects to send
            enter: if True, send an additional Enter key at the end

        This batches consecutive literal characters together for efficiency,
        and sends special keys individually.
        """
        if not keys and not enter:
            return TmuxResult(success=True)

        # Batch consecutive literal characters
        literal_batch: list[str] = []

        def flush_literals() -> TmuxResult | None:
            """Flush accumulated literal characters."""
            nonlocal literal_batch
            if literal_batch:
                text = "".join(literal_batch)
                literal_batch = []
                return self._run(["send-keys", "-t", name, "-l", text])
            return None

        for item in keys:
            if item.is_special:
                # Flush any pending literals first
                result = flush_literals()
                if result and not result.success:
                    return result

                # Send special key (without -l flag)
                result = self._run(["send-keys", "-t", name, item.value])
                if not result.success:
                    return result
            else:
                # Accumulate literal characters
                literal_batch.append(item.value)

        # Flush remaining literals
        result = flush_literals()
        if result and not result.success:
            return result

        if enter:
            return self._run(["send-keys", "-t", name, "Enter"])

        return TmuxResult(success=True)

    def list_sessions(self) -> list[str]:
        """List all tmux session names."""
        result = self._run(["list-sessions", "-F", "#{session_name}"])
        if result.success and result.output.strip():
            return result.output.strip().split("\n")
        return []

    def is_pane_dead(self, name: str) -> bool:
        """Check if a session's pane is dead (process has exited).

        When remain-on-exit is enabled, the pane stays but the process exits.
        This detects that state.
        """
        # Get pane_dead flag: 1 if pane has exited, 0 if still running
        result = self._run([
            "display-message", "-t", name, "-p", "#{pane_dead}"
        ])
        if result.success:
            return result.output.strip() == "1"
        return False

    def get_pane_exit_status(self, name: str) -> int | None:
        """Get the exit status of a dead pane's process.

        Returns the exit code (0 = success, non-zero = error) or None
        if the pane is still running or doesn't exist.
        """
        result = self._run([
            "display-message", "-t", name, "-p", "#{pane_dead_status}"
        ])
        if result.success and result.output.strip():
            try:
                return int(result.output.strip())
            except ValueError:
                pass
        return None

    def get_pane_pid(self, name: str) -> int | None:
        """Get the PID of the process running in the pane.

        Returns None if no process or pane doesn't exist.
        """
        result = self._run([
            "display-message", "-t", name, "-p", "#{pane_pid}"
        ])
        if result.success and result.output.strip():
            try:
                return int(result.output.strip())
            except ValueError:
                pass
        return None

    def clear_history(self, name: str) -> TmuxResult:
        """Clear a session's scrollback history."""
        return self._run(["clear-history", "-t", name])

    def cleanup_dead_zen_sessions(self, prefix: str = "zen-") -> int:
        """Clean up tmux sessions with the given prefix that have dead panes.

        Returns the number of sessions cleaned up.
        """
        count = 0
        for session_name in self.list_sessions():
            if session_name.startswith(prefix) and self.is_pane_dead(session_name):
                self.clear_history(session_name)
                if self.kill_session(session_name).success:
                    count += 1
        return count

    def list_external_sessions(self, exclude_prefix: str = "zen-") -> list[str]:
        """List tmux sessions that don't match the exclude prefix.

        Returns session names that are not managed by zen-portal.
        """
        return [
            name for name in self.list_sessions()
            if not name.startswith(exclude_prefix)
        ]

    def get_pane_command(self, name: str) -> str | None:
        """Get the command running in a session's active pane.

        Returns the command name (e.g., 'claude', 'zsh', 'vim') or None.
        """
        result = self._run([
            "display-message", "-t", name, "-p", "#{pane_current_command}"
        ])
        if result.success and result.output.strip():
            return result.output.strip()
        return None

    def get_session_cwd(self, name: str) -> Path | None:
        """Get the current working directory of a session's active pane.

        Returns the path or None if unavailable.
        """
        result = self._run([
            "display-message", "-t", name, "-p", "#{pane_current_path}"
        ])
        if result.success and result.output.strip():
            return Path(result.output.strip())
        return None

    def get_session_info(self, name: str) -> dict:
        """Get detailed info about a tmux session.

        Returns dict with command, cwd, is_dead, pid.
        """
        return {
            "name": name,
            "command": self.get_pane_command(name),
            "cwd": self.get_session_cwd(name),
            "is_dead": self.is_pane_dead(name),
            "pid": self.get_pane_pid(name),
        }
