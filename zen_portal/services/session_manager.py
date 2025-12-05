"""SessionManager: Simple session lifecycle management."""

import shlex
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models.session import Session, SessionState, SessionFeatures, SessionType
from ..models.events import SessionCreated, SessionPaused, SessionKilled, SessionCleaned
from .tmux import TmuxService
from .config import ConfigManager, FeatureSettings, WorktreeSettings
from .worktree import WorktreeService
from .banner import generate_banner_command
from .discovery import DiscoveryService
from .state import StateService, PortalState, SessionRecord


class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""

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
        # Fallback working dir (only used if no config/portal/session override)
        self._fallback_working_dir = working_dir or Path.cwd()
        self._on_event = on_event
        self._state = state_service or StateService()
        self._sessions: dict[str, Session] = {}

        # Load persisted state on startup
        self._load_persisted_state()

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
        """Create a new session (Claude Code or shell).

        Args:
            name: Display name for the session
            prompt: Optional initial prompt for Claude (interactive mode, Claude only)
            features: Optional session-level feature overrides
            session_type: Type of session (CLAUDE or SHELL)

        Returns:
            The created Session
        """
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        # Convert SessionFeatures to FeatureSettings for resolution
        session_override = None
        if features and features.has_overrides():
            session_override = FeatureSettings(
                working_dir=features.working_dir,
                model=features.model if session_type == SessionType.CLAUDE else None,
            )

        # Resolve features through all tiers
        resolved = self._config.resolve_features(session_override)

        # Start with resolved working directory
        working_dir = resolved.working_dir or self._fallback_working_dir

        # Determine if dangerous mode is enabled
        dangerous_mode = features.dangerously_skip_permissions if features else False

        # Create session model (we'll update worktree info after creation attempt)
        session = Session(
            name=name,
            prompt=prompt if session_type == SessionType.CLAUDE else "",
            session_type=session_type,
            features=features or SessionFeatures(),
            resolved_working_dir=working_dir,
            resolved_model=resolved.model if session_type == SessionType.CLAUDE else None,
            dangerously_skip_permissions=dangerous_mode,
        )

        # Determine if we should create a worktree
        use_worktree = self._should_use_worktree(features, resolved.worktree)

        if use_worktree and self._worktree:
            # Determine branch name
            branch_name = None
            if features and features.worktree_branch:
                branch_name = features.worktree_branch
            # If no explicit branch, create_worktree will use the worktree name

            # Determine from_branch
            from_branch = "main"
            if resolved.worktree and resolved.worktree.default_from_branch:
                from_branch = resolved.worktree.default_from_branch

            # Determine env files to symlink
            env_files = None
            if resolved.worktree and resolved.worktree.env_files:
                env_files = resolved.worktree.env_files

            # Create worktree
            worktree_name = f"{name}-{session.id[:8]}"
            wt_result = self._worktree.create_worktree(
                name=worktree_name,
                branch=branch_name,
                from_branch=from_branch,
                env_files=env_files,
            )

            if wt_result.success and wt_result.path:
                # Use worktree as working directory
                working_dir = wt_result.path
                session.worktree_path = wt_result.path
                session.worktree_branch = wt_result.branch
                session.resolved_working_dir = working_dir
            # If worktree creation fails, we fall back to regular working_dir
            # No error raised - graceful degradation

        self._sessions[session.id] = session

        # Build command based on session type
        if session_type == SessionType.CLAUDE:
            # Build claude command - don't specify session ID, let Claude generate it
            # We'll discover the session ID later for revival
            command_args = ["claude"]
            if resolved.model:
                command_args.extend(["--model", resolved.model.value])
            if dangerous_mode:
                command_args.append("--dangerously-skip-permissions")
            if prompt:
                command_args.append(prompt)
            # Clear the pre-generated session ID since we're not using it
            session.claude_session_id = ""
        elif session_type == SessionType.CODEX:
            # Codex session
            command_args = ["codex"]
            if prompt:
                command_args.append(prompt)
        else:
            # Shell session - start user's default shell (zsh) with login profile
            command_args = ["zsh", "-l"]

        # Wrap command with banner
        command = self._wrap_with_banner(command_args, name, session.id)

        # Create tmux session
        tmux_name = self._tmux_name(session.id)
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=working_dir,
        )

        if result.success:
            session.state = SessionState.GROWING
        else:
            session.state = SessionState.WILTED

        self._emit(SessionCreated(session))
        self._persist_session_change(session, "created")
        return session

    def create_session_with_resume(
        self,
        name: str,
        resume_session_id: str,
        working_dir: Path | None = None,
    ) -> Session:
        """Create a new session that resumes an existing Claude session.

        Args:
            name: Display name for the session
            resume_session_id: Claude session ID to resume
            working_dir: Optional working directory override

        Returns:
            The created Session
        """
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        # Resolve working directory
        resolved = self._config.resolve_features()
        effective_working_dir = working_dir or resolved.working_dir or self._fallback_working_dir

        # Create session model
        session = Session(
            name=name,
            claude_session_id=resume_session_id,
            session_type=SessionType.CLAUDE,
            resolved_working_dir=effective_working_dir,
            resolved_model=resolved.model,
        )

        self._sessions[session.id] = session

        # Build claude resume command
        claude_args = ["claude", "--resume", resume_session_id]
        if resolved.model:
            claude_args.extend(["--model", resolved.model.value])

        # Wrap command with banner
        command = self._wrap_with_banner(claude_args, name, session.id)

        # Create tmux session
        tmux_name = self._tmux_name(session.id)
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=effective_working_dir,
        )

        if result.success:
            session.state = SessionState.GROWING
        else:
            session.state = SessionState.WILTED

        self._emit(SessionCreated(session))
        self._persist_session_change(session, "created")
        return session

    def _should_use_worktree(
        self,
        features: SessionFeatures | None,
        worktree_settings: WorktreeSettings | None,
    ) -> bool:
        """Determine if we should create a worktree for this session.

        Session-level use_worktree takes precedence, then config/portal settings.
        """
        # Session-level explicit override
        if features and features.use_worktree is not None:
            return features.use_worktree

        # Fall back to config/portal settings
        if worktree_settings:
            return worktree_settings.enabled

        return False

    def _wrap_with_banner(
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

    def revive_session(self, session_id: str) -> bool:
        """Revive a bloomed/wilted/paused/killed session.

        For Claude sessions: uses --resume to continue the same session
        For shell sessions: restarts the shell with original configuration

        Returns True if successful.
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.state == SessionState.GROWING:
            return False  # Already running

        # Build command based on session type
        if session.session_type == SessionType.SHELL:
            # Shell session - just restart the shell
            command_args = ["zsh", "-l"]
        elif session.session_type == SessionType.CODEX:
            # Codex session
            command_args = ["codex"]
        else:
            # Claude session - need to discover or use known session ID
            claude_session_id = session.claude_session_id

            # If we don't have a session ID, try to discover it from the project folder
            if not claude_session_id and session.resolved_working_dir:
                discovery = DiscoveryService(session.resolved_working_dir)
                sessions = discovery.list_claude_sessions(
                    project_path=session.resolved_working_dir,
                    limit=1,
                )
                if sessions:
                    claude_session_id = sessions[0].session_id
                    # Store it for future revivals
                    session.claude_session_id = claude_session_id

            if claude_session_id:
                # Use --resume with the discovered/known session ID
                command_args = ["claude", "--resume", claude_session_id]
            else:
                # No session ID found - use --continue to resume most recent
                command_args = ["claude", "--continue"]

            if session.resolved_model:
                command_args.extend(["--model", session.resolved_model.value])
            if session.dangerously_skip_permissions:
                command_args.append("--dangerously-skip-permissions")

        # Wrap with banner
        command = self._wrap_with_banner(command_args, session.name, session.id)

        # Get correct tmux name (handles adopted external sessions)
        tmux_name = self.get_tmux_session_name(session.id)
        if not tmux_name:
            return False

        # Clean up old tmux session if it exists (clear history and kill)
        if self._tmux.session_exists(tmux_name):
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        # Determine working directory - fall back if original no longer exists
        # (e.g., worktree was deleted on kill)
        working_dir = session.resolved_working_dir
        if not working_dir or not working_dir.exists():
            # Try config-resolved working dir, then fallback
            resolved = self._config.resolve_features()
            working_dir = resolved.working_dir or self._fallback_working_dir

        # Create new tmux session
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=working_dir,
        )

        if result.success:
            session.state = SessionState.GROWING
            session.ended_at = None
            session.revived_at = datetime.now()  # Grace period for startup
            self._persist_session_change(session, "revived")
            return True

        return False

    def pause_session(self, session_id: str) -> bool:
        """Pause a session, preserving its worktree for later.

        This ends the tmux session but keeps the git worktree intact,
        allowing the user to resume work later via 'w' key.

        Args:
            session_id: ID of the session to pause
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        tmux_name = self.get_tmux_session_name(session_id)
        if tmux_name:
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        # Mark as paused (worktree preserved)
        session.state = SessionState.PAUSED
        session.ended_at = datetime.now()

        self._emit(SessionPaused(session_id))
        self._persist_session_change(session, "paused")
        return True

    def kill_session(self, session_id: str) -> bool:
        """Kill a session and remove its worktree.

        This ends the tmux session and removes the git worktree.
        Use pause_session() if you want to preserve the worktree.

        Args:
            session_id: ID of the session to kill
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        tmux_name = self.get_tmux_session_name(session_id)
        if tmux_name:
            self._tmux.clear_history(tmux_name)
            self._tmux.kill_session(tmux_name)

        # Clean up worktree if it exists
        if session.worktree_path and self._worktree:
            self._worktree.remove_worktree(session.worktree_path, force=True)

        session.state = SessionState.KILLED
        session.ended_at = datetime.now()

        self._emit(SessionKilled(session_id))
        self._persist_session_change(session, "killed")
        return True

    def clean_session(self, session_id: str) -> bool:
        """Clean up a non-active session - remove worktree and session from list.

        Use this to fully clean up ended sessions, removing both
        the worktree (if any) and the session from the zen portal listing.

        Args:
            session_id: ID of the session to clean (must not be active)
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        if session.is_active:
            return False

        # Remove the worktree if it exists
        if session.worktree_path and self._worktree:
            self._worktree.remove_worktree(session.worktree_path, force=True)

        # Create record before deletion for history
        record = self._session_to_record(session)

        # Remove session from listing
        del self._sessions[session_id]

        self._emit(SessionCleaned(session_id))

        # Persist state and history
        self.save_state()
        self._state.append_history(record, "cleaned")
        return True

    def navigate_to_worktree(self, session_id: str) -> Session | None:
        """Create a new shell session in a paused session's worktree.

        Args:
            session_id: ID of the paused session with a preserved worktree

        Returns:
            New Session if successful, None if not possible
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        if session.state != SessionState.PAUSED:
            return None

        if not session.worktree_path or not session.worktree_path.exists():
            return None

        # Create a new shell session in the worktree directory
        new_features = SessionFeatures(working_dir=session.worktree_path)
        new_session = self.create_session(
            name=f"{session.name} (resumed)",
            features=new_features,
            session_type=SessionType.SHELL,
        )

        return new_session

    def remove_session(self, session_id: str) -> bool:
        """Remove a session entirely."""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        if session.is_active:
            self.kill_session(session_id)

        del self._sessions[session_id]
        return True

    def get_output(self, session_id: str, lines: int = 100) -> str:
        """Get recent output from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return ""

        tmux_name = self.get_tmux_session_name(session_id)
        if not tmux_name:
            return ""
        result = self._tmux.capture_pane(tmux_name, lines=lines)

        if result.success:
            return result.output
        return ""

    def refresh_states(self) -> None:
        """Update session states based on tmux status.

        Detects:
        - Session tmux no longer exists -> BLOOMED
        - Session tmux exists but pane is dead -> BLOOMED

        Note: Recently revived sessions get a 5-second grace period before
        dead pane detection kicks in, allowing Claude to start up.
        """
        for session in self._sessions.values():
            if session.state != SessionState.GROWING:
                continue

            # Get the correct tmux name (handles external sessions)
            tmux_name = self.get_tmux_session_name(session.id)
            if not tmux_name:
                tmux_name = self._tmux_name(session.id)

            # Check if tmux session exists at all
            if not self._tmux.session_exists(tmux_name):
                session.state = SessionState.BLOOMED
                session.ended_at = datetime.now()
                session.revived_at = None
                continue

            # Check if pane is dead (process exited but tmux session remains)
            # Skip this check during the grace period after revive (5 seconds)
            if session.revived_at:
                grace_elapsed = (datetime.now() - session.revived_at).total_seconds()
                if grace_elapsed < 5.0:
                    continue  # Still in grace period, don't check pane_dead
                else:
                    session.revived_at = None  # Grace period expired

            if self._tmux.is_pane_dead(tmux_name):
                session.state = SessionState.BLOOMED
                session.ended_at = datetime.now()

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def count_by_state(self) -> tuple[int, int]:
        """Return (active_count, dead_count)."""
        active = sum(1 for s in self._sessions.values() if s.is_active)
        dead = sum(1 for s in self._sessions.values() if not s.is_active)
        return active, dead

    def kill_all_sessions(self) -> int:
        """Kill all tmux sessions and remove worktrees. Returns count killed."""
        count = 0
        for session_id in list(self._sessions.keys()):
            if self.kill_session(session_id):
                count += 1
        return count

    def kill_dead_sessions(self) -> int:
        """Kill only dead/bloomed sessions. Returns count killed."""
        count = 0
        for session in list(self._sessions.values()):
            if not session.is_active:
                tmux_name = self.get_tmux_session_name(session.id)
                if tmux_name and self._tmux.session_exists(tmux_name):
                    self._tmux.kill_session(tmux_name)
                    count += 1
        return count

    def cleanup_dead_tmux_sessions(self) -> int:
        """Clean up any orphaned tmux sessions with dead panes.

        This finds tmux sessions matching our prefix that have dead panes
        and kills them. Useful on exit to clean up stale sessions.

        Returns the number of sessions cleaned up.
        """
        prefix = f"{self._get_session_prefix()}-"
        return self._tmux.cleanup_dead_zen_sessions(prefix)

    def adopt_external_tmux(
        self,
        tmux_name: str,
        claude_session_id: str | None = None,
        working_dir: Path | None = None,
    ) -> Session:
        """Adopt an external tmux session into zen-portal management.

        Creates a Session that tracks the external tmux session. The session
        won't be renamed - it keeps its original tmux name.

        If the external session has a Claude session ID that matches an existing
        zen-portal session, updates that session to point to the new tmux session
        instead of creating a duplicate.

        Args:
            tmux_name: Name of the existing tmux session
            claude_session_id: Claude session ID if Claude is running
            working_dir: Working directory of the tmux session

        Returns:
            The created Session (or existing session if matched)
        """
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(f"Maximum sessions ({self.MAX_SESSIONS}) reached")

        # Check if we already track this tmux session by name
        for existing in self._sessions.values():
            existing_tmux = self.get_tmux_session_name(existing.id)
            if existing_tmux == tmux_name:
                # If pane is dead, revive the session
                if self._tmux.session_exists(tmux_name) and self._tmux.is_pane_dead(tmux_name):
                    self.revive_session(existing.id)
                elif self._tmux.session_exists(tmux_name):
                    existing.state = SessionState.GROWING
                return existing

        # Check if we already track this Claude session by claude_session_id
        # This handles the case where user resumed a Claude session in a new tmux
        if claude_session_id:
            for existing in self._sessions.values():
                if existing.claude_session_id == claude_session_id:
                    # Found matching Claude session - update to use new tmux session
                    existing._external_tmux_name = tmux_name
                    if working_dir:
                        existing.resolved_working_dir = working_dir
                    # If pane is dead, revive the session
                    if self._tmux.session_exists(tmux_name) and self._tmux.is_pane_dead(tmux_name):
                        self.revive_session(existing.id)
                    elif self._tmux.session_exists(tmux_name):
                        existing.state = SessionState.GROWING
                        existing.ended_at = None
                    return existing

        # Determine session type based on Claude detection
        session_type = SessionType.CLAUDE if claude_session_id else SessionType.SHELL

        # Create session model
        session = Session(
            name=tmux_name,
            claude_session_id=claude_session_id or "",
            session_type=session_type,
            resolved_working_dir=working_dir,
            # Mark that this is an adopted session (external tmux name)
            # We store the external tmux name so we can map back to it
        )

        # Override the ID to match the tmux name for lookup purposes
        # This is a bit of a hack but keeps the mapping simple
        session._external_tmux_name = tmux_name

        self._sessions[session.id] = session

        # Check initial state
        if self._tmux.session_exists(tmux_name):
            if self._tmux.is_pane_dead(tmux_name):
                session.state = SessionState.BLOOMED
            else:
                session.state = SessionState.GROWING
        else:
            session.state = SessionState.WILTED

        self._emit(SessionCreated(session))
        return session

    def get_tmux_session_name(self, session_id: str) -> str | None:
        """Get the tmux session name for a zen-portal session.

        Handles both managed sessions (zen-xxx) and adopted external sessions.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Check if this is an adopted external session
        if hasattr(session, "_external_tmux_name"):
            return session._external_tmux_name

        return self._tmux_name(session_id)

    # -------------------------------------------------------------------------
    # State Persistence
    # -------------------------------------------------------------------------

    def _load_persisted_state(self) -> None:
        """Load sessions from persisted state on startup.

        Only restores sessions that still have valid tmux sessions or worktrees.
        Dead sessions without resources are discarded.
        """
        state = self._state.load_state()

        for record in state.sessions:
            session = self._session_from_record(record)
            if session:
                self._sessions[session.id] = session

    def _session_from_record(self, record: SessionRecord) -> Session | None:
        """Reconstruct a Session from a persisted record.

        Returns None if the session should not be restored (no valid resources).
        """
        # Parse state
        try:
            state = SessionState(record.state)
        except ValueError:
            state = SessionState.BLOOMED

        # Parse session type
        try:
            session_type = SessionType(record.session_type)
        except ValueError:
            session_type = SessionType.CLAUDE

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
            created_at=created_at,
            ended_at=ended_at,
            resolved_working_dir=Path(record.working_dir) if record.working_dir else None,
            worktree_path=Path(record.worktree_path) if record.worktree_path else None,
            worktree_branch=record.worktree_branch,
        )

        # Override the auto-generated ID with the persisted one
        session.id = record.id

        # Set external tmux name if applicable
        if record.external_tmux_name:
            session._external_tmux_name = record.external_tmux_name

        # Set model if available
        if record.model:
            from .config import ClaudeModel
            try:
                session.resolved_model = ClaudeModel(record.model)
            except ValueError:
                pass

        # Update state based on current tmux status
        if tmux_exists and not tmux_dead:
            session.state = SessionState.GROWING
        elif state == SessionState.PAUSED:
            # Keep paused state if worktree exists
            session.state = SessionState.PAUSED if worktree_exists else SessionState.BLOOMED
        elif state == SessionState.KILLED:
            session.state = SessionState.KILLED
        else:
            session.state = SessionState.BLOOMED

        return session

    def _session_to_record(self, session: Session) -> SessionRecord:
        """Convert a Session to a persistable record."""
        external_name = None
        if hasattr(session, "_external_tmux_name"):
            external_name = session._external_tmux_name

        return SessionRecord(
            id=session.id,
            name=session.name,
            session_type=session.session_type.value,
            state=session.state.value,
            created_at=session.created_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            claude_session_id=session.claude_session_id,
            worktree_path=str(session.worktree_path) if session.worktree_path else None,
            worktree_branch=session.worktree_branch,
            working_dir=str(session.resolved_working_dir) if session.resolved_working_dir else None,
            model=session.resolved_model.value if session.resolved_model else None,
            external_tmux_name=external_name,
        )

    def save_state(self) -> bool:
        """Persist current session state to disk.

        Called automatically on session changes. Can also be called
        explicitly for manual saves.

        Returns True on success.
        """
        records = [self._session_to_record(s) for s in self._sessions.values()]
        state = PortalState(sessions=records)
        return self._state.save_state(state)

    def _persist_session_change(self, session: Session, event: str = "update") -> None:
        """Persist state after a session change.

        Saves full state and appends to history log.
        """
        # Save full state
        self.save_state()

        # Append to history
        record = self._session_to_record(session)
        self._state.append_history(record, event)
