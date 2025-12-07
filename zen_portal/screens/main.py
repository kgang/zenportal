"""MainScreen: The primary session management interface."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import MouseScrollDown, MouseScrollUp
from textual.reactive import reactive
from textual.widgets import Header, Static

from ..models.events import SessionSelected
from ..models.session import Session, SessionState, SessionType
from ..services.session_manager import SessionManager, SessionLimitError
from ..services.config import ConfigManager
from ..services.profile import ProfileManager
from ..services.proxy_monitor import ProxyMonitor, ProxyStatusEvent
from ..services.git import GitService
from ..widgets.session_list import SessionList
from ..widgets.output_view import OutputView
from ..widgets.session_info import SessionInfoView
from .base import ZenScreen
from .main_actions import MainScreenActionsMixin, MainScreenExitMixin


class MainScreen(MainScreenActionsMixin, MainScreenExitMixin, ZenScreen):
    """Main application screen with session list and output preview."""

    BINDINGS = [
        ("j", "move_down", "↓"),
        ("k", "move_up", "↑"),
        ("down", "move_down", "↓"),
        ("up", "move_up", "↑"),
        Binding("l", "toggle_grab", "→", show=False),
        Binding("space", "toggle_grab", "Grab", show=False),
        Binding("escape", "exit_grab", "Exit grab", show=False),
        ("n", "new_session", "New"),
        Binding("o", "attach_existing", "Attach Existing", show=False),
        ("p", "pause", "Pause"),
        ("x", "kill", "Kill"),
        ("d", "clean", "Clean"),
        Binding("w", "nav_worktree", "Worktree", show=False),
        Binding("W", "view_worktrees", "Worktrees", show=False),
        ("a", "attach_tmux", "Attach tmux"),
        ("v", "revive", "Revive"),
        ("e", "rename", "Rename"),
        Binding("i", "insert", "Insert", show=False),
        Binding("ctrl+i", "toggle_info", "Info", show=False),
        ("r", "refresh_output", "Refresh"),
        Binding("s", "toggle_streaming", "Stream", show=False),
        Binding("ctrl+f", "search_output", "Search", show=False),
        ("c", "config", "Config"),
        Binding("P", "proxy_dashboard", "Proxy Dashboard", show=False),
        ("?", "show_help", "Help"),
        ("q", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("/", "zen_prompt", "Ask AI", show=False),
        Binding("R", "restart_app", "Restart", show=False),
    ]

    info_mode: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
        padding: 1 2;
        layers: base notification;
    }

    MainScreen #content {
        height: 1fr;
    }

    MainScreen #session-list {
        width: 2fr;
        min-width: 30;
        max-width: 30vw;
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

    MainScreen #notifications {
        dock: bottom;
        layer: notification;
        margin-bottom: 2;
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
        self._streaming = False
        self._rapid_refresh_timer = None
        self._rapid_refresh_count = 0

        # Initialize proxy monitoring
        proxy_settings = self._config.get_proxy_settings()
        self._proxy_monitor = ProxyMonitor(proxy_settings) if proxy_settings and proxy_settings.enabled else None

        # Subscribe to proxy status events for notifications
        if self._proxy_monitor:
            self._proxy_monitor.add_status_callback(self._on_proxy_status_change)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="content"):
            yield SessionList(id="session-list")
            yield OutputView(id="output-view")
            info_view = SessionInfoView(proxy_monitor=self._proxy_monitor, id="info-view")
            info_view.display = False
            yield info_view
        yield Static("j/k nav  n new  a attach  ? help  q quit", id="hint", classes="hint")
        # Notification rack from ZenScreen base - must be last for layer ordering
        yield from super().compose()

    async def on_mount(self) -> None:
        """Initialize and start polling."""
        self._refresh_sessions()
        if self._focus_tmux_session:
            self._select_session_by_tmux_name(self._focus_tmux_session)
        self._refresh_selected_output()
        self.set_interval(1.0, self._poll_sessions)

        # Start proxy monitoring if available
        if self._proxy_monitor:
            await self._proxy_monitor.start_monitoring()

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
            info_view = self.query_one("#info-view", SessionInfoView)
            info_view.update_session(selected)
        else:
            if selected:
                output_view = self.query_one("#output-view", OutputView)
                if not selected.is_active:
                    content = self._build_dead_session_info(selected)
                else:
                    content = self._manager.get_output(selected.id)
                self._update_output_with_context(output_view, selected, content)

    def _refresh_sessions(self) -> None:
        """Update session list widget (skipped during grab mode to preserve reordering)."""
        session_list = self.query_one("#session-list", SessionList)
        if session_list.grab_mode:
            return  # Don't overwrite user's reordering
        session_list.update_sessions(self._manager.sessions)

    def _poll_sessions(self) -> None:
        """Periodic refresh of session states."""
        self._manager.refresh_states()
        self._refresh_sessions()
        if self._streaming:
            self._refresh_selected_output()

    def _start_rapid_refresh(self) -> None:
        """Start rapid refresh for 3 seconds after session creation."""
        if self._rapid_refresh_timer:
            self._rapid_refresh_timer.stop()
        self._rapid_refresh_count = 0
        self._rapid_refresh_timer = self.set_interval(1/3, self._rapid_refresh_tick)

    def _rapid_refresh_tick(self) -> None:
        """Single tick of rapid refresh."""
        self._rapid_refresh_count += 1
        self._manager.refresh_states()
        self._refresh_sessions()
        self._refresh_selected_output()

        if self._rapid_refresh_count >= 9:
            if self._rapid_refresh_timer:
                self._rapid_refresh_timer.stop()
                self._rapid_refresh_timer = None

    def on_session_selected(self, event: SessionSelected) -> None:
        """Handle session selection changes."""
        session = event.session

        if self.info_mode:
            info_view = self.query_one("#info-view", SessionInfoView)
            info_view.update_session(session)
        else:
            output_view = self.query_one("#output-view", OutputView)
            if not session.is_active:
                content = self._build_dead_session_info(session)
            else:
                content = self._manager.get_output(session.id)
            self._update_output_with_context(output_view, session, content)

    def _build_dead_session_info(self, session: Session) -> str:
        """Build informational content for a dead session."""
        lines = []
        paused_desc = "Stopped with worktree preserved" if session.worktree_path else "Session paused"
        killed_desc = "Stopped and worktree removed" if session.worktree_path else "Session ended"
        state_info = {
            SessionState.COMPLETED: ("completed", "Process exited normally"),
            SessionState.FAILED: ("failed", "Process failed to start or crashed"),
            SessionState.PAUSED: ("paused", paused_desc),
            SessionState.KILLED: ("killed", killed_desc),
        }
        state_label, state_desc = state_info.get(session.state, (session.state.value, ""))
        lines.append(f"  session {state_label}")
        if state_desc:
            lines.append(f"  {state_desc}")

        if session.state == SessionState.FAILED and session.error_message:
            lines.append(f"  error: {session.error_message}")

        lines.append("")

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

        if session.state == SessionState.PAUSED and session.worktree_path:
            lines.extend([
                "    w  open shell in worktree",
                "       (work on code without reviving session)",
                "    v  revive session",
                "       (resume Claude conversation)",
                "    d  clean up",
                "       (delete worktree and remove from list)",
            ])
        elif session.state == SessionState.PAUSED:
            lines.extend([
                "    v  revive session",
                "    d  clean up (remove from list)",
            ])
        elif session.state in (SessionState.COMPLETED, SessionState.FAILED):
            if session.worktree_path:
                lines.append("    w  open shell in worktree")
            lines.append("    v  revive session")
            if session.worktree_path:
                lines.append("    d  clean up (delete worktree)")
            else:
                lines.append("    d  clean up (remove from list)")
        else:
            lines.extend([
                "    v  revive session",
                "    d  clean up",
            ])

        return "\n".join(lines)

    def _update_output_with_context(
        self, output_view: OutputView, session: Session, content: str
    ) -> None:
        """Update output view with session context for eye strain reduction.

        Provides immediate visual echo of selection in the output panel header,
        reducing the need to scan back to the session list.
        """
        # Get state description
        state_map = {
            SessionState.RUNNING: "active",
            SessionState.COMPLETED: "complete",
            SessionState.FAILED: "failed",
            SessionState.PAUSED: "paused",
            SessionState.KILLED: "killed",
        }
        state = state_map.get(session.state, session.state.value)

        # Get git info if available
        working_path = session.worktree_path or session.resolved_working_dir
        git_info = ""
        if working_path and working_path.exists():
            info = GitService.get_info(working_path)
            if info:
                git_info = info.display

        output_view.update_session(
            session_name=session.display_name,
            output=content,
            glyph=session.status_glyph,
            state=state,
            age=session.age_display,
            session_type=session.session_type.value,
            git_info=git_info,
            working_dir=str(working_path) if working_path else "",
        )

    # Navigation actions
    def action_move_down(self) -> None:
        self.query_one("#session-list", SessionList).move_down()

    def action_move_up(self) -> None:
        self.query_one("#session-list", SessionList).move_up()

    def action_toggle_grab(self) -> None:
        """Toggle grab mode for reordering sessions."""
        session_list = self.query_one("#session-list", SessionList)
        if session_list.grab_mode:
            session_list.exit_grab_mode()
            self._save_session_order()
            self.zen_notify("order saved")
        else:
            session_list.toggle_grab_mode()
            self.zen_notify("grab mode: j/k to reorder, space/esc to exit")

    def action_exit_grab(self) -> None:
        """Exit grab mode and save order."""
        session_list = self.query_one("#session-list", SessionList)
        if session_list.grab_mode:
            session_list.exit_grab_mode()
            self._save_session_order()
            self.zen_notify("order saved")

    def _save_session_order(self) -> None:
        """Save current session order to state."""
        session_list = self.query_one("#session-list", SessionList)
        order = session_list.get_session_order()
        self._manager.set_session_order(order)

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
                    type_mapping = {
                        ScreenSessionType.CLAUDE: SessionType.CLAUDE,
                        ScreenSessionType.CODEX: SessionType.CODEX,
                        ScreenSessionType.GEMINI: SessionType.GEMINI,
                        ScreenSessionType.SHELL: SessionType.SHELL,
                        ScreenSessionType.OPENROUTER: SessionType.OPENROUTER,
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
                    self.zen_notify(f"created {session_type.value}: {session.display_name}")

                elif result.result_type == ResultType.ATTACH:
                    tmux_session = result.tmux_session
                    if tmux_session:
                        self._manager.adopt_external_tmux(
                            tmux_name=tmux_session.name,
                            claude_session_id=tmux_session.claude_session_id,
                            working_dir=tmux_session.cwd,
                        )
                        self.app.exit(result=f"attach:{tmux_session.name}")

                elif result.result_type == ResultType.RESUME:
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

                        # Show appropriate notification based on session state
                        if session.state == SessionState.FAILED:
                            error_msg = session.error_message or "Resume failed"
                            self.zen_notify(error_msg, "error")
                        else:
                            self.zen_notify(f"resumed: {session.display_name}")

            except SessionLimitError as e:
                self.zen_notify(str(e), "error")

        existing_names = {s.name for s in self._manager.sessions}
        known_claude_ids = {s.claude_session_id for s in self._manager.sessions if s.claude_session_id}
        self.app.push_screen(
            NewSessionModal(
                config_manager=self._config,
                discovery_service=discovery,
                tmux_service=self._manager._tmux,
                existing_names=existing_names,
                session_prefix=prefix,
                known_claude_session_ids=known_claude_ids,
                max_sessions=self._manager.MAX_SESSIONS,
                existing_sessions=list(self._manager.sessions),
            ),
            handle_result,
        )

    def action_refresh_output(self) -> None:
        self._refresh_selected_output()
        self._manager.refresh_states()
        self._refresh_sessions()

    def action_toggle_streaming(self) -> None:
        self._streaming = not self._streaming
        self.zen_notify(f"output mode: {'streaming' if self._streaming else 'snapshot'}")
        self._update_hint()

    def action_search_output(self) -> None:
        """Activate search in output view (only when not in info mode)."""
        if not self.info_mode:
            try:
                output_view = self.query_one("#output-view", OutputView)
                output_view.action_toggle_search()
            except Exception:
                pass

    def action_toggle_info(self) -> None:
        self.info_mode = not self.info_mode

    def watch_info_mode(self, info_mode: bool) -> None:
        try:
            output_view = self.query_one("#output-view", OutputView)
            info_view = self.query_one("#info-view", SessionInfoView)
            output_view.display = not info_mode
            info_view.display = info_mode
            self._refresh_selected_output()
            self._update_hint()
            self.zen_notify(f"view: {'info' if info_mode else 'output'}")
        except Exception:
            pass

    def _update_hint(self) -> None:
        hint = self.query_one("#hint", Static)
        base = "j/k nav  n new  a attach  ? help  q quit"
        if self.info_mode:
            hint.update(f"{base}  [dim]◦ info[/dim]")
        elif self._streaming:
            hint.update(f"{base}  [dim]◦ stream[/dim]")
        else:
            hint.update(base)

    def action_config(self) -> None:
        from .config_screen import ConfigScreen
        self.app.push_screen(ConfigScreen(self._config, self._profile))

    def action_proxy_dashboard(self) -> None:
        """Open proxy health dashboard."""
        if not self._proxy_monitor:
            self.zen_notify("proxy monitoring not available", "warning")
            return

        from .proxy_dashboard import ProxyDashboardScreen
        self.app.push_screen(ProxyDashboardScreen(
            proxy_monitor=self._proxy_monitor,
            config_manager=self._config
        ))

    def action_show_help(self) -> None:
        from ..screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

    def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        event.stop()

    def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        event.stop()

    def zen_notify(self, message: str, severity: str = "success") -> None:
        """Helper method for sending zen-styled notifications."""
        from ..services.notification import NotificationSeverity
        svc = self.app.notification_service
        if severity == "warning":
            self.post_message(svc.warning(message))
        elif severity == "error":
            self.post_message(svc.error(message))
        else:
            self.post_message(svc.success(message))

    def _on_proxy_status_change(self, event: ProxyStatusEvent) -> None:
        """Handle proxy status change events for proactive notifications."""
        from ..services.proxy_monitor import ProxyHealthStatus

        # Only notify on significant status changes
        if event.old_status == ProxyHealthStatus.UNKNOWN:
            # Initial status detection - don't notify
            return

        # Notify on degradation or recovery
        if event.new_status in [ProxyHealthStatus.ERROR, ProxyHealthStatus.WARNING]:
            if event.old_status in [ProxyHealthStatus.EXCELLENT, ProxyHealthStatus.GOOD]:
                # Degradation from healthy to problematic
                self.zen_notify(f"proxy: {event.message}", "warning")
        elif event.new_status in [ProxyHealthStatus.EXCELLENT, ProxyHealthStatus.GOOD]:
            if event.old_status in [ProxyHealthStatus.ERROR, ProxyHealthStatus.WARNING, ProxyHealthStatus.DEGRADED]:
                # Recovery from problematic to healthy
                self.zen_notify("proxy: connection restored", "success")

        # Update session info display if visible
        if self.info_mode:
            info_view = self.query_one("#info-view", SessionInfoView)
            info_view.refresh()

    async def _cleanup_monitoring(self) -> None:
        """Clean up proxy monitoring on screen exit."""
        if self._proxy_monitor:
            await self._proxy_monitor.stop_monitoring()

    async def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        await self._cleanup_monitoring()
