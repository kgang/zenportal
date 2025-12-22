"""Session command building for different session types."""

import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ..models.session import Session, SessionType
from .banner import generate_banner_command
from .config import ClaudeModel, ProxySettings


# Tmux has a command length limit (~16KB). Commands exceeding this need special handling.
_TMUX_CMD_LENGTH_THRESHOLD = 12000  # Leave margin for banner and other parts

# Validation patterns
_API_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
_SAFE_URL_SCHEMES = frozenset({'http', 'https'})
_MAX_API_KEY_LENGTH = 256
_MAX_URL_LENGTH = 2048


class SessionCommandBuilder:
    """Builds shell commands for different session types."""

    # Binary required for each AI provider
    AI_PROVIDER_BINARY_MAP = {
        "claude": "claude",
        "codex": "codex",
        "gemini": "gemini",
        "openrouter": "orchat",
    }

    def validate_binary(self, session_type: SessionType, provider: str = "claude") -> str | None:
        """Check if the required binary exists for the session type.

        Returns error message if binary not found, None if valid.
        """
        if session_type == SessionType.AI:
            binary = self.AI_PROVIDER_BINARY_MAP.get(provider)
            if binary and not shutil.which(binary):
                return f"Command '{binary}' not found in PATH"
        elif session_type == SessionType.SHELL:
            if not shutil.which("zsh"):
                return "Command 'zsh' not found in PATH"
        return None

    def build_create_command(
        self,
        session_type: SessionType,
        working_dir: Path,
        provider: str = "claude",
        model: ClaudeModel | None = None,
        prompt: str = "",
        system_prompt: str = "",
        dangerous_mode: bool = False,
    ) -> list[str]:
        """Build command args for creating a new session.

        Args:
            session_type: Type of session to create (AI or SHELL)
            working_dir: Working directory for the session
            provider: AI provider (claude, codex, gemini, openrouter) for AI sessions
            model: Claude model to use (Claude provider only)
            prompt: Initial prompt (AI sessions only)
            system_prompt: System prompt for Claude (--system-prompt argument)
            dangerous_mode: Skip permissions (Claude only)

        Returns:
            List of command arguments
        """
        if session_type == SessionType.AI:
            if provider == "claude":
                command_args = ["claude"]
                if model:
                    command_args.extend(["--model", model.value])
                if dangerous_mode:
                    command_args.append("--dangerously-skip-permissions")
                if system_prompt:
                    command_args.extend(["--system-prompt", system_prompt])
                if prompt:
                    command_args.append(prompt)

            elif provider == "codex":
                command_args = ["codex", "--cd", str(working_dir)]
                if prompt:
                    command_args.append(prompt)

            elif provider == "gemini":
                command_args = ["gemini"]
                if prompt:
                    command_args.extend(["-p", prompt])

            elif provider == "openrouter":
                command_args = ["orchat"]
                # Note: model selection handled via orchat's /model command
                # or --model flag if provided via config
            else:
                # Fallback to Claude
                command_args = ["claude"]
                if prompt:
                    command_args.append(prompt)

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

        elif session.session_type == SessionType.AI:
            provider = session.provider

            if provider == "codex":
                return ["codex", "resume", "--last"]

            elif provider == "gemini":
                return ["gemini", "--resume"]

            elif provider == "openrouter":
                # orchat has session management via /sessions command
                # Start fresh for revive
                return ["orchat"]

            else:
                # Claude session (default)
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

        # Fallback to shell
        return ["zsh", "-l"]

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

    def _validate_url(self, url: str) -> str | None:
        """Validate and sanitize a URL for use as an API base URL.

        Returns the sanitized URL or None if invalid.
        """
        if not url or len(url) > _MAX_URL_LENGTH:
            return None

        try:
            parsed = urlparse(url)
            # Only allow http/https schemes
            if parsed.scheme not in _SAFE_URL_SCHEMES:
                return None
            # Must have a host
            if not parsed.netloc:
                return None
            # Reconstruct to normalize (removes potential obfuscation)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        except Exception:
            return None

    def _validate_api_key(self, key: str) -> str | None:
        """Validate an API key for safe use in environment variables.

        Returns the key if valid, None otherwise.
        API keys should be alphanumeric with dashes/underscores only.
        """
        if not key or len(key) > _MAX_API_KEY_LENGTH:
            return None

        # Strip whitespace
        key = key.strip()

        # Check for safe characters only (alphanumeric, dash, underscore)
        # Most API keys follow this pattern (sk-or-xxx, sk-ant-xxx, etc.)
        if not _API_KEY_PATTERN.match(key):
            return None

        return key

    def _validate_model_name(self, model: str) -> str | None:
        """Validate a model name for safe use.

        Returns the model name if valid, None otherwise.
        Model names should be alphanumeric with common separators.
        """
        if not model or len(model) > 128:
            return None

        model = model.strip()

        # Allow alphanumeric, dash, underscore, slash, colon, period
        # e.g., "anthropic/claude-sonnet-4", "openai/gpt-4o:beta"
        if not re.match(r'^[a-zA-Z0-9/_:.-]+$', model):
            return None

        return model

    def build_proxy_env_vars(
        self,
        proxy_settings: ProxySettings,
    ) -> dict[str, str]:
        """Build environment variables for Claude proxy (y-router).

        Routes Claude Code through y-router for pay-per-token via OpenRouter.
        All values are validated before use to prevent injection attacks.

        Args:
            proxy_settings: Proxy configuration

        Returns:
            Dictionary of environment variables to set
        """
        if not proxy_settings or not proxy_settings.enabled:
            return {}

        env_vars = {}

        # Use effective_base_url which applies default
        validated_url = self._validate_url(proxy_settings.effective_base_url)
        if validated_url:
            env_vars["ANTHROPIC_BASE_URL"] = validated_url

        # OpenRouter API key for y-router
        api_key = proxy_settings.api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if api_key:
            validated_key = self._validate_api_key(api_key)
            if validated_key:
                env_vars["ANTHROPIC_API_KEY"] = validated_key
                env_vars["ANTHROPIC_CUSTOM_HEADERS"] = f"x-api-key: {validated_key}"

        # Model override (OpenRouter uses provider/model format)
        if proxy_settings.default_model:
            validated_model = self._validate_model_name(proxy_settings.default_model)
            if validated_model:
                env_vars["ANTHROPIC_MODEL"] = validated_model

        return env_vars

    # Backwards compatibility alias
    def build_openrouter_env_vars(
        self,
        proxy_settings: ProxySettings,
    ) -> dict[str, str]:
        """Deprecated: Use build_proxy_env_vars instead."""
        return self.build_proxy_env_vars(proxy_settings)

    def wrap_with_banner(
        self,
        command: list[str],
        session_name: str,
        session_id: str,
        env_vars: dict[str, str] | None = None,
    ) -> list[str]:
        """Wrap a command with a banner print for visual session separation.

        Args:
            command: The command to wrap
            session_name: Name to display in banner
            session_id: Session ID for banner
            env_vars: Optional environment variables to export before running

        Returns a bash command that prints the banner then execs the original command.

        For large commands (>12KB), writes a launcher script to a temp file
        to avoid tmux's command length limit (~16KB).
        """
        banner_cmd = generate_banner_command(session_name, session_id)

        # Build env var exports if provided
        # Always unset VIRTUAL_ENV to prevent zen-portal's venv from leaking into sessions
        env_exports = "unset VIRTUAL_ENV && "
        if env_vars:
            exports = [f"export {k}={shlex.quote(v)}" for k, v in env_vars.items()]
            env_exports += " && ".join(exports) + " && "

        # Shell-escape the original command args
        escaped_cmd = " ".join(shlex.quote(arg) for arg in command)

        # Check if command would exceed tmux's limit
        inline_script = f"{banner_cmd}; {env_exports}{escaped_cmd} || read -p 'Session ended with error. Press enter to close...'"

        if len(inline_script) > _TMUX_CMD_LENGTH_THRESHOLD:
            # Write to temp file to bypass tmux command length limit
            return self._create_launcher_script(
                banner_cmd, env_exports, escaped_cmd, session_id
            )

        # Standard inline approach for small commands
        # Use zsh -l -i -c to source ~/.zshrc and get user's PATH/aliases
        # -l = login shell (sources .zprofile)
        # -i = interactive shell (sources .zshrc)
        return ["zsh", "-l", "-i", "-c", inline_script]

    def _create_launcher_script(
        self,
        banner_cmd: str,
        env_exports: str,
        escaped_cmd: str,
        session_id: str,
    ) -> list[str]:
        """Create a launcher script file for commands exceeding tmux's limit.

        Writes a shell script to a temp file and returns a command to execute it.
        The script removes itself after running (self-cleaning).
        """
        # Create temp dir for zen-portal scripts if needed
        script_dir = Path(tempfile.gettempdir()) / "zen-portal"
        script_dir.mkdir(exist_ok=True)

        # Use session_id to make script name unique and traceable
        script_path = script_dir / f"launch-{session_id}.sh"

        # Build the script content
        script_content = f"""#!/bin/zsh -l
# Auto-generated launcher script for zen-portal session
# This file self-deletes after running

{banner_cmd}
{env_exports}{escaped_cmd} || read -p 'Session ended with error. Press enter to close...'

# Self-cleanup
rm -f "$0"
"""
        # Write script with secure permissions
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o700)  # Owner execute only

        # Return command to run the script via zsh for user PATH/aliases
        # -l = login shell, -i = interactive (sources .zshrc)
        return ["zsh", "-l", "-i", str(script_path)]
