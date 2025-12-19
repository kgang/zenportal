"""MainScreen: The primary session management interface."""

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key, MouseScrollDown, MouseScrollUp
from textual.reactive import reactive
from textual.widgets import Header, Static, Input

from ..models.events import SessionSelected
from ..models.session import Session, SessionState, SessionType
from ..services.session_manager import SessionManager
from ..services.events import (
    EventBus,
    SessionCreatedEvent,
    SessionPausedEvent,
    SessionKilledEvent,
    SessionCleanedEvent,
)
from ..services.config import ConfigManager
from ..services.tmux_async import AsyncTmuxService
from ..services.reactive.session_watcher import SessionStateWatcher
from ..services.profile import ProfileManager
from ..services.command_registry import create_default_registry
from ..services.template_manager import TemplateManager
from ..services.proxy_monitor import ProxyMonitor, ProxyStatusEvent
from ..services.git import GitService
from ..widgets.session_list import SessionList, SearchConfirmed, SearchCancelled
from ..widgets.output_view import OutputView
from ..widgets.session_info import SessionInfoView
from ..widgets.splitter import VerticalSplitter
from .base import ZenScreen
from .main_actions import MainScreenActionsMixin, MainScreenExitMixin
from .main_templates import MainScreenTemplateMixin, MainScreenPaletteMixin


class MainScreen(MainScreenPaletteMixin, MainScreenTemplateMixin, MainScreenActionsMixin, MainScreenExitMixin, ZenScreen):
    """Main application screen with session list and output preview."""

    BINDINGS = [
        ("j", "move_down", "↓"),
        ("k", "move_up", "↑"),
        ("down", "move_down", "↓"),
        ("up", "move_up", "↑"),
        Binding("l", "toggle_move", "→", show=False),
        Binding("space", "toggle_move", "Move", show=False),
        Binding("escape", "escape_handler", "Exit", show=False),
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
        Binding("I", "toggle_info", "Info", show=False),
        ("r", "refresh_output", "Refresh"),
        Binding("s", "toggle_streaming", "Stream", show=False),
        Binding("S", "search_output", "Search", show=False),
        ("c", "config", "Config"),
        ("?", "show_help", "Help"),
        ("q", "quit", "Quit"),
        Binding("/", "search_sessions", "Search", show=False),
        Binding("R", "restart_app", "Restart", show=False),
        Binding(":", "command_palette", "Commands", show=False),
        Binding("ctrl+p", "command_palette", "Commands", show=False),
        Binding("T", "templates", "Templates", show=False),
    ]

    info_mode: reactive[bool] = reactive(False)
    search_mode: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
        padding: 0;
        layers: base notification;
    }

    MainScreen #content {
        height: 1fr;
    }

    MainScreen #session-list {
        width: 28;
        min-width: 20;
        max-width: 50;
    }

    MainScreen #splitter {
        width: 1;
        height: 100%;
        background: $surface-lighten-1;
    }

    MainScreen #splitter:hover {
        background: $primary;
    }

    MainScreen #splitter.-dragging {
        background: $primary;
    }

    MainScreen #output-view {
        width: 1fr;
        padding-left: 1;
    }

    MainScreen #info-view {
        width: 1fr;
        padding-left: 1;
    }

    MainScreen .hint {
        dock: bottom;
        height: 1;
        color: $text-disabled;
        text-align: center;
        margin: 0;
        padding: 0 1;
    }

    MainScreen #notifications {
        layer: notification;
        dock: bottom;
        height: auto;
        width: auto;
        margin: 0 0 1 1;
    }

    MainScreen #search-input {
        dock: bottom;
        width: 100%;
        height: 1;
        background: $surface;
        border: none;
        padding: 0 1;
    }

    MainScreen #search-input.hidden {
        display: none;
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

        # Reactive state watcher (replaces polling)
        self._watcher: SessionStateWatcher | None = None
        self._rapid_refresh_task: asyncio.Task | None = None

        # Cached widget references (set in on_mount)
        self._session_list: SessionList | None = None
        self._output_view: OutputView | None = None
        self._info_view: SessionInfoView | None = None
        self._hint: Static | None = None
        self._search_input: Input | None = None

        # Initialize command registry for palette
        self._command_registry = create_default_registry()

        # Initialize template manager
        self._template_manager = TemplateManager()

        # Initialize proxy monitoring
        proxy_settings = self._config.get_proxy_settings()
        self._proxy_monitor = ProxyMonitor(proxy_settings) if proxy_settings and proxy_settings.enabled else None

        # Subscribe to proxy status events for notifications
        if self._proxy_monitor:
            self._proxy_monitor.add_status_callback(self._on_proxy_status_change)

        # EventBus for reactive session updates
        self._bus = EventBus.get()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="content"):
            yield SessionList(id="session-list")
            yield VerticalSplitter(target_id="session-list", min_width=20, max_width=60, id="splitter")
            yield OutputView(id="output-view")
            info_view = SessionInfoView(proxy_monitor=self._proxy_monitor, id="info-view")
            info_view.display = False
            yield info_view
        search_input = Input(placeholder="search ↑↓ tab enter", id="search-input", classes="hidden")
        search_input.can_focus = False  # Only focusable when search mode is active
        yield search_input
        yield Static("j/k nav  n new  a attach  / search  ? help  q quit", id="hint", classes="hint")
        # Notification rack from ZenScreen base - must be last for layer ordering
        yield from super().compose()

    async def on_mount(self) -> None:
        """Initialize and start async state watching."""
        # Cache widget references for performance (avoids repeated DOM queries)
        self._session_list = self.query_one("#session-list", SessionList)
        self._output_view = self.query_one("#output-view", OutputView)
        self._info_view = self.query_one("#info-view", SessionInfoView)
        self._hint = self.query_one("#hint", Static)
        self._search_input = self.query_one("#search-input", Input)

        # Subscribe to EventBus for reactive session updates
        self._bus.subscribe(SessionCreatedEvent, self._on_session_event)
        self._bus.subscribe(SessionPausedEvent, self._on_session_event)
        self._bus.subscribe(SessionKilledEvent, self._on_session_event)
        self._bus.subscribe(SessionCleanedEvent, self._on_session_event)

        self._refresh_sessions()
        if self._focus_tmux_session:
            self._select_session_by_tmux_name(self._focus_tmux_session)
        else:
            self._restore_cursor_position()
        self._refresh_selected_output()

        # Start async state watcher (replaces polling)
        self._watcher = SessionStateWatcher(
            AsyncTmuxService(self._manager._tmux),
            self._manager,
            on_state_change=lambda _: self._on_watcher_state_change(),
        )
        await self._watcher.start()

        # Start proxy monitoring if available
        if self._proxy_monitor:
            await self._proxy_monitor.start_monitoring()

    @property
    def session_list(self) -> SessionList:
        """Get cached session list widget."""
        if self._session_list is None:
            self._session_list = self.query_one("#session-list", SessionList)
        return self._session_list

    @property
    def output_view(self) -> OutputView:
        """Get cached output view widget."""
        if self._output_view is None:
            self._output_view = self.query_one("#output-view", OutputView)
        return self._output_view

    @property
    def info_view(self) -> SessionInfoView:
        """Get cached info view widget."""
        if self._info_view is None:
            self._info_view = self.query_one("#info-view", SessionInfoView)
        return self._info_view

    @property
    def hint(self) -> Static:
        """Get cached hint widget."""
        if self._hint is None:
            self._hint = self.query_one("#hint", Static)
        return self._hint

    @property
    def search_input(self) -> Input:
        """Get cached search input widget."""
        if self._search_input is None:
            self._search_input = self.query_one("#search-input", Input)
        return self._search_input

    def _select_session_by_tmux_name(self, tmux_name: str) -> None:
        """Select the session with the given tmux session name."""
        # Find session in visible list
        for i, session in enumerate(self.session_list.sessions):
            if self._manager.get_tmux_session_name(session.id) == tmux_name:
                self.session_list.selected_index = i
                self.session_list.refresh(recompose=True)
                break

    def _restore_cursor_position(self) -> None:
        """Restore cursor to last selected session from persisted state."""
        selected_id = self._manager.selected_session_id
        if not selected_id:
            return
        # Find session index by ID
        for i, session in enumerate(self.session_list.sessions):
            if session.id == selected_id:
                self.session_list.selected_index = i
                break

    def _refresh_selected_output(self) -> None:
        """Refresh output/info view for currently selected session."""
        selected = self.session_list.get_selected()

        if self.info_mode:
            self.info_view.update_session(selected)
        else:
            if selected:
                if not selected.is_active:
                    content = self._build_dead_session_info(selected)
                else:
                    content = self._manager.get_output(selected.id)
                self._update_output_with_context(self.output_view, selected, content)

    def _refresh_sessions(self) -> None:
        """Update session list widget (skipped during move mode to preserve reordering)."""
        if self.session_list.move_mode:
            return  # Don't overwrite user's reordering
        self.session_list.update_sessions(self._manager.sessions)

    def _on_watcher_state_change(self) -> None:
        """Handle state changes from async watcher."""
        self._refresh_sessions()
        if self._streaming:
            self._refresh_selected_output()

    def _start_rapid_refresh(self) -> None:
        """Start rapid async refresh for 3 seconds after session creation."""
        # Cancel any existing rapid refresh
        if self._rapid_refresh_task and not self._rapid_refresh_task.done():
            self._rapid_refresh_task.cancel()
        self._rapid_refresh_task = asyncio.create_task(self._rapid_refresh_async())

    async def _rapid_refresh_async(self) -> None:
        """Async rapid refresh - non-blocking."""
        if not self._watcher:
            return
        for _ in range(6):  # 6 checks over 3 seconds
            try:
                changed = await self._watcher.refresh_now()
                if changed:
                    self._refresh_sessions()
                    self._refresh_selected_output()
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break

    def on_session_selected(self, event: SessionSelected) -> None:
        """Handle session selection changes."""
        session = event.session

        # Persist cursor position (debounced via state save)
        self._manager.set_selected_session(session.id)

        if self.info_mode:
            self.info_view.update_session(session)
        else:
            if not session.is_active:
                content = self._build_dead_session_info(session)
            else:
                content = self._manager.get_output(session.id)
            self._update_output_with_context(self.output_view, session, content)

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

        if session.session_type == SessionType.AI and session.claude_session_id:
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
        self.session_list.move_down()

    def action_move_up(self) -> None:
        self.session_list.move_up()

    def action_toggle_move(self) -> None:
        """Toggle move mode for reordering sessions."""
        if self.session_list.move_mode:
            self.session_list.exit_move_mode()
            self._save_session_order()
            self.zen_notify("order saved")
        else:
            self.session_list.toggle_move_mode()
            self.zen_notify("move mode: j/k to reorder, space/esc to exit")

    def action_escape_handler(self) -> None:
        """Handle escape: exit search mode, then move mode."""
        if self.search_mode:
            self.search_mode = False
        elif self.session_list.move_mode:
            self.session_list.exit_move_mode()
            self._save_session_order()
            self.zen_notify("order saved")

    def _save_session_order(self) -> None:
        """Save current session order to state."""
        order = self.session_list.get_session_order()
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
                        ScreenSessionType.AI: SessionType.AI,
                        ScreenSessionType.SHELL: SessionType.SHELL,
                    }
                    session_type = type_mapping.get(result.session_type, SessionType.AI)
                    provider = result.provider.value if hasattr(result.provider, 'value') else result.provider
                    session = self._manager.create_session(
                        result.name,
                        result.prompt,
                        system_prompt=result.system_prompt,
                        features=result.features,
                        session_type=session_type,
                        provider=provider,
                    )
                    self._refresh_sessions()
                    self.session_list.selected_index = 0
                    self.session_list.refresh(recompose=True)
                    self._start_rapid_refresh()
                    # Show provider name for AI sessions
                    display_type = provider if session_type == SessionType.AI else session_type.value
                    self.zen_notify(f"created {display_type}: {session.display_name}")

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
                        self.session_list.selected_index = 0
                        self.session_list.refresh(recompose=True)
                        self._start_rapid_refresh()

                        # Show appropriate notification based on session state
                        if session.state == SessionState.FAILED:
                            error_msg = session.error_message or "Resume failed"
                            self.zen_notify(error_msg, "error")
                        else:
                            self.zen_notify(f"resumed: {session.display_name}")
            except Exception as e:
                # Log unexpected errors during session creation
                self.zen_notify(f"error: {e}", "error")

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
                existing_sessions=list(self._manager.sessions),
            ),
            handle_result,
        )

    async def action_refresh_output(self) -> None:
        """Manual refresh - triggers async state check."""
        self._refresh_selected_output()
        if self._watcher:
            await self._watcher.refresh_now()
        self._refresh_sessions()

    def action_toggle_streaming(self) -> None:
        self._streaming = not self._streaming
        self.zen_notify(f"output mode: {'streaming' if self._streaming else 'snapshot'}")
        self._update_hint()

    def action_search_output(self) -> None:
        """Activate search in output view (only when not in info mode)."""
        if not self.info_mode:
            try:
                self.output_view.action_toggle_search()
            except Exception:
                pass

    def action_search_sessions(self) -> None:
        """Activate session search mode."""
        self.search_mode = True

    def watch_search_mode(self, search_mode: bool) -> None:
        """Show/hide search input when mode changes."""
        if search_mode:
            self.search_input.can_focus = True
            self.search_input.remove_class("hidden")
            self.search_input.focus()
            # Clear after focus to ensure no stray characters
            self.search_input.value = ""
            # Enable session list focus for Tab navigation
            self.session_list.enable_focus()
        else:
            self.search_input.add_class("hidden")
            self.search_input.can_focus = False  # Prevent focus stealing
            self.session_list.clear_search()
            self.session_list.disable_focus()
            self.focus()  # Return focus to screen for keybindings
            self._update_hint()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update session filter as user types."""
        if event.input.id == "search-input":
            self.session_list.set_search(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Close search on Enter (keep filter active)."""
        if event.input.id == "search-input":
            self.search_mode = False

    def on_key(self, event: Key) -> None:
        """Intercept keys for search mode."""
        if not self.search_mode:
            return
        # Block the initial / that triggered search mode
        if event.key == "slash" and self.search_input.value == "":
            event.prevent_default()
            event.stop()
            return
        # Tab switches focus to session list for navigation
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self.session_list.focus()
        # Up/down arrows navigate even from input
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            self.session_list.move_down()
        elif event.key == "up":
            event.prevent_default()
            event.stop()
            self.session_list.move_up()

    def _exit_search(self) -> None:
        """Exit search mode and clear filter."""
        self.search_mode = False

    def on_search_confirmed(self, event: SearchConfirmed) -> None:
        """Handle search confirmation - keep filter, exit search mode."""
        self.search_mode = False
        self._update_hint()

    def on_search_cancelled(self, event: SearchCancelled) -> None:
        """Handle search cancellation - clear filter and exit."""
        self.search_mode = False

    def action_toggle_info(self) -> None:
        self.info_mode = not self.info_mode

    def watch_info_mode(self, info_mode: bool) -> None:
        try:
            self.output_view.display = not info_mode
            self.info_view.display = info_mode
            self._refresh_selected_output()
            self._update_hint()
            self.zen_notify(f"view: {'info' if info_mode else 'output'}")
        except Exception:
            pass

    def _update_hint(self) -> None:
        base = "j/k nav  n new  a attach  / search  ? help  q quit"
        modes = []
        if self.info_mode:
            modes.append("info")
        if self._streaming:
            modes.append("stream")
        if self.session_list.search_filter:
            modes.append(f"/{self.session_list.search_filter}")
        if modes:
            mode_str = " ".join(modes)
            self.hint.update(f"{base}  [dim]◦ {mode_str}[/dim]")
        else:
            self.hint.update(base)

    def action_config(self) -> None:
        from .config_screen import ConfigScreen
        self.app.push_screen(ConfigScreen(self._config, self._profile))


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

    def _on_session_event(
        self,
        event: SessionCreatedEvent | SessionPausedEvent | SessionKilledEvent | SessionCleanedEvent,
    ) -> None:
        """Handle session lifecycle events from EventBus.

        Reactively refreshes the session list when sessions are created,
        paused, killed, or cleaned. State is already updated by the action
        that triggered the event, so we just refresh the UI.
        """
        self._refresh_sessions()
        self._refresh_selected_output()

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
            self.info_view.refresh()

    async def _cleanup_monitoring(self) -> None:
        """Clean up proxy monitoring on screen exit."""
        if self._proxy_monitor:
            await self._proxy_monitor.stop_monitoring()

    async def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        # Unsubscribe from EventBus
        self._bus.unsubscribe(SessionCreatedEvent, self._on_session_event)
        self._bus.unsubscribe(SessionPausedEvent, self._on_session_event)
        self._bus.unsubscribe(SessionKilledEvent, self._on_session_event)
        self._bus.unsubscribe(SessionCleanedEvent, self._on_session_event)

        # Stop async state watcher
        if self._watcher:
            await self._watcher.stop()

        # Cancel rapid refresh if running
        if self._rapid_refresh_task and not self._rapid_refresh_task.done():
            self._rapid_refresh_task.cancel()

        await self._cleanup_monitoring()
