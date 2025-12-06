"""SessionManager: Core session lifecycle management."""

from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models.session import Session, SessionState, SessionFeatures, SessionType
from ..models.events import SessionCreated, SessionPaused, SessionKilled, SessionCleaned
from .tmux import TmuxService
from .config import ConfigManager, FeatureSettings, WorktreeSettings, OpenRouterProxySettings
from .worktree import WorktreeService
from .discovery import DiscoveryService
from .state import StateService
from .token_parser import TokenParser
from .session_persistence import SessionPersistence
from .session_commands import SessionCommandBuilder
from .proxy_validation import ProxyValidator, ProxyValidationResult


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass


class ProxyConfigWarning(Exception):
    """Warning about proxy configuration issues (non-fatal)."""
    pass


class SessionManager:
    """Manages Claude Code sessions in tmux."""

    MAX_SESSIONS = 10

    def __init__(
        self,
        tmux: TmuxService,
        config_manager: ConfigManager,
        worktree_service: WorktreeService | None = None,
        working_dir: Path | None = None,
        on_event: Callable | None = None,
        state_service: StateService | None = None,
    ):
        self._tmux = tmux
        self._config = config_manager
        self._worktree = worktree_service
        self._fallback_working_dir = working_dir or Path.cwd()
        self._on_event = on_event
        self._state = state_service or StateService()
        self._sessions: dict[str, Session] = {}
        self._token_parser = TokenParser()
        self._commands = SessionCommandBuilder()

        # Initialize persistence handler
        self._persistence = SessionPersistence(
            state_service=self._state,
            tmux_name_func=self._tmux_name,
            tmux_session_exists_func=self._tmux.session_exists,
            tmux_is_pane_dead_func=self._tmux.is_pane_dead,
        )

        # Load persisted state on startup
        self._sessions = self._persistence.load_persisted_sessions()

    @property
    def sessions(self) -> list[Session]:
        """All sessions sorted by creation time (newest first)."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )

    def _emit(self, event) -> None:
        if self._on_event:
            self._on_event(event)

    def _get_session_prefix(self) -> str:
        """Get the session prefix from resolved config."""
        resolved = self._config.resolve_features()
        return resolved.session_prefix or "zen"

    def _tmux_name(self, session_id: str) -> str:
        prefix = self._get_session_prefix()
        return f"{prefix}-{session_id[:8]}"

    def create_session(
        self,
        name: str,
        prompt: str = "",
        features: SessionFeatures | None = None,
        session_type: SessionType = SessionType.CLAUDE,
    ) -> Session:
        """Create a new session (Claude Code, Codex, Gemini, or shell).

        Args:
            name: Display name for the session
            prompt: Optional initial prompt (AI sessions only)
            features: Optional session-level feature overrides
            session_type: Type of session to create

        Returns:
            The created Session
        """
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        # Resolve features through config tiers
        session_override = None
        if features and features.has_overrides():
            session_override = FeatureSettings(
                working_dir=features.working_dir,
                model=features.model if session_type == SessionType.CLAUDE else None,
            )
        resolved = self._config.resolve_features(session_override)

        # Determine working directory
        working_dir = resolved.working_dir or self._fallback_working_dir
        dangerous_mode = features.dangerously_skip_permissions if features else False

        # Create session model
        session = Session(
            name=name,
            prompt=prompt if session_type == SessionType.CLAUDE else "",
            session_type=session_type,
            features=features or SessionFeatures(),
            resolved_working_dir=working_dir,
            resolved_model=resolved.model if session_type == SessionType.CLAUDE else None,
            dangerously_skip_permissions=dangerous_mode,
        )

        # Handle worktree creation if enabled
        working_dir = self._setup_worktree_if_needed(session, features, resolved.worktree)

        self._sessions[session.id] = session

        # Validate binary exists
        binary_error = self._commands.validate_binary(session_type)
        if binary_error:
            session.state = SessionState.FAILED
            session.error_message = binary_error
            self._emit(SessionCreated(session))
            self._persist_change(session, "created")
            return session

        # Validate proxy settings for Claude sessions
        if session_type == SessionType.CLAUDE and resolved.openrouter_proxy:
            proxy_result = self.validate_proxy(resolved.openrouter_proxy)
            if proxy_result and proxy_result.has_errors:
                # Store warning but don't fail - proxy issues shouldn't block session start
                session.proxy_warning = proxy_result.summary

        # Build and wrap command
        if session_type == SessionType.CLAUDE:
            session.claude_session_id = ""  # Will be discovered later

        command_args = self._commands.build_create_command(
            session_type=session_type,
            working_dir=working_dir,
            model=resolved.model,
            prompt=prompt,
            dangerous_mode=dangerous_mode,
        )

        # Get OpenRouter proxy env vars if enabled for Claude sessions
        env_vars = None
        if session_type == SessionType.CLAUDE and resolved.openrouter_proxy:
            env_vars = self._commands.build_openrouter_env_vars(resolved.openrouter_proxy)

        command = self._commands.wrap_with_banner(command_args, name, session.id, env_vars)

        # Create tmux session
        tmux_name = self._tmux_name(session.id)
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=working_dir,
        )

        session.state = SessionState.RUNNING if result.success else SessionState.FAILED
        if not result.success:
            session.error_message = result.error or "Failed to create tmux session"

        self._emit(SessionCreated(session))
        self._persist_change(session, "created")
        return session

    def _setup_worktree_if_needed(
        self,
        session: Session,
        features: SessionFeatures | None,
        worktree_settings: WorktreeSettings | None,
    ) -> Path:
        """Set up worktree for session if enabled. Returns working directory."""
        working_dir = session.resolved_working_dir

        use_worktree = self._should_use_worktree(features, worktree_settings)
        if not use_worktree or not self._worktree:
            return working_dir

        # Determine branch and from_branch
        branch_name = features.worktree_branch if features else None
        from_branch = "main"
        if worktree_settings and worktree_settings.default_from_branch:
            from_branch = worktree_settings.default_from_branch

        env_files = None
        if worktree_settings and worktree_settings.env_files:
            env_files = worktree_settings.env_files

        # Create worktree
        worktree_name = f"{session.name}-{session.id[:8]}"
        wt_result = self._worktree.create_worktree(
            name=worktree_name,
            branch=branch_name,
            from_branch=from_branch,
            env_files=env_files,
        )

        if wt_result.success and wt_result.path:
            session.worktree_path = wt_result.path
            session.worktree_branch = wt_result.branch
            session.resolved_working_dir = wt_result.path
            return wt_result.path

        return working_dir

    def _should_use_worktree(
        self,
        features: SessionFeatures | None,
        worktree_settings: WorktreeSettings | None,
    ) -> bool:
        """Determine if we should create a worktree for this session."""
        if features and features.use_worktree is not None:
            return features.use_worktree
        if worktree_settings:
            return worktree_settings.enabled
        return False

    def create_session_with_resume(
        self,
        name: str,
        resume_session_id: str,
        working_dir: Path | None = None,
    ) -> Session:
        """Create a new session that resumes an existing Claude session."""
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        resolved = self._config.resolve_features()
        effective_working_dir = working_dir or resolved.working_dir or self._fallback_working_dir

        session = Session(
            name=name,
            claude_session_id=resume_session_id,
            session_type=SessionType.CLAUDE,
            resolved_working_dir=effective_working_dir,
            resolved_model=resolved.model,
        )

        self._sessions[session.id] = session

        # Validate session file exists before attempting resume
        discovery = DiscoveryService(effective_working_dir)
        if not discovery.session_file_exists(resume_session_id, effective_working_dir):
            session.state = SessionState.FAILED
            session.error_message = f"Session file not found: {resume_session_id[:8]}..."
            self._emit(SessionCreated(session))
            self._persist_change(session, "created")
            return session

        command_args = self._commands.build_resume_command(resume_session_id, resolved.model)

        # Get OpenRouter proxy env vars if enabled
        env_vars = None
        if resolved.openrouter_proxy:
            env_vars = self._commands.build_openrouter_env_vars(resolved.openrouter_proxy)

        command = self._commands.wrap_with_banner(command_args, name, session.id, env_vars)

        tmux_name = self._tmux_name(session.id)
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=effective_working_dir,
        )

        session.state = SessionState.RUNNING if result.success else SessionState.FAILED
        if not result.success:
            session.error_message = result.error or "Failed to create tmux session"

        self._emit(SessionCreated(session))
        self._persist_change(session, "created")
        return session

    def revive_session(self, session_id: str) -> bool:
        """Revive a completed/failed/paused/killed session."""
        session = self._sessions.get(session_id)
        if not session or session.state == SessionState.RUNNING:
            return False

        was_failed = session.state == SessionState.FAILED
        if was_failed:
            session.error_message = None
            session.claude_session_id = ""

        # For non-failed Claude sessions, try to discover session ID
        if session.session_type == SessionType.CLAUDE and not was_failed:
            if not session.claude_session_id and session.resolved_working_dir:
                discovery = DiscoveryService(session.resolved_working_dir)
                sessions = discovery.list_claude_sessions(
                    project_path=session.resolved_working_dir,
                    limit=1,
                )
                if sessions:
                    session.claude_session_id = sessions[0].session_id

        command_args = self._commands.build_revive_command(session, was_failed)

        # Get OpenRouter proxy env vars if enabled for Claude sessions
        env_vars = None
        if session.session_type == SessionType.CLAUDE:
            resolved = self._config.resolve_features()
            if resolved.openrouter_proxy:
                env_vars = self._commands.build_openrouter_env_vars(resolved.openrouter_proxy)

        command = self._commands.wrap_with_banner(command_args, session.name, session.id, env_vars)

        tmux_name = self.get_tmux_session_name(session_id)
        if not tmux_name:
            return False

        # Clean up old tmux session if it exists
        if self._tmux.session_exists(tmux_name):
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        # Determine working directory
        working_dir = session.resolved_working_dir
        if not working_dir or not working_dir.exists():
            resolved = self._config.resolve_features()
            working_dir = resolved.working_dir or self._fallback_working_dir

        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=working_dir,
        )

        if result.success:
            session.state = SessionState.RUNNING
            session.ended_at = None
            session.revived_at = datetime.now()
            self._persist_change(session, "revived")
            return True

        return False

    def pause_session(self, session_id: str) -> bool:
        """Pause a session, preserving its worktree for later."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        tmux_name = self.get_tmux_session_name(session_id)
        if tmux_name:
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        session.state = SessionState.PAUSED
        session.ended_at = datetime.now()

        self._emit(SessionPaused(session_id))
        self._persist_change(session, "paused")
        return True

    def kill_session(self, session_id: str) -> bool:
        """Kill a session and remove its worktree."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        tmux_name = self.get_tmux_session_name(session_id)
        if tmux_name:
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        if session.worktree_path and self._worktree:
            self._worktree.remove_worktree(session.worktree_path, force=True)

        session.state = SessionState.KILLED
        session.ended_at = datetime.now()

        self._emit(SessionKilled(session_id))
        self._persist_change(session, "killed")
        return True

    def clean_session(self, session_id: str) -> bool:
        """Clean up a non-active session - remove worktree and from list."""
        session = self._sessions.get(session_id)
        if not session or session.is_active:
            return False

        if session.worktree_path and self._worktree:
            self._worktree.remove_worktree(session.worktree_path, force=True)

        record = self._persistence.session_to_record(session)
        del self._sessions[session_id]

        self._emit(SessionCleaned(session_id))
        self.save_state()
        self._state.append_history(record, "cleaned")
        return True

    def navigate_to_worktree(self, session_id: str) -> Session | None:
        """Create a new shell session in a paused session's worktree."""
        session = self._sessions.get(session_id)
        if not session or session.state != SessionState.PAUSED:
            return None
        if not session.worktree_path or not session.worktree_path.exists():
            return None

        new_features = SessionFeatures(working_dir=session.worktree_path)
        return self.create_session(
            name=f"{session.name} (resumed)",
            features=new_features,
            session_type=SessionType.SHELL,
        )

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """Rename a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        new_name = new_name.strip()
        if not new_name:
            return False

        session.name = new_name
        self._persist_change(session, "renamed")
        return True

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_output(self, session_id: str, lines: int = 100) -> str:
        """Get recent output from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return ""

        tmux_name = self.get_tmux_session_name(session_id)
        if not tmux_name:
            return ""

        result = self._tmux.capture_pane(tmux_name, lines=lines)
        return result.output if result.success else ""

    def update_session_tokens(self, session_id: str) -> bool:
        """Update token statistics for a Claude session."""
        session = self._sessions.get(session_id)
        if not session or session.session_type != SessionType.CLAUDE:
            return False
        if not session.claude_session_id:
            return False

        stats = self._token_parser.get_session_stats(
            claude_session_id=session.claude_session_id,
            working_dir=session.resolved_working_dir,
        )

        if stats:
            session.token_stats = stats.total_usage
            return True
        return False

    def refresh_states(self) -> None:
        """Update session states based on tmux status."""
        for session in self._sessions.values():
            if session.state != SessionState.RUNNING:
                continue

            tmux_name = self.get_tmux_session_name(session.id) or self._tmux_name(session.id)

            if not self._tmux.session_exists(tmux_name):
                session.state = SessionState.COMPLETED
                session.ended_at = datetime.now()
                session.revived_at = None
                continue

            # Grace period check
            if session.revived_at:
                grace_elapsed = (datetime.now() - session.revived_at).total_seconds()
                if grace_elapsed < 5.0:
                    continue
                session.revived_at = None

            if self._tmux.is_pane_dead(tmux_name):
                exit_status = self._tmux.get_pane_exit_status(tmux_name)
                if exit_status is not None and exit_status != 0:
                    session.state = SessionState.FAILED
                    session.error_message = f"Process exited with code {exit_status}"
                else:
                    session.state = SessionState.COMPLETED
                session.ended_at = datetime.now()

            if session.session_type == SessionType.CLAUDE:
                self.update_session_tokens(session.id)

    def count_by_state(self) -> tuple[int, int]:
        """Return (active_count, dead_count)."""
        active = sum(1 for s in self._sessions.values() if s.is_active)
        dead = sum(1 for s in self._sessions.values() if not s.is_active)
        return active, dead

    def kill_all_sessions(self) -> int:
        """Kill all sessions. Returns count killed."""
        count = 0
        for session_id in list(self._sessions.keys()):
            if self.kill_session(session_id):
                count += 1
        return count

    def kill_dead_sessions(self) -> int:
        """Kill only dead/completed sessions. Returns count killed."""
        count = 0
        for session in list(self._sessions.values()):
            if not session.is_active:
                tmux_name = self.get_tmux_session_name(session.id)
                if tmux_name and self._tmux.session_exists(tmux_name):
                    self._tmux.kill_session(tmux_name)
                    count += 1
        return count

    def cleanup_dead_tmux_sessions(self) -> int:
        """Clean up orphaned tmux sessions with dead panes."""
        prefix = f"{self._get_session_prefix()}-"
        return self._tmux.cleanup_dead_zen_sessions(prefix)

    def adopt_external_tmux(
        self,
        tmux_name: str,
        claude_session_id: str | None = None,
        working_dir: Path | None = None,
    ) -> Session:
        """Adopt an external tmux session into zen-portal management."""
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        # Check if already tracking this tmux session
        for existing in self._sessions.values():
            existing_tmux = self.get_tmux_session_name(existing.id)
            if existing_tmux == tmux_name:
                if self._tmux.session_exists(tmux_name) and self._tmux.is_pane_dead(tmux_name):
                    self.revive_session(existing.id)
                elif self._tmux.session_exists(tmux_name):
                    existing.state = SessionState.RUNNING
                return existing

        # Check if tracking by claude_session_id
        if claude_session_id:
            for existing in self._sessions.values():
                if existing.claude_session_id == claude_session_id:
                    existing._external_tmux_name = tmux_name
                    if working_dir:
                        existing.resolved_working_dir = working_dir
                    if self._tmux.session_exists(tmux_name) and self._tmux.is_pane_dead(tmux_name):
                        self.revive_session(existing.id)
                    elif self._tmux.session_exists(tmux_name):
                        existing.state = SessionState.RUNNING
                        existing.ended_at = None
                    return existing

        # Create new session
        session_type = SessionType.CLAUDE if claude_session_id else SessionType.SHELL
        session = Session(
            name=tmux_name,
            claude_session_id=claude_session_id or "",
            session_type=session_type,
            resolved_working_dir=working_dir,
        )
        session._external_tmux_name = tmux_name

        self._sessions[session.id] = session

        if self._tmux.session_exists(tmux_name):
            if self._tmux.is_pane_dead(tmux_name):
                session.state = SessionState.COMPLETED
            else:
                session.state = SessionState.RUNNING
        else:
            session.state = SessionState.FAILED

        self._emit(SessionCreated(session))
        return session

    def get_tmux_session_name(self, session_id: str) -> str | None:
        """Get the tmux session name for a zen-portal session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        if hasattr(session, "_external_tmux_name"):
            return session._external_tmux_name
        return self._tmux_name(session_id)

    def remove_session(self, session_id: str) -> bool:
        """Remove a session entirely."""
        if session_id not in self._sessions:
            return False
        session = self._sessions[session_id]
        if session.is_active:
            self.kill_session(session_id)
        del self._sessions[session_id]
        return True

    # -------------------------------------------------------------------------
    # Persistence helpers
    # -------------------------------------------------------------------------

    def save_state(self) -> bool:
        """Persist current session state to disk."""
        return self._persistence.save_state(self._sessions)

    def _persist_change(self, session: Session, event: str = "update") -> None:
        """Persist state after a session change."""
        self.save_state()
        self._persistence.append_history(session, event)

    def validate_proxy(
        self,
        settings: OpenRouterProxySettings | None = None,
    ) -> ProxyValidationResult | None:
        """Validate proxy configuration.

        Checks for common gotchas:
        - y-router: Docker not running, missing API key, wrong key format
        - CLIProxyAPI: Not running, not logged in
        - General: URL unreachable, port conflicts, missing credentials

        Args:
            settings: Proxy settings to validate. If None, uses resolved config.

        Returns:
            ProxyValidationResult with detailed check results, or None if proxy disabled.
        """
        if settings is None:
            resolved = self._config.resolve_features()
            settings = resolved.openrouter_proxy

        if not settings or not settings.enabled:
            return None

        validator = ProxyValidator(settings)
        return validator.validate_sync()

    def get_proxy_status(self) -> str:
        """Get a one-line proxy status for display.

        Returns:
            Status like "proxy: ready", "proxy: unreachable", or "proxy: disabled"
        """
        resolved = self._config.resolve_features()
        if not resolved.openrouter_proxy or not resolved.openrouter_proxy.enabled:
            return "proxy: disabled"

        result = self.validate_proxy(resolved.openrouter_proxy)
        if not result:
            return "proxy: disabled"

        if result.is_ok:
            from .config import ProxyAuthType
            auth_type = ProxyAuthType.normalize(resolved.openrouter_proxy.auth_type)
            auth_desc = {
                ProxyAuthType.OPENROUTER: "OpenRouter",
                ProxyAuthType.CLAUDE_ACCOUNT: "Claude Account",
            }.get(auth_type, "custom")
            return f"proxy: {auth_desc}"

        return f"proxy: {result.summary}"
