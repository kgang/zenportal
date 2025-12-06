"""Session command building for different session types."""

import os
import re
import shlex
import shutil
from pathlib import Path
from urllib.parse import urlparse

from ..models.session import Session, SessionType
from .banner import generate_banner_command
from .config import ClaudeModel, ProxySettings, ProxyAuthType


# Validation patterns
_API_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
# OAuth tokens are base64-encoded JWTs: header.payload.signature
# Allow alphanumeric, dash, underscore, period, equals (padding)
_OAUTH_TOKEN_PATTERN = re.compile(r'^[a-zA-Z0-9_.\-=]+$')
_SAFE_URL_SCHEMES = frozenset({'http', 'https'})
_MAX_API_KEY_LENGTH = 256
_MAX_OAUTH_TOKEN_LENGTH = 4096  # JWTs can be longer than API keys
_MAX_URL_LENGTH = 2048


class SessionCommandBuilder:
    """Builds shell commands for different session types."""

    # Binary required for each session type
    BINARY_MAP = {
        SessionType.CLAUDE: "claude",
        SessionType.CODEX: "codex",
        SessionType.GEMINI: "gemini",
        SessionType.SHELL: "zsh",
        SessionType.OPENROUTER: "orchat",
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

        elif session_type == SessionType.OPENROUTER:
            command_args = ["orchat"]
            # Note: model selection handled via orchat's /model command
            # or --model flag if provided via config

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

        elif session.session_type == SessionType.OPENROUTER:
            # orchat has session management via /sessions command
            # Start fresh for revive
            return ["orchat"]

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

    def _validate_oauth_token(self, token: str) -> str | None:
        """Validate an OAuth token for safe use in environment variables.

        Returns the token if valid, None otherwise.
        OAuth tokens are typically JWTs (base64-encoded with periods as separators).
        """
        if not token or len(token) > _MAX_OAUTH_TOKEN_LENGTH:
            return None

        token = token.strip()

        # Check for safe characters only (base64 + JWT separators)
        if not _OAUTH_TOKEN_PATTERN.match(token):
            return None

        return token

    def build_proxy_env_vars(
        self,
        proxy_settings: ProxySettings,
    ) -> dict[str, str]:
        """Build environment variables for Claude proxy (y-router or CLIProxyAPI).

        Two primary modes:
        - OPENROUTER: y-router with OpenRouter API key (pay-per-token)
        - CLAUDE_ACCOUNT: CLIProxyAPI handles auth internally (Pro/Max subscription)

        All values are validated before use to prevent injection attacks.

        Args:
            proxy_settings: Proxy configuration

        Returns:
            Dictionary of environment variables to set
        """
        if not proxy_settings or not proxy_settings.enabled:
            return {}

        env_vars = {}

        # Use effective_base_url which applies mode-appropriate defaults
        validated_url = self._validate_url(proxy_settings.effective_base_url)
        if validated_url:
            env_vars["ANTHROPIC_BASE_URL"] = validated_url

        # Normalize auth type for consistent handling
        auth_type = ProxyAuthType.normalize(proxy_settings.auth_type)

        if auth_type == ProxyAuthType.CLAUDE_ACCOUNT:
            # Claude Account mode: proxy handles auth internally (CLIProxyAPI)
            # No credentials needed from us
            pass
        elif auth_type == ProxyAuthType.OPENROUTER:
            # OpenRouter mode: x-api-key header for y-router
            api_key = proxy_settings.api_key or os.environ.get("OPENROUTER_API_KEY", "")
            if api_key:
                validated_key = self._validate_api_key(api_key)
                if validated_key:
                    env_vars["ANTHROPIC_API_KEY"] = validated_key
                    env_vars["ANTHROPIC_CUSTOM_HEADERS"] = f"x-api-key: {validated_key}"
        else:
            # OAuth mode (deprecated): manual token injection
            oauth_token = proxy_settings.oauth_token or os.environ.get("CLAUDE_OAUTH_TOKEN", "")
            if oauth_token:
                validated_token = self._validate_oauth_token(oauth_token)
                if validated_token:
                    env_vars["ANTHROPIC_API_KEY"] = validated_token
                    env_vars["ANTHROPIC_CUSTOM_HEADERS"] = (
                        f"Authorization: Bearer {validated_token}\n"
                        f"Cookie: sessionKey={validated_token}"
                    )

        # Model override (primarily for OpenRouter which uses provider/model format)
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
        """
        banner_cmd = generate_banner_command(session_name, session_id)

        # Build env var exports if provided
        env_exports = ""
        if env_vars:
            exports = [f"export {k}={shlex.quote(v)}" for k, v in env_vars.items()]
            env_exports = " && ".join(exports) + " && "

        # Shell-escape the original command args
        escaped_cmd = " ".join(shlex.quote(arg) for arg in command)
        # Create a bash script that prints banner then execs command
        # Run command and wait on error
        script = f"{banner_cmd}; {env_exports}{escaped_cmd} || read -p 'Session ended with error. Press enter to close...'"
        return ["bash", "-c", script]
