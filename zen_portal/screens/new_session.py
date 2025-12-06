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
from ..services.config import ConfigManager, ClaudeModel
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
        Binding("ctrl+t", "next_tab", "Next tab", priority=True),  # priority=True to work when Input has focus
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    NewSessionModal {
        align: center middle;
    }

    NewSessionModal #dialog {
        width: 75;
        height: auto;
        max-height: 40;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
        overflow-y: auto;
    }

    NewSessionModal #title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    NewSessionModal TabbedContent {
        height: auto;
        max-height: 30;
    }

    NewSessionModal TabPane {
        padding: 1;
        height: auto;
        max-height: 28;
        overflow-y: auto;
    }

    NewSessionModal .field-label {
        margin-top: 1;
        color: $text-muted;
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
        color: $text-muted;
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
        background: $primary-darken-2;
    }

    NewSessionModal .empty-list {
        color: $text-disabled;
        text-style: italic;
        padding: 1;
        text-align: center;
    }

    NewSessionModal #advanced-config {
        margin-top: 1;
    }

    NewSessionModal #advanced-config CollapsibleTitle {
        padding: 0 1;
        color: $text-muted;
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
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        discovery_service: DiscoveryService | None = None,
        tmux_service: TmuxService | None = None,
        existing_names: set[str] | None = None,
        session_prefix: str = "zen-",
        initial_working_dir: Path | None = None,
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
                    yield Static("type", classes="field-label")
                    yield Select(
                        [
                            (SessionType.CLAUDE.value, SessionType.CLAUDE),
                            (SessionType.CODEX.value, SessionType.CODEX),
                            (SessionType.GEMINI.value, SessionType.GEMINI),
                            (SessionType.SHELL.value, SessionType.SHELL),
                        ],
                        value=SessionType.CLAUDE,
                        id="type-select",
                    )

                    yield Static("name", classes="field-label")
                    default_name = self._get_default_name(SessionType.CLAUDE)
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

            yield Static("^t tabs  tab fields  enter confirm  esc cancel", classes="hint")

    def on_mount(self) -> None:
        """Focus the name input and load lists."""
        self.query_one("#name-input", Input).focus()
        self._load_external_sessions()
        self._load_claude_sessions()

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

        self._refresh_attach_list()

    def _load_claude_sessions(self) -> None:
        """Load recent Claude sessions for resume tab."""
        self._claude_sessions = self._discovery.list_claude_sessions(limit=15)
        self._refresh_resume_list()

    def _refresh_attach_list(self) -> None:
        """Refresh the attach list display."""
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
            attach_list.mount(Static(label, classes=classes, markup=True))

    def _refresh_resume_list(self) -> None:
        """Refresh the resume list display."""
        resume_list = self.query_one("#resume-list", Vertical)
        resume_list.remove_children()

        if not self._claude_sessions:
            resume_list.mount(Static("no claude sessions found", classes="empty-list"))
            return

        for i, session in enumerate(self._claude_sessions):
            short_id = session.session_id[:8]
            project_name = session.project_path.name if session.project_path else "?"
            time_ago = self._format_time_ago(session.modified_at)

            label = f"  {short_id}  {project_name:<25} {time_ago}"
            classes = "list-row selected" if i == self._claude_selected else "list-row"
            resume_list.mount(Static(label, classes=classes))

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

    def key_j(self) -> None:
        """Move selection down in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._external_sessions:
            if self._external_selected < len(self._external_sessions) - 1:
                self._external_selected += 1
                self._refresh_attach_list()
        elif tab == "tab-resume" and self._claude_sessions:
            if self._claude_selected < len(self._claude_sessions) - 1:
                self._claude_selected += 1
                self._refresh_resume_list()

    def key_k(self) -> None:
        """Move selection up in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._external_selected > 0:
            self._external_selected -= 1
            self._refresh_attach_list()
        elif tab == "tab-resume" and self._claude_selected > 0:
            self._claude_selected -= 1
            self._refresh_resume_list()

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

    def action_next_tab(self) -> None:
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
