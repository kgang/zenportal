"""Session command building for different session types."""

import shlex
import shutil
from pathlib import Path

from ..models.session import Session, SessionType
from .banner import generate_banner_command
from .config import ClaudeModel


class SessionCommandBuilder:
    """Builds shell commands for different session types."""

    # Binary required for each session type
    BINARY_MAP = {
        SessionType.CLAUDE: "claude",
        SessionType.CODEX: "codex",
        SessionType.GEMINI: "gemini",
        SessionType.SHELL: "zsh",
    }

    def validate_binary(self, session_type: SessionType) -> str | None:
        """Check if the required binary exists for the session type.

        Returns error message if binary not found, None if valid.
        """
        binary = self.BINARY_MAP.get(session_type)
        if binary and not shutil.which(binary):
            return f"Command '{binary}' not found in PATH"
        return None

    def build_create_command(
        self,
        session_type: SessionType,
        working_dir: Path,
        model: ClaudeModel | None = None,
        prompt: str = "",
        dangerous_mode: bool = False,
    ) -> list[str]:
        """Build command args for creating a new session.

        Args:
            session_type: Type of session to create
            working_dir: Working directory for the session
            model: Claude model to use (Claude sessions only)
            prompt: Initial prompt (Claude/Codex/Gemini only)
            dangerous_mode: Skip permissions (Claude only)

        Returns:
            List of command arguments
        """
        if session_type == SessionType.CLAUDE:
            command_args = ["claude"]
            if model:
                command_args.extend(["--model", model.value])
            if dangerous_mode:
                command_args.append("--dangerously-skip-permissions")
            if prompt:
                command_args.append(prompt)

        elif session_type == SessionType.CODEX:
            command_args = ["codex", "--cd", str(working_dir)]
            if prompt:
                command_args.append(prompt)

        elif session_type == SessionType.GEMINI:
            command_args = ["gemini"]
            if prompt:
                command_args.extend(["-p", prompt])

        else:
            # Shell session - start user's default shell with login profile
            command_args = ["zsh", "-l"]

        return command_args

    def build_revive_command(
        self,
        session: Session,
        was_failed: bool = False,
    ) -> list[str]:
        """Build command args for reviving a session.

        Args:
            session: Session to revive
            was_failed: Whether the session was in FAILED state

        Returns:
            List of command arguments
        """
        if session.session_type == SessionType.SHELL:
            return ["zsh", "-l"]

        elif session.session_type == SessionType.CODEX:
            return ["codex", "resume", "--last"]

        elif session.session_type == SessionType.GEMINI:
            return ["gemini", "--resume"]

        else:
            # Claude session
            if was_failed:
                # Failed session - start fresh
                command_args = ["claude"]
            else:
                # Completed/paused - try to resume
                if session.claude_session_id:
                    command_args = ["claude", "--resume", session.claude_session_id]
                else:
                    # No session ID - use --continue
                    command_args = ["claude", "--continue"]

            if session.resolved_model:
                command_args.extend(["--model", session.resolved_model.value])
            if session.dangerously_skip_permissions:
                command_args.append("--dangerously-skip-permissions")

            return command_args

    def build_resume_command(
        self,
        resume_session_id: str,
        model: ClaudeModel | None = None,
    ) -> list[str]:
        """Build command for resuming a specific Claude session.

        Args:
            resume_session_id: Claude session ID to resume
            model: Optional model override

        Returns:
            List of command arguments
        """
        command_args = ["claude", "--resume", resume_session_id]
        if model:
            command_args.extend(["--model", model.value])
        return command_args

    def wrap_with_banner(
        self,
        command: list[str],
        session_name: str,
        session_id: str,
    ) -> list[str]:
        """Wrap a command with a banner print for visual session separation.

        Returns a bash command that prints the banner then execs the original command.
        """
        banner_cmd = generate_banner_command(session_name, session_id)
        # Shell-escape the original command args
        escaped_cmd = " ".join(shlex.quote(arg) for arg in command)
        # Create a bash script that prints banner then execs command
        # Run command and wait on error
        script = f"{banner_cmd}; {escaped_cmd} || read -p 'Session ended with error. Press enter to close...'"
        return ["bash", "-c", script]
