"""NewSessionModal: Create, attach, or resume sessions."""

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Input, Select, Static, TabbedContent, TabPane

from ..models.session import SessionFeatures
from ..models.new_session import NewSessionType, ResultType, NewSessionResult
from ..services.config import ConfigManager, ClaudeModel, ProxySettings, ALL_SESSION_TYPES
from ..services.discovery import DiscoveryService
from ..services.openrouter_models import OpenRouterModelsService
from ..services.tmux import TmuxService
from ..services.proxy_validation import ProxyValidator, ProxyStatus
from ..widgets.directory_browser import DirectoryBrowser
from ..widgets.model_selector import ModelSelector
from .new_session_lists import AttachListBuilder, ResumeListBuilder, update_list_selection

# Re-export for backwards compatibility
SessionType = NewSessionType


class BillingMode:
    """Billing mode for Claude sessions."""
    CLAUDE = "claude"  # Use Claude account (default)
    OPENROUTER = "openrouter"  # Pay-per-token via y-router


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Modal for creating, attaching, or resuming sessions."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    /* Component-specific: tabs and form layout */
    NewSessionModal TabbedContent {
        height: auto;
    }

    NewSessionModal TabPane {
        padding: 1 0;
        height: auto;
        overflow-y: auto;
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

    NewSessionModal .list-container {
        height: auto;
        max-height: 30vh;
        min-height: 8;
        padding: 0;
        overflow-y: auto;
    }

    NewSessionModal #advanced-config {
        margin-top: 1;
    }

    NewSessionModal #advanced-config CollapsibleTitle {
        padding: 0 1;
        color: $text-disabled;
    }

    NewSessionModal #advanced-config Contents {
        height: auto;
    }

    NewSessionModal #default-dir-row {
        height: auto;
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

    NewSessionModal #shell-options {
        margin-top: 1;
        height: auto;
    }

    NewSessionModal #shell-options.hidden {
        display: none;
    }

    NewSessionModal #billing-section {
        margin-top: 0;
    }

    NewSessionModal #billing-section.hidden {
        display: none;
    }

    NewSessionModal #proxy-config {
        height: auto;
        margin-top: 1;
    }

    NewSessionModal #proxy-config.hidden {
        display: none;
    }

    NewSessionModal .proxy-row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    NewSessionModal .proxy-label {
        color: $text-muted;
        height: 1;
    }

    NewSessionModal .proxy-input {
        width: 100%;
    }

    NewSessionModal .proxy-status {
        height: 1;
        margin-top: 1;
    }

    NewSessionModal .proxy-status-ok {
        color: $success;
    }

    NewSessionModal .proxy-status-warning {
        color: $warning;
    }

    NewSessionModal .proxy-status-error {
        color: $error;
    }

    NewSessionModal .proxy-hint {
        color: $text-disabled;
        height: auto;
    }

    NewSessionModal ModelSelector {
        width: 100%;
        margin-bottom: 0;
    }

    NewSessionModal ModelSelector #model-input {
        border: tall $surface-lighten-1;
    }

    NewSessionModal ModelSelector #dropdown {
        border: round $surface-lighten-1;
        background: $surface;
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
        models_service: OpenRouterModelsService | None = None,
    ) -> None:
        super().__init__()
        self._config = config_manager
        self._discovery = discovery_service or DiscoveryService()
        self._tmux = tmux_service or TmuxService()
        self._models_service = models_service or OpenRouterModelsService()
        self._existing_names = existing_names or set()
        self._prefix = session_prefix

        # Resolve initial working directory
        resolved = self._config.resolve_features()
        self._initial_dir = initial_working_dir or resolved.working_dir or Path.cwd()

        # List builders for attach and resume tabs
        self._attach_list = AttachListBuilder(self._discovery, self._tmux)
        self._resume_list = ResumeListBuilder(
            self._discovery,
            known_claude_session_ids,
        )

        # Enabled session types from config
        self._enabled_types = self._get_enabled_session_types()

    def _get_enabled_session_types(self) -> list[NewSessionType]:
        """Get enabled session types from config."""
        resolved = self._config.resolve_features()
        enabled = resolved.enabled_session_types
        if enabled is None:
            return list(NewSessionType)
        return [NewSessionType(t) for t in enabled if t in [st.value for st in NewSessionType]]

    def _generate_unique_name(self, base: str = "session") -> str:
        """Generate a unique session name."""
        if base not in self._existing_names:
            return base
        counter = 1
        while f"{base}-{counter}" in self._existing_names:
            counter += 1
        return f"{base}-{counter}"

    def _get_default_name(self, session_type: NewSessionType) -> str:
        """Generate a smart default name based on session type."""
        if session_type == NewSessionType.SHELL:
            base = self._initial_dir.name or "shell"
        else:
            base = "session"
        return self._generate_unique_name(base)

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-lg")
        resolved = self._config.resolve_features()

        with Vertical(id="dialog"):
            yield Static("session", classes="dialog-title")

            with TabbedContent(id="tabs"):
                # Tab 1: New session
                with TabPane("new", id="tab-new"):
                    yield from self._compose_new_tab(resolved)

                # Tab 2: Attach to existing tmux
                with TabPane("attach", id="tab-attach"):
                    yield Static("tmux sessions", classes="field-label")
                    yield Vertical(id="attach-list", classes="list-container list-md")

                # Tab 3: Resume Claude session
                with TabPane("resume", id="tab-resume"):
                    yield Static("claude sessions", classes="field-label")
                    yield Vertical(id="resume-list", classes="list-container list-md")

            yield Static("h/l tabs  j/k select  f expand  enter confirm  esc cancel", classes="dialog-hint")

    def _compose_new_tab(self, resolved) -> ComposeResult:
        """Compose the new session tab content."""
        type_options = [
            (st.value, st) for st in NewSessionType if st in self._enabled_types
        ]
        default_type = self._enabled_types[0] if self._enabled_types else NewSessionType.CLAUDE

        # Type selector (hidden if only one type)
        if len(type_options) > 1:
            yield Static("type", classes="field-label")
            yield Select(type_options, value=default_type, id="type-select")
        else:
            yield Select(type_options, value=default_type, id="type-select", classes="hidden")

        yield Static("name", classes="field-label")
        yield Input(
            placeholder="session name",
            value=self._get_default_name(default_type),
            id="name-input",
            classes="field-input",
        )

        yield Static("prompt", classes="field-label", id="prompt-label")
        yield Input(placeholder="initial prompt for claude", id="prompt-input", classes="field-input")

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

        # Shell-specific options
        with Horizontal(id="shell-options", classes="hidden"):
            yield Checkbox("worktree", id="shell-worktree-check")

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

            # Billing mode selector (Claude only)
            yield from self._compose_billing_section(resolved)

    def _compose_billing_section(self, resolved) -> ComposeResult:
        """Compose the billing mode section for Claude sessions."""
        # Get current proxy settings
        proxy = resolved.openrouter_proxy
        proxy_enabled = proxy.enabled if proxy else False
        proxy_key = proxy.api_key if proxy else ""
        proxy_model = proxy.default_model if proxy else ""

        # Determine initial billing mode
        initial_billing = BillingMode.OPENROUTER if proxy_enabled else BillingMode.CLAUDE

        with Vertical(id="billing-section"):
            yield Static("billing", classes="field-label")
            yield Select(
                [
                    ("claude account", BillingMode.CLAUDE),
                    ("openrouter", BillingMode.OPENROUTER),
                ],
                value=initial_billing,
                id="billing-select",
            )

            # Proxy config (shown when openrouter selected)
            with Vertical(id="proxy-config"):
                # Check if API key is available (from env or config)
                has_env_key = bool(os.environ.get("OPENROUTER_API_KEY"))
                has_config_key = bool(proxy_key)
                has_key = has_env_key or has_config_key

                if has_key:
                    yield Static("● ready", id="proxy-status", classes="proxy-status proxy-status-ok")
                    yield Static("", id="proxy-hint", classes="proxy-hint")
                else:
                    yield Static("● needs api key", id="proxy-status", classes="proxy-status proxy-status-warning")
                    yield Static("get key from openrouter.ai/keys", id="proxy-hint", classes="proxy-hint")

                with Vertical(classes="proxy-row"):
                    yield Static("api key (or set OPENROUTER_API_KEY env)", classes="proxy-label")
                    yield Input(
                        value=proxy_key,
                        placeholder="sk-or-...",
                        password=True,
                        id="proxy-key-input",
                        classes="proxy-input",
                    )

                with Vertical(classes="proxy-row"):
                    yield Static("model (optional)", classes="proxy-label")
                    yield ModelSelector(
                        models_service=self._models_service,
                        initial_value=proxy_model,
                        placeholder="anthropic/claude-sonnet-4",
                        id="proxy-model-selector",
                    )

    def on_mount(self) -> None:
        """Focus the name input and load lists."""
        self.query_one("#name-input", Input).focus()
        self._load_lists()
        self._set_initial_visibility()

    def _load_lists(self) -> None:
        """Load attach and resume lists."""
        self._attach_list.load_sessions()
        self._attach_list.build_list(self.query_one("#attach-list", Vertical))

        self._resume_list.load_sessions()
        self._resume_list.build_list(self.query_one("#resume-list", Vertical))

    def _set_initial_visibility(self) -> None:
        """Set initial visibility based on default type."""
        if not self._enabled_types:
            return

        default_type = self._enabled_types[0]
        is_ai = default_type in (NewSessionType.CLAUDE, NewSessionType.CODEX, NewSessionType.GEMINI, NewSessionType.OPENROUTER)
        is_claude = default_type == NewSessionType.CLAUDE
        is_shell = default_type == NewSessionType.SHELL

        self.query_one("#prompt-label", Static).display = is_ai
        self.query_one("#prompt-input", Input).display = is_ai
        self.query_one("#advanced-config", Collapsible).display = is_claude

        shell_options = self.query_one("#shell-options", Horizontal)
        shell_options.remove_class("hidden") if is_shell else shell_options.add_class("hidden")

        # Set initial proxy config visibility based on billing mode
        try:
            billing_select = self.query_one("#billing-select", Select)
            proxy_config = self.query_one("#proxy-config", Vertical)
            proxy_config.display = (billing_select.value == BillingMode.OPENROUTER)
        except Exception:
            pass

    def _get_active_tab(self) -> str:
        """Get the currently active tab ID."""
        tabs = self.query_one("#tabs", TabbedContent)
        return tabs.active or "tab-new"

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "type-select":
            self._handle_type_change(event.value)
        elif event.select.id == "billing-select":
            self._handle_billing_change(event.value)

    def _handle_type_change(self, value) -> None:
        """Handle session type changes."""
        is_ai = value in (NewSessionType.CLAUDE, NewSessionType.CODEX, NewSessionType.GEMINI, NewSessionType.OPENROUTER)
        is_claude = value == NewSessionType.CLAUDE
        is_shell = value == NewSessionType.SHELL

        self.query_one("#prompt-label", Static).display = is_ai
        self.query_one("#prompt-input", Input).display = is_ai
        self.query_one("#advanced-config", Collapsible).display = is_claude

        shell_options = self.query_one("#shell-options", Horizontal)
        shell_options.remove_class("hidden") if is_shell else shell_options.add_class("hidden")

        # Auto-update name if not customized
        name_input = self.query_one("#name-input", Input)
        if name_input.value.startswith("session") or name_input.value.startswith(self._initial_dir.name):
            name_input.value = self._get_default_name(value)

    def _handle_billing_change(self, value) -> None:
        """Handle billing mode changes."""
        try:
            proxy_config = self.query_one("#proxy-config", Vertical)
            show = (value == BillingMode.OPENROUTER)
            proxy_config.display = show
            if show:
                self._update_proxy_status()
        except Exception:
            pass

    def _update_proxy_status(self) -> None:
        """Update proxy status display based on current input."""
        try:
            status_widget = self.query_one("#proxy-status", Static)
            hint_widget = self.query_one("#proxy-hint", Static)

            # Check for API key from input or env
            api_key_input = self.query_one("#proxy-key-input", Input).value.strip()
            has_key = bool(api_key_input or os.environ.get("OPENROUTER_API_KEY"))

            status_widget.remove_class("proxy-status-ok", "proxy-status-warning", "proxy-status-error")

            if has_key:
                status_widget.update("● ready")
                status_widget.add_class("proxy-status-ok")
                hint_widget.update("")
            else:
                status_widget.update("● needs api key")
                status_widget.add_class("proxy-status-warning")
                hint_widget.update("get key from openrouter.ai/keys")
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "proxy-key-input":
            self._update_proxy_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
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
        self.query_one("#dir-path-input", Input).value = str(event.path)

    def on_directory_browser_directory_selected(self, event: DirectoryBrowser.DirectorySelected) -> None:
        self.query_one("#dir-path-input", Input).value = str(event.path)
        self.query_one("#dir-browser", DirectoryBrowser).remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "dir-path-input":
            self._handle_dir_input_submit(event.value)
        elif event.input.id in ("name-input", "prompt-input"):
            self._submit()

    def _handle_dir_input_submit(self, path_str: str) -> None:
        """Handle enter on directory path input."""
        path_str = path_str.strip()
        if path_str.startswith("~"):
            path_str = str(Path.home()) + path_str[1:]
        try:
            path = Path(path_str).expanduser().resolve()
            if path.is_dir():
                self.query_one("#dir-browser", DirectoryBrowser).set_path(path)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _is_in_new_tab_input(self) -> bool:
        """Check if focus is in an input field on the new tab."""
        if self._get_active_tab() != "tab-new":
            return False
        try:
            for input_widget in self.query(Input):
                if input_widget.has_focus:
                    return True
        except Exception:
            pass
        return False

    def _cycle_select_value(self, select: Select, forward: bool) -> None:
        """Cycle through Select options with j/k."""
        options = select._options
        if not options:
            return

        current_value = select.value
        current_idx = -1
        for i, (_, value) in enumerate(options):
            if value == current_value:
                current_idx = i
                break

        if current_idx == -1:
            current_idx = 1 if len(options) > 1 and options[0][1] == Select.BLANK else 0

        start_idx = 1 if options[0][1] == Select.BLANK else 0
        end_idx = len(options) - 1

        if forward:
            new_idx = current_idx + 1 if current_idx < end_idx else start_idx
        else:
            new_idx = current_idx - 1 if current_idx > start_idx else end_idx

        select.value = options[new_idx][1]

    def on_key(self, event) -> None:
        """Handle key events."""
        # ctrl+t cycles tabs even when Input has focus
        if event.key == "ctrl+t":
            event.prevent_default()
            event.stop()
            self._next_tab()
            return

        # Handle j/k in type-select dropdown
        type_select = self.query_one("#type-select", Select)
        if type_select.has_focus:
            if event.key == "j":
                event.prevent_default()
                event.stop()
                self._cycle_select_value(type_select, forward=True)
                return
            elif event.key == "k":
                event.prevent_default()
                event.stop()
                self._cycle_select_value(type_select, forward=False)
                return

        # h/l for tab navigation (only when not in input)
        if not self._is_in_new_tab_input():
            if event.key == "h":
                event.prevent_default()
                event.stop()
                self._prev_tab()
            elif event.key == "l":
                event.prevent_default()
                event.stop()
                self._next_tab()
            elif event.key == "j":
                event.prevent_default()
                event.stop()
                self._select_next()
            elif event.key == "k":
                event.prevent_default()
                event.stop()
                self._select_prev()
            elif event.key == "f":
                event.prevent_default()
                event.stop()
                self._handle_focus_expand()
            elif event.key == "space":
                tab = self._get_active_tab()
                if tab in ("tab-attach", "tab-resume"):
                    event.prevent_default()
                    event.stop()
                    self._submit()

    def _handle_focus_expand(self) -> None:
        """Handle f key to focus/expand appropriate element."""
        tab = self._get_active_tab()
        if tab != "tab-new":
            self._submit()
            return

        type_select = self.query_one("#type-select", Select)
        browse_btn = self.query_one("#browse-btn", Button)
        dir_input = self.query_one("#dir-path-input", Input)
        advanced = self.query_one("#advanced-config", Collapsible)

        if type_select.has_focus:
            if type_select.expanded:
                type_select.action_dismiss()
            else:
                type_select.action_show_overlay()
        elif browse_btn.has_focus or dir_input.has_focus:
            self._toggle_directory_browser()
        elif advanced.has_focus:
            advanced.collapsed = not advanced.collapsed
        else:
            self._toggle_directory_browser()

    def _select_next(self) -> None:
        """Move selection down in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._attach_list.sessions:
            if self._attach_list.selected < len(self._attach_list.sessions) - 1:
                old_idx = self._attach_list.selected
                self._attach_list.selected += 1
                update_list_selection(self.query_one, "attach-row-", old_idx, self._attach_list.selected)
        elif tab == "tab-resume" and self._resume_list.sessions:
            if self._resume_list.selected < len(self._resume_list.sessions) - 1:
                old_idx = self._resume_list.selected
                self._resume_list.selected += 1
                update_list_selection(self.query_one, "resume-row-", old_idx, self._resume_list.selected)

    def _select_prev(self) -> None:
        """Move selection up in attach/resume lists."""
        tab = self._get_active_tab()
        if tab == "tab-attach" and self._attach_list.selected > 0:
            old_idx = self._attach_list.selected
            self._attach_list.selected -= 1
            update_list_selection(self.query_one, "attach-row-", old_idx, self._attach_list.selected)
        elif tab == "tab-resume" and self._resume_list.selected > 0:
            old_idx = self._resume_list.selected
            self._resume_list.selected -= 1
            update_list_selection(self.query_one, "resume-row-", old_idx, self._resume_list.selected)

    def key_enter(self) -> None:
        """Submit on enter (unless in directory browser)."""
        try:
            dir_browser = self.query_one("#dir-browser", DirectoryBrowser)
            if dir_browser.has_focus or any(child.has_focus for child in dir_browser.query("*")):
                return
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

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._focus_for_tab(event.pane.id)

    def _focus_for_tab(self, tab_id: str) -> None:
        """Set appropriate focus for the given tab."""
        if tab_id == "tab-new":
            self.query_one("#name-input", Input).focus()
        else:
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
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            self.post_message(self.app.notification_service.warning("enter a session name"))
            return

        type_select = self.query_one("#type-select", Select)
        session_type = type_select.value
        if session_type is Select.BLANK:
            session_type = NewSessionType.CLAUDE

        prompt = ""
        model = None
        use_worktree = None

        if session_type == NewSessionType.CLAUDE:
            prompt = self.query_one("#prompt-input", Input).value.strip()
            model_select = self.query_one("#model-select", Select)
            model = model_select.value if model_select.value is not Select.BLANK else None
            worktree_check = self.query_one("#worktree-check", Checkbox)
            use_worktree = worktree_check.value if worktree_check.value else None

            # Handle billing mode / proxy settings
            self._save_billing_settings()

        elif session_type in (NewSessionType.CODEX, NewSessionType.GEMINI, NewSessionType.OPENROUTER):
            prompt = self.query_one("#prompt-input", Input).value.strip()
        elif session_type == NewSessionType.SHELL:
            shell_worktree = self.query_one("#shell-worktree-check", Checkbox)
            use_worktree = shell_worktree.value if shell_worktree.value else None

        # Get working directory
        path_str = self.query_one("#dir-path-input", Input).value.strip()
        if path_str.startswith("~"):
            path_str = str(Path.home()) + path_str[1:]
        try:
            working_dir = Path(path_str).expanduser().resolve()
            if not working_dir.is_dir():
                working_dir = self._initial_dir
        except Exception:
            working_dir = self._initial_dir

        # Save as default if checked
        if self.query_one("#set-default-dir-check", Checkbox).value:
            from ..services.config import FeatureSettings
            self._config.update_portal_features(FeatureSettings(working_dir=working_dir))

        dangerous_check = self.query_one("#dangerous-check", Checkbox)
        features = SessionFeatures(
            working_dir=working_dir,
            model=model,
            use_worktree=use_worktree,
            dangerously_skip_permissions=dangerous_check.value,
        )

        self.dismiss(NewSessionResult(
            result_type=ResultType.NEW,
            name=name,
            prompt=prompt,
            features=features,
            session_type=session_type,
        ))

    def _save_billing_settings(self) -> None:
        """Save billing/proxy settings to config."""
        try:
            billing_select = self.query_one("#billing-select", Select)
            billing_mode = billing_select.value

            if billing_mode == BillingMode.OPENROUTER:
                # Get proxy settings from form
                api_key = self.query_one("#proxy-key-input", Input).value.strip()
                model_selector = self.query_one("#proxy-model-selector", ModelSelector)
                model = model_selector.get_value().strip()

                # Create proxy settings (enabled)
                proxy_settings = ProxySettings(
                    enabled=True,
                    api_key=api_key,
                    default_model=model,
                )

                # Save to config
                config = self._config.config
                config.features.openrouter_proxy = proxy_settings
                self._config.save_config(config)
            else:
                # Disable proxy if switching to Claude account
                config = self._config.config
                if config.features.openrouter_proxy:
                    config.features.openrouter_proxy.enabled = False
                    self._config.save_config(config)
        except Exception:
            pass  # Non-critical - continue with session creation

    def _submit_attach(self) -> None:
        """Attach to external tmux session."""
        session = self._attach_list.get_selected()
        if not session:
            self.post_message(self.app.notification_service.warning("no sessions to attach"))
            return
        self.dismiss(NewSessionResult(result_type=ResultType.ATTACH, tmux_session=session))

    def _submit_resume(self) -> None:
        """Resume a Claude session."""
        session = self._resume_list.get_selected()
        if not session:
            self.post_message(self.app.notification_service.warning("no sessions to resume"))
            return
        self.dismiss(NewSessionResult(result_type=ResultType.RESUME, claude_session=session))
