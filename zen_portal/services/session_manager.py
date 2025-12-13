"""SessionManager: Core session lifecycle management."""

import logging
from datetime import datetime
from pathlib import Path

from ..models.session import Session, SessionState, SessionFeatures, SessionType
from .tmux import TmuxService
from .config import ConfigManager, FeatureSettings, WorktreeSettings, OpenRouterProxySettings, ClaudeModel
from .worktree import WorktreeService
from .discovery import DiscoveryService
from .session_state import SessionStateService
from .session_commands import SessionCommandBuilder
from .proxy_validation import ProxyValidator, ProxyValidationResult
from .core import TokenManager, StateRefresher
from .pipelines import CreateContext, CreateSessionPipeline
from .events import (
    EventBus,
    SessionCreatedEvent,
    SessionStateChangedEvent,
    SessionPausedEvent,
    SessionKilledEvent,
    SessionCleanedEvent,
)


logger = logging.getLogger(__name__)


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass


class ProxyConfigWarning(Exception):
    """Warning about proxy configuration issues (non-fatal)."""
    pass


class SessionManager:
    """Manages Claude Code sessions in tmux."""

    STATE_FILE = "state.json"
    HISTORY_DIR = "history"

    def __init__(
        self,
        tmux: TmuxService,
        config_manager: ConfigManager,
        worktree_service: WorktreeService | None = None,
        working_dir: Path | None = None,
        base_dir: Path | None = None,
        state_service: SessionStateService | None = None,
        event_bus: EventBus | None = None,
    ):
        self._tmux = tmux
        self._config = config_manager
        self._worktree = worktree_service
        self._fallback_working_dir = working_dir or Path.cwd()
        self._bus = event_bus or EventBus.get()
        self._sessions: dict[str, Session] = {}
        self._session_order: list[str] = []  # Custom display order
        self._selected_session_id: str | None = None  # Cursor position
        self._commands = SessionCommandBuilder()

        # State persistence service (injected or created)
        if base_dir:
            self._base_dir = base_dir
        else:
            self._base_dir = Path.home() / ".zen_portal"

        self._state = state_service or SessionStateService(self._base_dir)

        # Initialize extracted managers
        self._token_mgr = TokenManager()
        self._state_refresher = StateRefresher(
            tmux=tmux,
            get_tmux_name=self.get_tmux_session_name,
            on_token_update=lambda s: self._token_mgr.update_session(s),
        )

        # Public access for screens that need direct manager access
        self.tokens = self._token_mgr

        # Load persisted state on startup
        self._sessions, self._session_order, self._selected_session_id = (
            self._load_persisted_state()
        )

    @property
    def sessions(self) -> list[Session]:
        """All sessions in custom order (or by creation time if no custom order)."""
        if self._session_order:
            # Use custom order, with any new sessions at the top
            by_id = {s.id: s for s in self._sessions.values()}
            ordered = []
            for sid in self._session_order:
                if sid in by_id:
                    ordered.append(by_id.pop(sid))
            # New sessions not in order go to top (newest first)
            new_sessions = sorted(by_id.values(), key=lambda s: s.created_at, reverse=True)
            return new_sessions + ordered
        return sorted(
            self._sessions.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )

    @property
    def session_order(self) -> list[str]:
        """Get the custom session order."""
        return self._session_order

    @property
    def selected_session_id(self) -> str | None:
        """Get the last selected session ID (cursor position)."""
        return self._selected_session_id

    def set_session_order(self, order: list[str]) -> None:
        """Set custom session display order and persist."""
        self._session_order = order
        self._save_state()

    def set_selected_session(self, session_id: str | None) -> None:
        """Set the selected session (cursor position) and persist."""
        self._selected_session_id = session_id
        self._save_state()

    def _emit_created(self, session: Session) -> None:
        """Emit session created event via EventBus."""
        self._bus.emit(SessionCreatedEvent(
            session_id=session.id,
            session_name=session.name,
            session_type=session.session_type.value,
        ))

    def _emit_state_changed(self, session: Session, old_state: SessionState) -> None:
        """Emit session state changed event via EventBus."""
        self._bus.emit(SessionStateChangedEvent(
            session_id=session.id,
            old_state=old_state.value,
            new_state=session.state.value,
        ))

    def _emit_paused(self, session_id: str) -> None:
        """Emit session paused event via EventBus."""
        self._bus.emit(SessionPausedEvent(session_id=session_id))

    def _emit_killed(self, session_id: str) -> None:
        """Emit session killed event via EventBus."""
        self._bus.emit(SessionKilledEvent(session_id=session_id))

    def _emit_cleaned(self, session_id: str) -> None:
        """Emit session cleaned event via EventBus."""
        self._bus.emit(SessionCleanedEvent(session_id=session_id))

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
        session_type: SessionType = SessionType.AI,
        provider: str = "claude",
    ) -> Session:
        """Create a new session via pipeline.

        Args:
            name: Display name for the session
            prompt: Optional initial prompt (AI sessions only)
            features: Optional session-level feature overrides
            session_type: Type of session to create (AI or SHELL)
            provider: AI provider (claude, codex, gemini, openrouter) for AI sessions

        Returns:
            The created Session
        """
        ctx = CreateContext(
            name=name,
            prompt=prompt,
            session_type=session_type,
            provider=provider,
            features=features,
        )

        pipeline = CreateSessionPipeline(
            tmux=self._tmux,
            config_manager=self._config,
            commands=self._commands,
            worktree_service=self._worktree,
            tmux_name_func=self._tmux_name,
            fallback_dir=self._fallback_working_dir,
        )

        result = pipeline.invoke(ctx)

        if not result.ok:
            # Create a failed session for other errors
            session = Session(
                name=name,
                state=SessionState.FAILED,
                error_message=result.error,
                session_type=session_type,
                provider=provider,
            )
            self._sessions[session.id] = session
            self._emit_created(session)
            self._persist_change(session, "created")
            return session

        session = result.value
        self._sessions[session.id] = session
        self._emit_created(session)
        self._persist_change(session, "created")
        return session

    def create_session_with_resume(
        self,
        name: str,
        resume_session_id: str,
        working_dir: Path | None = None,
    ) -> Session:
        """Create a new session that resumes an existing Claude session."""

        resolved = self._config.resolve_features()
        effective_working_dir = working_dir or resolved.working_dir or self._fallback_working_dir

        session = Session(
            name=name,
            claude_session_id=resume_session_id,
            session_type=SessionType.AI,
            provider="claude",
            resolved_working_dir=effective_working_dir,
            resolved_model=resolved.model,
        )

        self._sessions[session.id] = session

        # Validate session file exists before attempting resume
        discovery = DiscoveryService(effective_working_dir)
        if not discovery.session_file_exists(resume_session_id, effective_working_dir):
            session.state = SessionState.FAILED
            session.error_message = f"Session file not found: {resume_session_id[:8]}..."
            self._emit_created(session)
            self._persist_change(session, "created")
            return session

        command_args = self._commands.build_resume_command(resume_session_id, resolved.model)

        # Get OpenRouter proxy env vars if enabled
        env_vars = None
        if resolved.openrouter_proxy:
            env_vars = self._commands.build_openrouter_env_vars(resolved.openrouter_proxy)

        command = self._commands.wrap_with_banner(command_args, name, session.id, env_vars)

        tmux_name = self._tmux_name(session.id)
        session.tmux_name = tmux_name
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=effective_working_dir,
        )

        session.state = SessionState.RUNNING if result.success else SessionState.FAILED
        if not result.success:
            session.error_message = result.error or "Failed to create tmux session"

        self._emit_created(session)
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

        # For non-failed Claude AI sessions, try to discover session ID
        if session.session_type == SessionType.AI and session.provider == "claude" and not was_failed:
            if not session.claude_session_id and session.resolved_working_dir:
                discovery = DiscoveryService(session.resolved_working_dir)
                sessions = discovery.list_claude_sessions(
                    project_path=session.resolved_working_dir,
                    limit=5,
                )
                # Find the most recent session modified after this zenportal session started
                # This prevents reviving the wrong claude session when multiple exist
                for claude_session in sessions:
                    if claude_session.modified_at >= session.created_at:
                        session.claude_session_id = claude_session.session_id
                        break
                else:
                    # Fallback to most recent if none match the time window
                    if sessions:
                        session.claude_session_id = sessions[0].session_id

        command_args = self._commands.build_revive_command(session, was_failed)

        # Get OpenRouter proxy env vars if enabled for Claude AI sessions
        env_vars = None
        if session.session_type == SessionType.AI and session.provider == "claude":
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

        self._emit_paused(session_id)
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

        # Cleanup worktree if service is available
        if self._worktree and session.worktree_path:
            self._worktree.cleanup_session(session)

        session.state = SessionState.KILLED
        session.ended_at = datetime.now()

        self._emit_killed(session_id)
        self._persist_change(session, "killed")
        return True

    def clean_session(self, session_id: str) -> bool:
        """Clean up a non-active session - remove worktree and from list."""
        session = self._sessions.get(session_id)
        if not session or session.is_active:
            return False

        # Cleanup worktree if service is available
        if self._worktree and session.worktree_path:
            self._worktree.cleanup_session(session)

        del self._sessions[session_id]

        self._emit_cleaned(session_id)
        self._save_state()
        self._state.append_history(session, "cleaned")
        return True

    def navigate_to_worktree(self, session_id: str) -> Session | None:
        """Create a new shell session in a paused session's worktree."""
        session = self._sessions.get(session_id)
        if not session or not self._worktree:
            return None

        if not self._worktree.can_navigate_to_session(session):
            return None

        worktree_path = self._worktree.get_session_worktree_path(session)
        if not worktree_path:
            return None

        new_features = SessionFeatures(working_dir=worktree_path)
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
        """Update token statistics and history for a Claude session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        return self._token_mgr.update_session(session)

    def refresh_states(self) -> None:
        """Update session states based on tmux status."""
        self._state_refresher.refresh(self._sessions)

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
                    existing.tmux_name = tmux_name
                    if working_dir:
                        existing.resolved_working_dir = working_dir
                    if self._tmux.session_exists(tmux_name) and self._tmux.is_pane_dead(tmux_name):
                        self.revive_session(existing.id)
                    elif self._tmux.session_exists(tmux_name):
                        existing.state = SessionState.RUNNING
                        existing.ended_at = None
                    return existing

        # Create new session
        if claude_session_id:
            session_type = SessionType.AI
            provider = "claude"
        else:
            session_type = SessionType.SHELL
            provider = "claude"

        session = Session(
            name=tmux_name,
            claude_session_id=claude_session_id or "",
            session_type=session_type,
            provider=provider,
            resolved_working_dir=working_dir,
        )
        session._external_tmux_name = tmux_name
        session.tmux_name = tmux_name

        self._sessions[session.id] = session

        if self._tmux.session_exists(tmux_name):
            # Configure the session for zen-portal management
            self._tmux.configure_session(tmux_name)

            if self._tmux.is_pane_dead(tmux_name):
                session.state = SessionState.COMPLETED
            else:
                session.state = SessionState.RUNNING
        else:
            session.state = SessionState.FAILED

        self._emit_created(session)
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
    # State Persistence (delegates to SessionStateService)
    # -------------------------------------------------------------------------

    def _save_state(self) -> bool:
        """Save state to disk atomically."""
        sessions = list(self._sessions.values())
        return self._state.save(
            sessions,
            self._session_order,
            self._selected_session_id,
        )

    def _load_persisted_state(self) -> tuple[dict[str, Session], list[str], str | None]:
        """Load sessions, order, and cursor position from persisted state.

        Returns:
            Tuple of (sessions dict, session order list, selected session ID)
        """
        state = self._state.load()
        sessions = {}

        for record in state.sessions:
            session = self._state.session_from_record(
                record,
                tmux_name_func=self._tmux_name,
                tmux_exists_func=self._tmux.session_exists,
                is_pane_dead_func=self._tmux.is_pane_dead,
            )
            if session:
                sessions[session.id] = session

        # Filter order to only include existing sessions
        order = [sid for sid in state.session_order if sid in sessions]

        # Validate selected session still exists
        selected = state.selected_session_id
        if selected and selected not in sessions:
            selected = None

        return sessions, order, selected

    def _persist_change(self, session: Session, event: str = "update") -> None:
        """Persist state after a session change."""
        self._save_state()
        self._state.append_history(session, event)

    # Public interface (for backward compatibility and tests)
    def save_state(self) -> bool:
        """Persist current session state to disk."""
        return self._save_state()

    @property
    def base_dir(self) -> Path:
        """Get the base directory path."""
        return self._state.base_dir

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
            return "proxy: y-router"

        return f"proxy: {result.summary}"
