"""NewSessionModal: Create, attach, or resume sessions."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Input, Select, Static, TabbedContent, TabPane

from ..models.session import SessionFeatures
from ..services.config import ConfigManager, ClaudeModel, ALL_SESSION_TYPES
from ..services.discovery import DiscoveryService, ClaudeSessionInfo, ExternalTmuxSession
from ..services.tmux import TmuxService
from ..widgets.directory_browser import DirectoryBrowser


class SessionType(Enum):
    """Type of session to create."""

    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    SHELL = "shell"


class ResultType(Enum):
    """Type of result from the modal."""

    NEW = "new"
    ATTACH = "attach"
    RESUME = "resume"


@dataclass
class NewSessionResult:
    """Result from new session modal."""

    result_type: ResultType
    # For NEW sessions
    name: str = ""
    prompt: str = ""
    features: SessionFeatures | None = None
    session_type: SessionType = SessionType.CLAUDE
    # For ATTACH sessions
    tmux_session: ExternalTmuxSession | None = None
    # For RESUME sessions
    claude_session: ClaudeSessionInfo | None = None


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Modal for creating, attaching, or resuming sessions."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    NewSessionModal {
        align: center middle;
    }

    NewSessionModal #dialog {
        width: 65;
        height: auto;
        max-height: 36;
        padding: 1 2;
        background: $surface;
        border: round $surface-lighten-1;
        overflow-y: auto;
    }

    NewSessionModal #title {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        color: $text-muted;
    }

    NewSessionModal TabbedContent {
        height: auto;
        max-height: 28;
    }

    NewSessionModal TabPane {
        padding: 1 0;
        height: auto;
        max-height: 26;
        overflow-y: auto;
    }

    NewSessionModal .field-label {
        margin-top: 1;
        color: $text-disabled;
    }

    NewSessionModal .field-input {
        width: 100%;
        margin-bottom: 0;
    }

    NewSessionModal #type-select, #model-select {
        width: 100%;
    }

    NewSessionModal #options-row {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    NewSessionModal .hint {
        text-align: center;
        color: $text-disabled;
        margin-top: 1;
    }

    NewSessionModal .list-container {
        height: auto;
        max-height: 15;
        padding: 0;
    }

    NewSessionModal .list-row {
        height: 1;
        padding: 0 1;
    }

    NewSessionModal .list-row:hover {
        background: $surface-lighten-1;
    }

    NewSessionModal .list-row.selected {
        background: $surface-lighten-1;
    }

    NewSessionModal .empty-list {
        color: $text-disabled;
        padding: 2;
        text-align: center;
    }

    NewSessionModal #advanced-config {
        margin-top: 1;
    }

    NewSessionModal #advanced-config CollapsibleTitle {
        padding: 0 1;
        color: $text-disabled;
    }

    NewSessionModal #dir-path-row {
        width: 100%;
        height: auto;
    }

    NewSessionModal #dir-path-input {
        width: 1fr;
    }

    NewSessionModal #browse-btn {
        width: auto;
        min-width: 8;
        margin-left: 1;
    }

    NewSessionModal #dir-browser {
        display: none;
        margin-top: 1;
    }

    NewSessionModal #dir-browser.visible {
        display: block;
    }

    NewSessionModal Select.hidden {
        display: none;
    }
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        discovery_service: DiscoveryService | None = None,
        tmux_service: TmuxService | None = None,
        existing_names: set[str] | None = None,
        session_prefix: str = "zen-",
        initial_working_dir: Path | None = None,
        known_claude_session_ids: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._config = config_manager
        self._discovery = discovery_service or DiscoveryService()
        self._tmux = tmux_service or TmuxService()
        self._existing_names = existing_names or set()
        self._prefix = session_prefix
        # Resolve initial working directory
        resolved = self._config.resolve_features()
        self._initial_dir = initial_working_dir or resolved.working_dir or Path.cwd()
        # External tmux sessions for attach tab
        self._external_sessions: list[ExternalTmuxSession] = []
        self._external_selected = 0
        # Claude sessions for resume tab
        self._claude_sessions: list[ClaudeSessionInfo] = []
        self._claude_selected = 0
        # Enabled session types from config
        self._enabled_types = self._get_enabled_session_types()
        # Known Claude session IDs from zen-portal state (for tagging)
        self._known_claude_ids = known_claude_session_ids or set()

    def _get_enabled_session_types(self) -> list[SessionType]:
        """Get enabled session types from config."""
        resolved = self._config.resolve_features()
        enabled = resolved.enabled_session_types
        if enabled is None:
            # None means all types enabled
            return list(SessionType)
        # Map string values to SessionType enum
        return [SessionType(t) for t in enabled if t in [st.value for st in SessionType]]

    def _generate_unique_name(self, base: str = "session") -> str:
        """Generate a unique session name."""
        if base not in self._existing_names:
            return base
        counter = 1
        while f"{base}-{counter}" in self._existing_names:
            counter += 1
        return f"{base}-{counter}"

    def _get_default_name(self, session_type: SessionType) -> str:
        """Generate a smart default name based on session type."""
        if session_type == SessionType.SHELL:
            # Use directory name for shell sessions
            base = self._initial_dir.name or "shell"
        else:
            base = "session"
        return self._generate_unique_name(base)

    def compose(self) -> ComposeResult:
        resolved = self._config.resolve_features()

        with Vertical(id="dialog"):
            yield Static("session", id="title")

            with TabbedContent(id="tabs"):
                # Tab 1: New session
                with TabPane("new", id="tab-new"):
                    # Type selector at the top for discoverability
                    # Only show enabled session types
                    type_options = [
                        (st.value, st) for st in SessionType if st in self._enabled_types
                    ]
                    default_type = self._enabled_types[0] if self._enabled_types else SessionType.CLAUDE
                    # Only show type selector if more than one type is enabled
                    if len(type_options) > 1:
                        yield Static("type", classes="field-label")
                        yield Select(type_options, value=default_type, id="type-select")
                    else:
                        # Hidden select with default value for single-type mode
                        yield Select(type_options, value=default_type, id="type-select", classes="hidden")

                    yield Static("name", classes="field-label")
                    default_name = self._get_default_name(default_type)
                    yield Input(
                        placeholder="session name",
                        value=default_name,
                        id="name-input",
                        classes="field-input",
                    )

                    yield Static("prompt", classes="field-label", id="prompt-label")
                    yield Input(
                        placeholder="initial prompt for claude",
                        id="prompt-input",
                        classes="field-input",
                    )

                    yield Static("directory", classes="field-label", id="dir-label")
                    with Horizontal(id="dir-path-row"):
                        yield Input(
                            placeholder="working directory",
                            value=str(self._initial_dir),
                            id="dir-path-input",
                            classes="field-input",
                        )
                        yield Button("browse", id="browse-btn", variant="default")

                    yield DirectoryBrowser(initial_path=self._initial_dir, id="dir-browser", show_hint=False)

                    with Collapsible(title="advanced", id="advanced-config", collapsed=True):
                        yield Static("model", classes="field-label", id="model-label")
                        model_options = [
                            ("default", None),
                            (ClaudeModel.SONNET.value, ClaudeModel.SONNET),
                            (ClaudeModel.OPUS.value, ClaudeModel.OPUS),
                            (ClaudeModel.HAIKU.value, ClaudeModel.HAIKU),
                        ]
                        yield Select(model_options, value=resolved.model, id="model-select")

                        with Horizontal(id="options-row"):
                            yield Checkbox("worktree", id="worktree-check")
                            yield Checkbox("dangerous", id="dangerous-check")

                        with Horizontal(id="default-dir-row"):
                            yield Checkbox("set as default dir", id="set-default-dir-check")

                # Tab 2: Attach to existing tmux
                with TabPane("attach", id="tab-attach"):
                    yield Static("tmux sessions", classes="field-label")
                    yield Vertical(id="attach-list", classes="list-container")

                # Tab 3: Resume Claude session
                with TabPane("resume", id="tab-resume"):
                    yield Static("recent claude sessions", classes="field-label")
                    yield Vertical(id="resume-list", classes="list-container")

            yield Static("h/l tabs  j/k select  enter confirm  esc cancel", classes="hint")

    def on_mount(self) -> None:
        """Focus the name input and load lists."""
        self.query_one("#name-input", Input).focus()
        self._load_external_sessions()
        self._load_claude_sessions()
        # Set initial visibility based on default type
        if self._enabled_types:
            default_type = self._enabled_types[0]
            is_ai_session = default_type in (SessionType.CLAUDE, SessionType.CODEX, SessionType.GEMINI)
            is_claude = default_type == SessionType.CLAUDE
            self.query_one("#prompt-label", Static).display = is_ai_session
            self.query_one("#prompt-input", Input).display = is_ai_session
            self.query_one("#advanced-config", Collapsible).display = is_claude

    def _load_external_sessions(self) -> None:
        """Load all tmux sessions for attach tab.

        Shows all tmux sessions (including those from other zen-portal instances)
        so user can attach to any session.
        """
        all_names = self._tmux.list_sessions()
        self._external_sessions = []

        for name in all_names:
            info = self._tmux.get_session_info(name)
            session = self._discovery.analyze_tmux_session(info)
            if not session.is_dead:
                self._external_sessions.append(session)

        self._build_attach_list()

    def _load_claude_sessions(self) -> None:
        """Load recent Claude sessions for resume tab."""
        self._claude_sessions = self._discovery.list_claude_sessions(limit=15)
        self._build_resume_list()

    def _build_attach_list(self) -> None:
        """Build the attach list display (called once on load)."""
        attach_list = self.query_one("#attach-list", Vertical)
        attach_list.remove_children()

        if not self._external_sessions:
            attach_list.mount(Static("no tmux sessions", classes="empty-list"))
            return

        for i, session in enumerate(self._external_sessions):
            glyph = "[green]●[/green]" if session.has_claude else "○"
            cmd = session.command or "?"
            cwd_name = session.cwd.name if session.cwd else ""

            label = f"{glyph} {session.name:<20} {cmd:<10} {cwd_name}"
            classes = "list-row selected" if i == self._external_selected else "list-row"
            attach_list.mount(Static(label, id=f"attach-row-{i}", classes=classes, markup=True))

    def _update_attach_selection(self, old_idx: int, new_idx: int) -> None:
        """Update selection styling without rebuilding the list."""
        if old_idx == new_idx:
            return
        try:
            old_row = self.query_one(f"#attach-row-{old_idx}", Static)
            old_row.remove_class("selected")
        except Exception:
            pass
        try:
            new_row = self.query_one(f"#attach-row-{new_idx}", Static)
            new_row.add_class("selected")
        except Exception:
            pass

    def _build_resume_list(self) -> None:
        """Build the resume list display (called once on load).

        Sessions known to zen-portal (via state) are tagged with a glyph.
        """
        resume_list = self.query_one("#resume-list", Vertical)
        resume_list.remove_children()

        if not self._claude_sessions:
            resume_list.mount(Static("no claude sessions found", classes="empty-list"))
            return

        for i, session in enumerate(self._claude_sessions):
            short_id = session.session_id[:8]
            project_name = session.project_path.name if session.project_path else "?"
            time_ago = self._format_time_ago(session.modified_at)

            # Tag sessions known to zen-portal
            is_known = session.session_id in self._known_claude_ids
            glyph = "[cyan]●[/cyan]" if is_known else "○"

            label = f"{glyph} {short_id}  {project_name:<24} {time_ago}"
            classes = "list-row selected" if i == self._claude_selected else "list-row"
            resume_list.mount(Static(label, id=f"resume-row-{i}", classes=classes, markup=True))

    def _update_resume_selection(self, old_idx: int, new_idx: int) -> None:
        """Update selection styling without rebuilding the list."""
        if old_idx == new_idx:
            return
        try:
            old_row = self.query_one(f"#resume-row-{old_idx}", Static)
            old_row.remove_class("selected")
        except Exception:
            pass
        try:
            new_row = self.query_one(f"#resume-row-{new_idx}", Static)
            new_row.add_class("selected")
        except Exception:
            pass

    def _format_time_ago(self, dt) -> str:
        """Format a datetime as a human-readable time ago string."""
        from datetime import datetime
        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return "now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"

    def _get_active_tab(self) -> str:
        """Get the currently active tab ID."""
        tabs = self.query_one("#tabs", TabbedContent)
        return tabs.active or "tab-new"

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle session type changes."""
        if event.select.id == "type-select":
            is_ai_session = event.value in (SessionType.CLAUDE, SessionType.CODEX, SessionType.GEMINI)
            is_claude = event.value == SessionType.CLAUDE
            # Toggle visibility of prompt (for AI sessions)
            self.query_one("#prompt-label", Static).display = is_ai_session
            self.query_one("#prompt-input", Input).display = is_ai_session
            # Hide advanced config for non-Claude (it contains Claude-specific options)
            self.query_one("#advanced-config", Collapsible).display = is_claude

            # Update default name based on session type
            name_input = self.query_one("#name-input", Input)
            current_name = name_input.value
            # Only auto-update if user hasn't customized the name
            if current_name.startswith("session") or current_name.startswith(self._initial_dir.name):
                new_default = self._get_default_name(event.value)
                name_input.value = new_default

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-btn":
            self._toggle_directory_browser()

    def _toggle_directory_browser(self) -> None:
        """Toggle the directory browser visibility."""
        dir_browser = self.query_one("#dir-browser", DirectoryBrowser)
        if dir_browser.has_class("visible"):
            dir_browser.remove_class("visible")
        else:
            dir_browser.add_class("visible")
            dir_browser.focus()

    def on_directory_browser_path_changed(self, event: DirectoryBrowser.PathChanged) -> None:
        """Update path input when directory browser path changes."""
        self.query_one("#dir-path-input", Input).value = str(event.path)

    def on_directory_browser_directory_selected(self, event: DirectoryBrowser.DirectorySelected) -> None:
        """Handle directory selection from browser."""
        self.query_one("#dir-path-input", Input).value = str(event.path)
        self.query_one("#dir-browser", DirectoryBrowser).remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter in input fields."""
        if event.input.id == "dir-path-input":
            # Navigate directory browser to entered path
            path_str = event.value.strip()
            if path_str.startswith("~"):
                path_str = str(Path.home()) + path_str[1:]
            try:
                path = Path(path_str).expanduser().resolve()
                if path.is_dir():
                    self.query_one("#dir-browser", DirectoryBrowser).set_path(path)
            except Exception:
                pass
        elif event.input.id in ("name-input", "prompt-input"):
            self._submit()

    def action_cancel(self) -> None:
        """Cancel the modal."""
        self.dismiss(None)

    def _is_in_new_tab_input(self) -> bool:
        """Check if focus is in an input field on the new tab."""
        tab = self._get_active_tab()
        if tab != "tab-new":
            return False
        # Check if any input has focus
        try:
            for input_widget in self.query(Input):
                if input_widget.has_focus:
                    return True
        except Exception:
            pass
        return False

    def on_key(self, event) -> None:
        """Handle key events, including those that need to work in Input fields."""
        # ctrl+t cycles tabs even when Input has focus
        if event.key == "ctrl+t":
            event.prevent_default()
            event.stop()
            self._next_tab()
            return

        # h/l for tab navigation (only when not in input)
        if not self._is_in_new_tab_input():
            if event.key == "h":
                event.prevent_default()
                event.stop()
                self._prev_tab()
                return
            elif event.key == "l":
                event.prevent_default()
                event.stop()
                self._next_tab()
                return
            elif event.key == "j":
                event.prevent_default()
                event.stop()
                self._select_next()
                return
            elif event.key == "k":
                event.prevent_default()
                event.stop()
                self._select_prev()
                return
            elif event.key in ("space", "f"):
                # space/f to confirm selection on attach/resume tabs
                tab = self._get_active_tab()
                if tab in ("tab-attach", "tab-resume"):
                    event.prevent_default()
                    event.stop()
                    self._submit()
                    return

    def _select_next(self) -> None:
        """Move selection down in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._external_sessions:
            if self._external_selected < len(self._external_sessions) - 1:
                old_idx = self._external_selected
                self._external_selected += 1
                self._update_attach_selection(old_idx, self._external_selected)
        elif tab == "tab-resume" and self._claude_sessions:
            if self._claude_selected < len(self._claude_sessions) - 1:
                old_idx = self._claude_selected
                self._claude_selected += 1
                self._update_resume_selection(old_idx, self._claude_selected)

    def _select_prev(self) -> None:
        """Move selection up in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._external_selected > 0:
            old_idx = self._external_selected
            self._external_selected -= 1
            self._update_attach_selection(old_idx, self._external_selected)
        elif tab == "tab-resume" and self._claude_selected > 0:
            old_idx = self._claude_selected
            self._claude_selected -= 1
            self._update_resume_selection(old_idx, self._claude_selected)

    def key_enter(self) -> None:
        """Submit on enter (unless in directory browser)."""
        # Check if directory browser has focus
        try:
            dir_browser = self.query_one("#dir-browser", DirectoryBrowser)
            if dir_browser.has_focus or any(
                child.has_focus for child in dir_browser.query("*")
            ):
                return  # Let directory browser handle it
        except Exception:
            pass

        self._submit()

    def _next_tab(self) -> None:
        """Switch to the next tab."""
        tabs = self.query_one("#tabs", TabbedContent)
        tab_ids = ["tab-new", "tab-attach", "tab-resume"]
        current = tabs.active or "tab-new"
        try:
            current_idx = tab_ids.index(current)
            next_idx = (current_idx + 1) % len(tab_ids)
            tabs.active = tab_ids[next_idx]
            self._focus_for_tab(tab_ids[next_idx])
        except ValueError:
            tabs.active = "tab-new"
            self._focus_for_tab("tab-new")

    def _prev_tab(self) -> None:
        """Switch to the previous tab."""
        tabs = self.query_one("#tabs", TabbedContent)
        tab_ids = ["tab-new", "tab-attach", "tab-resume"]
        current = tabs.active or "tab-new"
        try:
            current_idx = tab_ids.index(current)
            prev_idx = (current_idx - 1) % len(tab_ids)
            tabs.active = tab_ids[prev_idx]
            self._focus_for_tab(tab_ids[prev_idx])
        except ValueError:
            tabs.active = "tab-new"
            self._focus_for_tab("tab-new")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation (e.g., when clicked)."""
        self._focus_for_tab(event.pane.id)

    def _focus_for_tab(self, tab_id: str) -> None:
        """Set appropriate focus for the given tab."""
        if tab_id == "tab-new":
            self.query_one("#name-input", Input).focus()
        else:
            # For attach/resume tabs, blur any inputs to prevent Enter capture
            # Focus the screen itself so Enter goes to key_enter
            self.focus()

    def _submit(self) -> None:
        """Submit based on active tab."""
        tab = self._get_active_tab()

        if tab == "tab-new":
            self._submit_new()
        elif tab == "tab-attach":
            self._submit_attach()
        elif tab == "tab-resume":
            self._submit_resume()

    def _submit_new(self) -> None:
        """Create a new session."""
        name_input = self.query_one("#name-input", Input)
        prompt_input = self.query_one("#prompt-input", Input)
        dir_path_input = self.query_one("#dir-path-input", Input)
        type_select = self.query_one("#type-select", Select)
        model_select = self.query_one("#model-select", Select)
        worktree_check = self.query_one("#worktree-check", Checkbox)
        dangerous_check = self.query_one("#dangerous-check", Checkbox)
        set_default_check = self.query_one("#set-default-dir-check", Checkbox)

        name = name_input.value.strip()
        if not name:
            self.app.notify("enter a session name", severity="warning")
            return

        session_type = type_select.value
        if session_type is Select.BLANK:
            session_type = SessionType.CLAUDE

        prompt = ""
        model = None

        if session_type == SessionType.CLAUDE:
            prompt = prompt_input.value.strip()
            model = model_select.value if model_select.value is not Select.BLANK else None

        # Get working directory from path input
        path_str = dir_path_input.value.strip()
        if path_str.startswith("~"):
            path_str = str(Path.home()) + path_str[1:]
        try:
            working_dir = Path(path_str).expanduser().resolve()
            if not working_dir.is_dir():
                working_dir = self._initial_dir
        except Exception:
            working_dir = self._initial_dir

        # Save as default directory if checkbox is checked
        if set_default_check.value:
            from ..services.config import FeatureSettings
            self._config.update_portal_features(FeatureSettings(working_dir=working_dir))

        features = SessionFeatures(
            working_dir=working_dir,
            model=model,
            use_worktree=worktree_check.value if worktree_check.value else None,
            dangerously_skip_permissions=dangerous_check.value,
        )

        self.dismiss(NewSessionResult(
            result_type=ResultType.NEW,
            name=name,
            prompt=prompt,
            features=features,
            session_type=session_type,
        ))

    def _submit_attach(self) -> None:
        """Attach to external tmux session."""
        if not self._external_sessions:
            self.app.notify("no sessions to attach", severity="warning")
            return

        if self._external_selected >= len(self._external_sessions):
            return

        session = self._external_sessions[self._external_selected]
        self.dismiss(NewSessionResult(
            result_type=ResultType.ATTACH,
            tmux_session=session,
        ))

    def _submit_resume(self) -> None:
        """Resume a Claude session."""
        if not self._claude_sessions:
            self.app.notify("no sessions to resume", severity="warning")
            return

        if self._claude_selected >= len(self._claude_sessions):
            return

        session = self._claude_sessions[self._claude_selected]
        self.dismiss(NewSessionResult(
            result_type=ResultType.RESUME,
            claude_session=session,
        ))
