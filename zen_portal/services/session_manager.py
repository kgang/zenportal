"""SessionManager: Core session lifecycle management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from ..models.session import Session, SessionState, SessionFeatures, SessionType
from ..models.events import SessionCreated, SessionPaused, SessionKilled, SessionCleaned
from .tmux import TmuxService
from .config import ConfigManager, FeatureSettings, WorktreeSettings, OpenRouterProxySettings, ClaudeModel
from .worktree import WorktreeService
from .discovery import DiscoveryService
from .state import SessionRecord, PortalState
from .token_parser import TokenParser
from .session_commands import SessionCommandBuilder
from .proxy_validation import ProxyValidator, ProxyValidationResult
from .core import WorktreeManager, TokenManager, StateRefresher
from .pipelines import CreateContext, CreateSessionPipeline


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass


class ProxyConfigWarning(Exception):
    """Warning about proxy configuration issues (non-fatal)."""
    pass


class SessionManager:
    """Manages Claude Code sessions in tmux."""

    MAX_SESSIONS = 10
    STATE_FILE = "state.json"
    HISTORY_DIR = "history"

    def __init__(
        self,
        tmux: TmuxService,
        config_manager: ConfigManager,
        worktree_service: WorktreeService | None = None,
        working_dir: Path | None = None,
        on_event: Callable | None = None,
        base_dir: Path | None = None,
    ):
        self._tmux = tmux
        self._config = config_manager
        self._worktree = worktree_service
        self._fallback_working_dir = working_dir or Path.cwd()
        self._on_event = on_event
        self._sessions: dict[str, Session] = {}
        self._session_order: list[str] = []  # Custom display order
        self._commands = SessionCommandBuilder()

        # State persistence paths
        if base_dir:
            self._base_dir = base_dir
        else:
            self._base_dir = Path.home() / ".zen_portal"
        self._state_file = self._base_dir / self.STATE_FILE
        self._history_dir = self._base_dir / self.HISTORY_DIR

        # Initialize extracted managers
        self._worktree_mgr = WorktreeManager(worktree_service)
        self._token_mgr = TokenManager()
        self._state_refresher = StateRefresher(
            tmux=tmux,
            get_tmux_name=self.get_tmux_session_name,
            on_token_update=lambda s: self._token_mgr.update_session(s),
        )

        # Public access for screens that need direct manager access
        self.worktree = self._worktree_mgr
        self.tokens = self._token_mgr

        # Load persisted state on startup
        self._sessions, self._session_order = self._load_persisted_sessions_with_order()

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

    def set_session_order(self, order: list[str]) -> None:
        """Set custom session display order and persist."""
        self._session_order = order
        self._save_state_with_order(order)

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
            worktree_mgr=self._worktree_mgr,
            tmux_name_func=self._tmux_name,
            max_sessions=self.MAX_SESSIONS,
            current_count=len(self._sessions),
            fallback_dir=self._fallback_working_dir,
        )

        result = pipeline.invoke(ctx)

        if not result.ok:
            if "Maximum sessions" in result.error:
                raise SessionLimitError(result.error)
            # Create a failed session for other errors
            session = Session(
                name=name,
                state=SessionState.FAILED,
                error_message=result.error,
                session_type=session_type,
                provider=provider,
            )
            self._sessions[session.id] = session
            self._emit(SessionCreated(session))
            self._persist_change(session, "created")
            return session

        session = result.value
        self._sessions[session.id] = session
        self._emit(SessionCreated(session))
        self._persist_change(session, "created")
        return session

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
        session.tmux_name = tmux_name
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

        # For non-failed Claude AI sessions, try to discover session ID
        if session.session_type == SessionType.AI and session.provider == "claude" and not was_failed:
            if not session.claude_session_id and session.resolved_working_dir:
                discovery = DiscoveryService(session.resolved_working_dir)
                sessions = discovery.list_claude_sessions(
                    project_path=session.resolved_working_dir,
                    limit=1,
                )
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

        self._worktree_mgr.cleanup(session)

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

        self._worktree_mgr.cleanup(session)

        record = self._session_to_record(session)
        del self._sessions[session_id]

        self._emit(SessionCleaned(session_id))
        self._save_state()
        self._append_history(record, "cleaned")
        return True

    def navigate_to_worktree(self, session_id: str) -> Session | None:
        """Create a new shell session in a paused session's worktree."""
        session = self._sessions.get(session_id)
        if not session or not self._worktree_mgr.can_navigate(session):
            return None

        worktree_path = self._worktree_mgr.get_worktree_path(session)
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
    # State Persistence (merged from StateService)
    # -------------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> PortalState:
        """Load state from disk.

        Returns empty state if file doesn't exist or is corrupted.
        """
        if not self._state_file.exists():
            return PortalState()

        try:
            with open(self._state_file) as f:
                data = json.load(f)
            return PortalState.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted state - return empty
            return PortalState()

    def _save_state(self) -> bool:
        """Save state to disk atomically.

        Uses temp file + rename for atomic writes.
        Returns True on success.
        """
        self._ensure_dirs()

        records = [self._session_to_record(s) for s in self._sessions.values()]
        state = PortalState(sessions=records, session_order=self._session_order)
        state.last_updated = datetime.now().isoformat()

        # Write to temp file first
        temp_file = self._state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(state.to_dict(), f, indent=2)

            # Atomic rename
            temp_file.rename(self._state_file)
            return True
        except OSError:
            # Clean up temp file if it exists
            if temp_file.exists():
                temp_file.unlink()
            return False

    def _save_state_with_order(self, order: list[str]) -> bool:
        """Save state with custom order."""
        self._session_order = order
        return self._save_state()

    def _append_history(self, record: SessionRecord, event: str = "update") -> None:
        """Append a session event to today's history log.

        History is stored as JSONL (one JSON object per line) for easy
        streaming reads and appends.

        Args:
            record: Session record to log
            event: Event type (created, updated, ended, cleaned)
        """
        self._ensure_dirs()

        today = datetime.now().strftime("%Y-%m-%d")
        history_file = self._history_dir / f"{today}.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "session": record.to_dict(),
        }

        try:
            with open(history_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # History is optional, don't fail on errors

    def _session_to_record(self, session: Session) -> SessionRecord:
        """Convert a Session to a persistable record."""
        external_name = None
        if hasattr(session, "_external_tmux_name"):
            external_name = session._external_tmux_name

        # Extract token stats if available
        input_tokens = 0
        output_tokens = 0
        cache_tokens = 0
        if session.token_stats:
            input_tokens = session.token_stats.input_tokens
            output_tokens = session.token_stats.output_tokens
            cache_tokens = session.token_stats.cache_tokens

        return SessionRecord(
            id=session.id,
            name=session.name,
            session_type=session.session_type.value,
            provider=session.provider,
            state=session.state.value,
            created_at=session.created_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            claude_session_id=session.claude_session_id,
            worktree_path=str(session.worktree_path) if session.worktree_path else None,
            worktree_branch=session.worktree_branch,
            working_dir=str(session.resolved_working_dir) if session.resolved_working_dir else None,
            model=session.resolved_model.value if session.resolved_model else None,
            external_tmux_name=external_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_tokens=cache_tokens,
            message_count=session.message_count,
            uses_proxy=session.uses_proxy,
            token_history=session.token_history,
        )

    def _session_from_record(self, record: SessionRecord) -> Session | None:
        """Reconstruct a Session from a persisted record.

        Returns None if the session should not be restored (no valid resources).
        """
        # Parse state
        try:
            state = SessionState(record.state)
        except ValueError:
            state = SessionState.COMPLETED

        # Parse session type
        try:
            session_type = SessionType(record.session_type)
        except ValueError:
            session_type = SessionType.AI

        # Parse created_at
        try:
            created_at = datetime.fromisoformat(record.created_at)
        except ValueError:
            created_at = datetime.now()

        # Parse ended_at
        ended_at = None
        if record.ended_at:
            try:
                ended_at = datetime.fromisoformat(record.ended_at)
            except ValueError:
                pass

        # Determine tmux name for this session
        if record.external_tmux_name:
            tmux_name = record.external_tmux_name
        else:
            tmux_name = self._tmux_name(record.id)

        # Check if tmux session still exists
        tmux_exists = self._tmux.session_exists(tmux_name)
        tmux_dead = tmux_exists and self._tmux.is_pane_dead(tmux_name)

        # Check if worktree still exists
        worktree_exists = (
            record.worktree_path
            and Path(record.worktree_path).exists()
        )

        # Decide whether to restore this session
        # Restore if: tmux exists (alive or dead) OR worktree exists
        if not tmux_exists and not worktree_exists:
            return None

        # Reconstruct session
        session = Session(
            name=record.name,
            claude_session_id=record.claude_session_id,
            session_type=session_type,
            provider=record.provider,
            created_at=created_at,
            ended_at=ended_at,
            resolved_working_dir=Path(record.working_dir) if record.working_dir else None,
            worktree_path=Path(record.worktree_path) if record.worktree_path else None,
            worktree_branch=record.worktree_branch,
            uses_proxy=record.uses_proxy,
            message_count=record.message_count,
            token_history=record.token_history,
        )

        # Override the auto-generated ID with the persisted one
        session.id = record.id

        # Set tmux name (computed or external)
        session.tmux_name = tmux_name
        if record.external_tmux_name:
            session._external_tmux_name = record.external_tmux_name

        # Set model if available
        if record.model:
            try:
                session.resolved_model = ClaudeModel(record.model)
            except ValueError:
                pass

        # Update state based on current tmux status
        if tmux_exists and not tmux_dead:
            session.state = SessionState.RUNNING
        elif state == SessionState.PAUSED:
            # Keep paused state if worktree exists
            session.state = SessionState.PAUSED if worktree_exists else SessionState.COMPLETED
        elif state == SessionState.KILLED:
            session.state = SessionState.KILLED
        else:
            session.state = SessionState.COMPLETED

        return session

    def _load_persisted_sessions_with_order(self) -> tuple[dict[str, Session], list[str]]:
        """Load sessions and custom order from persisted state.

        Returns:
            Tuple of (sessions dict, session order list)
        """
        state = self._load_state()
        sessions = {}

        for record in state.sessions:
            session = self._session_from_record(record)
            if session:
                sessions[session.id] = session

        # Filter order to only include existing sessions
        order = [sid for sid in state.session_order if sid in sessions]
        return sessions, order

    def _persist_change(self, session: Session, event: str = "update") -> None:
        """Persist state after a session change."""
        self._save_state()
        record = self._session_to_record(session)
        self._append_history(record, event)

    # Public interface (for backward compatibility and tests)
    def save_state(self) -> bool:
        """Persist current session state to disk."""
        return self._save_state()

    @property
    def base_dir(self) -> Path:
        """Get the base directory path."""
        return self._base_dir

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
