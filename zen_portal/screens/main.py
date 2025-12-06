"""MainScreen: The primary session management interface."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import MouseScrollDown, MouseScrollUp
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Header, Static

from ..models.events import SessionSelected
from ..models.session import Session, SessionState, SessionType
from ..services.session_manager import SessionManager, SessionLimitError
from ..services.config import ConfigManager, ExitBehavior
from ..services.profile import ProfileManager
from ..widgets.session_list import SessionList
from ..widgets.output_view import OutputView
from ..widgets.session_info import SessionInfoView


class MainScreen(Screen):
    """Main application screen with session list and output preview."""

    BINDINGS = [
        ("j", "move_down", "↓"),
        ("k", "move_up", "↑"),
        ("down", "move_down", "↓"),
        ("up", "move_up", "↑"),
        ("n", "new_session", "New"),
        Binding("o", "attach_existing", "Attach Existing", show=False),
        ("p", "pause", "Pause"),
        ("x", "kill", "Kill"),
        ("d", "clean", "Clean"),
        Binding("w", "nav_worktree", "Worktree", show=False),
        Binding("W", "view_worktrees", "Worktrees", show=False),
        ("a", "attach_tmux", "Attach tmux"),
        ("v", "revive", "Revive"),
        Binding("R", "rename", "Rename", show=False),
        Binding("i", "insert", "Insert", show=False),
        Binding("ctrl+i", "toggle_info", "Info", show=False),
        ("r", "refresh_output", "Refresh"),
        Binding("s", "toggle_streaming", "Stream", show=False),
        ("c", "config", "Config"),
        ("?", "show_help", "Help"),
        ("q", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    # Information mode - shows metadata instead of output
    info_mode: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
        padding: 1 2;
    }

    MainScreen #content {
        height: 1fr;
    }

    MainScreen #session-list {
        width: 2fr;
        max-width: 50;
    }

    MainScreen #output-view {
        width: 3fr;
        border-left: solid $surface-lighten-1;
        padding-left: 2;
    }

    MainScreen #info-view {
        width: 3fr;
        border-left: solid $surface-lighten-1;
        padding-left: 2;
    }

    MainScreen .hint {
        dock: bottom;
        height: 1;
        color: $text-disabled;
        text-align: center;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        session_manager: SessionManager,
        config_manager: ConfigManager,
        profile_manager: ProfileManager | None = None,
        focus_tmux_session: str | None = None,
    ) -> None:
        super().__init__()
        self._manager = session_manager
        self._config = config_manager
        self._profile = profile_manager or ProfileManager()
        self._focus_tmux_session = focus_tmux_session
        self._streaming = False  # Start in snapshot mode
        self._rapid_refresh_timer = None  # Timer for rapid refresh after session creation
        self._rapid_refresh_count = 0  # Counter for rapid refresh iterations

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="content"):
            yield SessionList(id="session-list")
            yield OutputView(id="output-view")
            info_view = SessionInfoView(id="info-view")
            info_view.display = False  # Hidden by default
            yield info_view

        yield Static(
            "j/k nav  n new  a attach  ? help  q quit",
            id="hint",
            classes="hint",
        )

    def on_mount(self) -> None:
        """Initialize and start polling."""
        self._refresh_sessions()

        # Focus on specific session if requested (e.g., after detaching from tmux)
        if self._focus_tmux_session:
            self._select_session_by_tmux_name(self._focus_tmux_session)

        # Refresh output for selected session (important after returning from tmux)
        self._refresh_selected_output()
        self.set_interval(1.0, self._poll_sessions)

    def _select_session_by_tmux_name(self, tmux_name: str) -> None:
        """Select the session with the given tmux session name."""
        session_list = self.query_one("#session-list", SessionList)
        for i, session in enumerate(self._manager.sessions):
            if self._manager.get_tmux_session_name(session.id) == tmux_name:
                session_list.selected_index = i
                session_list.refresh(recompose=True)
                break

    def _refresh_selected_output(self) -> None:
        """Refresh output/info view for currently selected session."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()

        if self.info_mode:
            # Update info view
            info_view = self.query_one("#info-view", SessionInfoView)
            info_view.update_session(selected)
        else:
            # Update output view
            if selected:
                output_view = self.query_one("#output-view", OutputView)
                if not selected.is_active:
                    content = self._build_dead_session_info(selected)
                    output_view.update_output(selected.display_name, content)
                else:
                    output = self._manager.get_output(selected.id)
                    output_view.update_output(selected.display_name, output)

    def _refresh_sessions(self) -> None:
        """Update session list widget."""
        session_list = self.query_one("#session-list", SessionList)
        session_list.update_sessions(self._manager.sessions)

    def _poll_sessions(self) -> None:
        """Periodic refresh of session states."""
        self._manager.refresh_states()
        self._refresh_sessions()

        # Only update output if streaming mode is enabled
        if self._streaming:
            self._refresh_selected_output()

    def _start_rapid_refresh(self) -> None:
        """Start rapid refresh for 3 seconds after session creation."""
        # Cancel any existing rapid refresh
        if self._rapid_refresh_timer:
            self._rapid_refresh_timer.stop()

        self._rapid_refresh_count = 0
        # 3 times per second = every 333ms
        self._rapid_refresh_timer = self.set_interval(1/3, self._rapid_refresh_tick)

    def _rapid_refresh_tick(self) -> None:
        """Single tick of rapid refresh."""
        self._rapid_refresh_count += 1
        self._manager.refresh_states()
        self._refresh_sessions()
        self._refresh_selected_output()

        # Stop after 9 ticks (3 seconds at 3/second)
        if self._rapid_refresh_count >= 9:
            if self._rapid_refresh_timer:
                self._rapid_refresh_timer.stop()
                self._rapid_refresh_timer = None

    def on_session_selected(self, event: SessionSelected) -> None:
        """Handle session selection changes."""
        session = event.session

        if self.info_mode:
            # Update info view
            info_view = self.query_one("#info-view", SessionInfoView)
            info_view.update_session(session)
        else:
            # Update output view
            output_view = self.query_one("#output-view", OutputView)
            if not session.is_active:
                content = self._build_dead_session_info(session)
                output_view.update_output(session.display_name, content)
            else:
                output = self._manager.get_output(session.id)
                output_view.update_output(session.display_name, output)

    def _build_dead_session_info(self, session: Session) -> str:
        """Build informational content for a dead session."""
        lines = []

        # State header with description
        # Only mention worktree if one exists
        paused_desc = "Stopped with worktree preserved" if session.worktree_path else "Session paused"
        killed_desc = "Stopped and worktree removed" if session.worktree_path else "Session ended"
        state_info = {
            SessionState.COMPLETED: ("completed", "Process exited normally"),
            SessionState.FAILED: ("failed", "Process failed to start or crashed"),
            SessionState.PAUSED: ("paused", paused_desc),
            SessionState.KILLED: ("killed", killed_desc),
        }
        state_label, state_desc = state_info.get(
            session.state, (session.state.value, "")
        )
        lines.append(f"  session {state_label}")
        if state_desc:
            lines.append(f"  {state_desc}")

        # Show error message for failed sessions
        if session.state == SessionState.FAILED and session.error_message:
            lines.append(f"  [red]{session.error_message}[/red]")

        lines.append("")

        # Session details
        if session.session_type == SessionType.CLAUDE and session.claude_session_id:
            lines.append("  details")
            lines.append(f"    session id: {session.claude_session_id[:8]}...")
            if session.resolved_model:
                lines.append(f"    model: {session.resolved_model.value}")
            if session.resolved_working_dir:
                lines.append(f"    working dir: {session.resolved_working_dir}")
        elif session.session_type == SessionType.SHELL:
            lines.append("  shell session")
            if session.resolved_working_dir:
                lines.append(f"    working dir: {session.resolved_working_dir}")

        # Worktree section - prominent for paused sessions
        if session.worktree_path:
            lines.append("")
            lines.append("  worktree")
            lines.append(f"    path: {session.worktree_path}")
            if session.state == SessionState.PAUSED:
                lines.append("")
                lines.append("    Code changes are preserved on disk.")
                lines.append("    You can continue working on this branch.")

        lines.append("")
        lines.append("  actions")

        # State-specific actions
        if session.state == SessionState.PAUSED and session.worktree_path:
            lines.append("    [bold]w[/bold]  open shell in worktree")
            lines.append("        (work on code without reviving session)")
            lines.append("    [bold]v[/bold]  revive session")
            lines.append("        (resume Claude conversation)")
            lines.append("    [bold]d[/bold]  clean up")
            lines.append("        (delete worktree and remove from list)")
        elif session.state == SessionState.PAUSED:
            lines.append("    [bold]v[/bold]  revive session")
            lines.append("    [bold]d[/bold]  clean up (remove from list)")
        elif session.state in (SessionState.COMPLETED, SessionState.FAILED):
            if session.worktree_path:
                lines.append("    [bold]w[/bold]  open shell in worktree")
            lines.append("    [bold]v[/bold]  revive session")
            if session.worktree_path:
                lines.append("    [bold]d[/bold]  clean up (delete worktree)")
            else:
                lines.append("    [bold]d[/bold]  clean up (remove from list)")
        else:
            lines.append("    [bold]v[/bold]  revive session")
            lines.append("    [bold]d[/bold]  clean up")

        return "\n".join(lines)

    def action_move_down(self) -> None:
        """Move selection down."""
        self.query_one("#session-list", SessionList).move_down()

    def action_move_up(self) -> None:
        """Move selection up."""
        self.query_one("#session-list", SessionList).move_up()

    def action_new_session(self) -> None:
        """Open new session modal."""
        from .new_session import NewSessionModal, NewSessionResult, SessionType as ScreenSessionType, ResultType
        from ..services.discovery import DiscoveryService

        discovery = DiscoveryService()
        prefix = f"{self._manager._get_session_prefix()}-"

        def handle_result(result: NewSessionResult | None) -> None:
            if not result:
                return

            try:
                if result.result_type == ResultType.NEW:
                    # Create new session - map screen session type to model session type
                    type_mapping = {
                        ScreenSessionType.CLAUDE: SessionType.CLAUDE,
                        ScreenSessionType.CODEX: SessionType.CODEX,
                        ScreenSessionType.GEMINI: SessionType.GEMINI,
                        ScreenSessionType.SHELL: SessionType.SHELL,
                    }
                    session_type = type_mapping.get(result.session_type, SessionType.CLAUDE)
                    session = self._manager.create_session(
                        result.name,
                        result.prompt,
                        features=result.features,
                        session_type=session_type,
                    )
                    self._refresh_sessions()
                    session_list = self.query_one("#session-list", SessionList)
                    session_list.selected_index = 0
                    session_list.refresh(recompose=True)
                    self._start_rapid_refresh()
                    self.notify(f"Created {session_type.value}: {session.display_name}", timeout=3)

                elif result.result_type == ResultType.ATTACH:
                    # Attach to external tmux session
                    tmux_session = result.tmux_session
                    if tmux_session:
                        self._manager.adopt_external_tmux(
                            tmux_name=tmux_session.name,
                            claude_session_id=tmux_session.claude_session_id,
                            working_dir=tmux_session.cwd,
                        )
                        # Exit TUI to attach to tmux, then return to TUI on detach
                        self.app.exit(result=f"attach:{tmux_session.name}")

                elif result.result_type == ResultType.RESUME:
                    # Resume Claude session
                    claude_session = result.claude_session
                    if claude_session:
                        session = self._manager.create_session_with_resume(
                            name=f"resume:{claude_session.session_id[:8]}",
                            resume_session_id=claude_session.session_id,
                            working_dir=claude_session.project_path,
                        )
                        self._refresh_sessions()
                        session_list = self.query_one("#session-list", SessionList)
                        session_list.selected_index = 0
                        session_list.refresh(recompose=True)
                        self._start_rapid_refresh()
                        self.notify(f"Resumed: {session.display_name}", timeout=3)

            except SessionLimitError as e:
                self.notify(str(e), severity="error", timeout=5)

        # Get existing session names for unique name generation
        existing_names = {s.name for s in self._manager.sessions}
        self.app.push_screen(
            NewSessionModal(
                config_manager=self._config,
                discovery_service=discovery,
                tmux_service=self._manager._tmux,
                existing_names=existing_names,
                session_prefix=prefix,
            ),
            handle_result,
        )

    def action_pause(self) -> None:
        """Pause selected session (ends tmux but preserves worktree)."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            if not selected.is_active:
                self.notify("Session already ended", severity="warning")
                return

            self._manager.pause_session(selected.id)
            self._refresh_sessions()

            if selected.worktree_path:
                self.notify(
                    f"Paused: {selected.display_name} (worktree preserved at {selected.worktree_path})",
                    timeout=5,
                )
            else:
                self.notify(f"Paused: {selected.display_name}", timeout=3)
        else:
            self.notify("No session selected", severity="warning")

    def action_kill(self) -> None:
        """Kill selected session and remove its worktree."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            if not selected.is_active:
                self.notify("Session already ended", severity="warning")
                return

            had_worktree = selected.worktree_path is not None
            self._manager.kill_session(selected.id)
            self._refresh_sessions()

            if had_worktree:
                self.notify(f"Killed: {selected.display_name} (worktree removed)", timeout=3)
            else:
                self.notify(f"Killed: {selected.display_name}", timeout=3)
        else:
            self.notify("No session selected", severity="warning")

    def action_clean(self) -> None:
        """Clean up an ended session (remove worktree and session from list)."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if not selected:
            self.notify("No session selected", severity="warning")
            return

        if selected.is_active:
            self.notify("Cannot clean active session - use 'p' to pause or 'x' to kill first", severity="warning")
            return

        had_worktree = selected.worktree_path is not None
        self._manager.clean_session(selected.id)
        self._refresh_sessions()

        if had_worktree:
            self.notify(f"Cleaned: {selected.display_name} (worktree removed)", timeout=3)
        else:
            self.notify(f"Cleaned: {selected.display_name}", timeout=3)

    def action_nav_worktree(self) -> None:
        """Navigate to a session's worktree."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if not selected:
            self.notify("No session selected", severity="warning")
            return

        if selected.is_active:
            self.notify("Session is still active - use 'a' to attach directly", severity="warning")
            return

        if not selected.worktree_path:
            self.notify("Session has no worktree", severity="warning")
            return

        new_session = self._manager.navigate_to_worktree(selected.id)
        if new_session:
            self._refresh_sessions()
            self.notify(f"Created shell session in worktree: {new_session.display_name}", timeout=3)
        else:
            self.notify("Could not create session in worktree", severity="error")

    def action_view_worktrees(self) -> None:
        """Open worktrees view."""
        from .worktrees import WorktreesScreen, WorktreeAction
        from ..models.session import SessionFeatures, SessionType

        # Check if we have a worktree service
        if not self._manager._worktree:
            self.notify("Worktrees not configured", severity="warning")
            return

        def handle_result(result: WorktreeAction | None) -> None:
            if not result or result.action == "cancel":
                return

            wt = result.worktree
            if not wt:
                return

            if result.action == "shell":
                # Create a shell session in the worktree
                try:
                    features = SessionFeatures(working_dir=wt.path)
                    session = self._manager.create_session(
                        name=f"wt:{wt.branch[:12]}" if wt.branch else "worktree",
                        features=features,
                        session_type=SessionType.SHELL,
                    )
                    self._refresh_sessions()
                    # Select the new session
                    session_list = self.query_one("#session-list", SessionList)
                    session_list.selected_index = 0
                    session_list.refresh(recompose=True)
                    self._start_rapid_refresh()
                    self.notify(f"Shell in worktree: {wt.branch}", timeout=3)
                except Exception as e:
                    self.notify(f"Error: {e}", severity="error", timeout=5)

            elif result.action == "delete":
                # Delete the worktree
                wt_result = self._manager._worktree.remove_worktree(wt.path, force=True)
                if wt_result.success:
                    self.notify(f"Deleted worktree: {wt.branch}", timeout=3)
                else:
                    self.notify(f"Failed: {wt_result.error}", severity="error", timeout=5)

        self.app.push_screen(
            WorktreesScreen(
                worktree_service=self._manager._worktree,
                sessions=self._manager.sessions,
            ),
            handle_result,
        )

    def action_attach_tmux(self) -> None:
        """Attach to tmux session (leaves TUI)."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if not selected:
            self.notify("No session selected", severity="warning")
            return

        if not selected.is_active:
            self.notify("Cannot attach to ended session - use 'v' to revive first", severity="warning")
            return

        tmux_name = self._manager.get_tmux_session_name(selected.id)
        if tmux_name:
            self.app.exit(result=f"attach:{tmux_name}")

    def action_attach_existing(self) -> None:
        """Open modal to attach to an external tmux session."""
        from .attach_session import AttachSessionModal, AttachSessionResult
        from ..services.discovery import DiscoveryService

        discovery = DiscoveryService()
        prefix = f"{self._manager._get_session_prefix()}-"

        # Track existing session IDs to detect reconnection
        existing_ids = {s.id for s in self._manager.sessions}

        def handle_result(result: AttachSessionResult | None) -> None:
            if not result:
                return

            try:
                # Adopt the external tmux session into zen-portal
                session = self._manager.adopt_external_tmux(
                    tmux_name=result.tmux_name,
                    claude_session_id=result.claude_session_id,
                    working_dir=result.cwd,
                )
                self._refresh_sessions()

                # Check if this was a reconnection to existing session
                is_reconnection = session.id in existing_ids

                # Select the session (find its index)
                session_list = self.query_one("#session-list", SessionList)
                sessions = self._manager.sessions
                for i, s in enumerate(sessions):
                    if s.id == session.id:
                        session_list.selected_index = i
                        break
                session_list.refresh(recompose=True)

                # Start rapid refresh
                self._start_rapid_refresh()

                if is_reconnection:
                    self.notify(f"Reconnected: {session.display_name}", timeout=3)
                elif result.has_claude:
                    self.notify(f"Adopted: {session.display_name} (claude synced)", timeout=3)
                else:
                    self.notify(f"Adopted: {session.display_name}", timeout=3)
            except Exception as e:
                self.notify(f"Error: {e}", severity="error", timeout=5)

        self.app.push_screen(
            AttachSessionModal(
                discovery_service=discovery,
                tmux_service=self._manager._tmux,
                session_prefix=prefix,
            ),
            handle_result,
        )

    def action_revive(self) -> None:
        """Revive a bloomed/wilted session."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            if selected.is_active:
                self.notify("Session is already running", severity="warning")
            elif self._manager.revive_session(selected.id):
                self._refresh_sessions()
                # Start rapid refresh to catch initial output
                self._start_rapid_refresh()
                self.notify(f"Revived: {selected.display_name}", timeout=3)
            else:
                self.notify("Could not revive session", severity="error")
        else:
            self.notify("No session selected", severity="warning")

    def action_rename(self) -> None:
        """Rename the selected session."""
        from .rename_modal import RenameModal

        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if not selected:
            self.notify("No session selected", severity="warning")
            return

        def handle_result(new_name: str | None) -> None:
            if new_name is None:
                return  # Cancelled

            if self._manager.rename_session(selected.id, new_name):
                self._refresh_sessions()
                self.notify(f"Renamed to: {new_name}", timeout=2)
            else:
                self.notify("Could not rename session", severity="error")

        self.app.push_screen(RenameModal(selected.name), handle_result)

    def action_refresh_output(self) -> None:
        """Refresh output for selected session."""
        self._refresh_selected_output()
        # Also refresh session states
        self._manager.refresh_states()
        self._refresh_sessions()

    def action_toggle_streaming(self) -> None:
        """Toggle streaming mode for output updates."""
        self._streaming = not self._streaming
        mode = "streaming" if self._streaming else "snapshot"
        self.notify(f"Output mode: {mode}", timeout=2)
        self._update_hint()

    def action_toggle_info(self) -> None:
        """Toggle information mode (show metadata instead of output)."""
        self.info_mode = not self.info_mode

    def watch_info_mode(self, info_mode: bool) -> None:
        """Update view visibility when info mode changes."""
        try:
            output_view = self.query_one("#output-view", OutputView)
            info_view = self.query_one("#info-view", SessionInfoView)

            output_view.display = not info_mode
            info_view.display = info_mode

            # Refresh the appropriate view
            self._refresh_selected_output()

            # Update hint
            self._update_hint()

            mode = "info" if info_mode else "output"
            self.notify(f"View: {mode}", timeout=1)
        except Exception:
            pass  # Views may not exist during initialization

    def _update_hint(self) -> None:
        """Update hint line based on current modes."""
        hint = self.query_one("#hint", Static)
        base = "j/k nav  n new  a attach  ? help  q quit"

        if self.info_mode:
            hint.update(f"{base}  [dim]◦ info[/dim]")
        elif self._streaming:
            hint.update(f"{base}  [dim]◦ stream[/dim]")
        else:
            hint.update(base)

    def action_config(self) -> None:
        """Show config screen."""
        from .config_screen import ConfigScreen

        self.app.push_screen(ConfigScreen(self._config, self._profile))

    def action_insert(self) -> None:
        """Open insert modal to send keys to session."""
        from .insert_modal import InsertModal, InsertResult

        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if not selected:
            self.notify("No session selected", severity="warning")
            return

        if not selected.is_active:
            self.notify("Session is not active", severity="warning")
            return

        def handle_result(result: InsertResult | None) -> None:
            if result is not None and result.keys:  # None means cancelled (ESC with empty buffer)
                tmux_name = self._manager.get_tmux_session_name(selected.id)
                if tmux_name:
                    self._manager._tmux.send_keys(tmux_name, result.keys)
                    # Start rapid refresh to catch output from sent keys
                    self._start_rapid_refresh()
                    # Show preview of what was sent
                    preview_parts = []
                    for item in result.keys[:10]:  # First 10 items
                        if item.is_special:
                            preview_parts.append(f"[{item.display}]")
                        elif item.value == "\n":
                            preview_parts.append("↵")
                        else:
                            preview_parts.append(item.display)
                    preview = "".join(preview_parts)[:20]
                    suffix = "..." if len(result.keys) > 10 or len(preview) > 20 else ""
                    self.notify(f"Sent: {preview}{suffix}", timeout=2)

        self.app.push_screen(InsertModal(selected.display_name), handle_result)


    def action_show_help(self) -> None:
        """Show help screen."""
        from ..screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    def _exit_with_cleanup(self, cleanup_orphans: bool = False, keep_running: bool = False) -> None:
        """Exit the application.

        Args:
            cleanup_orphans: If True, clean up orphaned tmux sessions with dead panes.
                           Only used with "kill all" exit behavior.
            keep_running: If True, return session info for display after exit.
        """
        if cleanup_orphans:
            self._manager.cleanup_dead_tmux_sessions()
        # Save state before exit so sessions persist across restarts
        self._manager.save_state()

        # Collect info about running sessions to display after exit
        if keep_running:
            running_sessions = []
            for session in self._manager.sessions:
                if session.is_active:
                    tmux_name = self._manager.get_tmux_session_name(session.id)
                    if tmux_name:
                        running_sessions.append({
                            "tmux_name": tmux_name,
                            "display_name": session.display_name,
                        })
            if running_sessions:
                self.app.exit(result={"kept_sessions": running_sessions})
                return

        self.app.exit()

    def action_quit(self) -> None:
        """Quit the application with optional cleanup."""
        from .exit_modal import ExitModal, ExitResult, ExitChoice

        behavior = self._config.config.exit_behavior
        active, dead = self._manager.count_by_state()

        # If no sessions or config says don't ask, handle directly
        if active == 0 and dead == 0:
            self._exit_with_cleanup()
            return

        if behavior == ExitBehavior.KILL_ALL:
            self._manager.kill_all_sessions()
            self._exit_with_cleanup(cleanup_orphans=True)
            return
        elif behavior == ExitBehavior.KILL_DEAD:
            self._manager.kill_dead_sessions()
            self._exit_with_cleanup()
            return
        elif behavior == ExitBehavior.KEEP_ALL:
            self._exit_with_cleanup(keep_running=True)
            return

        # ASK behavior - show modal
        def handle_exit(result: ExitResult | None) -> None:
            if result is None:
                return  # Cancelled

            if result.remember:
                if result.choice == ExitChoice.KILL_ALL:
                    self._config.update_exit_behavior(ExitBehavior.KILL_ALL)
                elif result.choice == ExitChoice.KILL_DEAD:
                    self._config.update_exit_behavior(ExitBehavior.KILL_DEAD)
                elif result.choice == ExitChoice.KEEP_ALL:
                    self._config.update_exit_behavior(ExitBehavior.KEEP_ALL)

            cleanup_orphans = result.choice == ExitChoice.KILL_ALL
            keep_running = result.choice == ExitChoice.KEEP_ALL
            if result.choice == ExitChoice.KILL_ALL:
                self._manager.kill_all_sessions()
            elif result.choice == ExitChoice.KILL_DEAD:
                self._manager.kill_dead_sessions()

            self._exit_with_cleanup(cleanup_orphans=cleanup_orphans, keep_running=keep_running)

        self.app.push_screen(ExitModal(active, dead), handle_exit)

    def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        """Prevent scroll wheel from affecting the main view."""
        event.stop()

    def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        """Prevent scroll wheel from affecting the main view."""
        event.stop()
