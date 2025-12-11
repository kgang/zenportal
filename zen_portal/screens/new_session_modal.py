"""NewSessionModal: Create, attach, or resume sessions."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Input, Select, Static, TabbedContent, TabPane

from ..models.session import SessionFeatures
from ..models.new_session import NewSessionType, AIProvider, ResultType, NewSessionResult
from ..services.config import ConfigManager, ClaudeModel, ALL_SESSION_TYPES, ALL_AI_PROVIDERS
from ..services.conflict import detect_conflicts, has_blocking_conflict, ConflictSeverity
from ..services.discovery import DiscoveryService
from ..services.validation import SessionValidator, ValidationResult
from ..services.openrouter_models import OpenRouterModelsService
from ..services.tmux import TmuxService
from ..widgets.directory_browser import DirectoryBrowser
from .new_session_lists import AttachListBuilder, ResumeListBuilder, update_list_selection
from .new_session.css import NEW_SESSION_CSS
from .new_session.billing_widget import BillingWidget, BillingMode

# Re-export for backwards compatibility
SessionType = NewSessionType


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Modal for creating, attaching, or resuming sessions."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = NEW_SESSION_CSS

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
        existing_sessions: list | None = None,
    ) -> None:
        super().__init__()
        self._config = config_manager
        self._discovery = discovery_service or DiscoveryService()
        self._tmux = tmux_service or TmuxService()
        self._models_service = models_service or OpenRouterModelsService()
        self._existing_names = existing_names or set()
        self._prefix = session_prefix
        self._existing_sessions = existing_sessions or []

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

        # Validator for session creation (extracted business logic)
        self._validator = SessionValidator()

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

    def _get_default_name(self, session_type: NewSessionType, provider: AIProvider | None = None) -> str:
        """Generate a smart default name based on session type and context.

        Follows zen principles: use directory name for meaningful context,
        fall back to session type if no directory context available.
        """
        # Use directory name for context (most meaningful default)
        dir_name = self._initial_dir.name if self._initial_dir else ""

        # Fallback to session type if no directory context
        if session_type == NewSessionType.AI and provider:
            fallback = provider.value
        elif session_type == NewSessionType.SHELL:
            fallback = "shell"
        else:
            fallback = "session"

        base = dir_name or fallback
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
        default_type = self._enabled_types[0] if self._enabled_types else NewSessionType.AI

        # Type selector (hidden if only one type)
        if len(type_options) > 1:
            yield Static("type", classes="field-label")
            yield Select(type_options, value=default_type, id="type-select")
        else:
            yield Select(type_options, value=default_type, id="type-select", classes="hidden")

        # Provider selector (for AI sessions)
        provider_options = [(p.value, p) for p in AIProvider]
        default_provider = AIProvider.CLAUDE
        yield Static("provider", classes="field-label", id="provider-label")
        yield Select(provider_options, value=default_provider, id="provider-select")

        yield Static("name", classes="field-label")
        yield Input(
            placeholder="session name",
            value=self._get_default_name(default_type, default_provider if default_type == NewSessionType.AI else None),
            id="name-input",
            classes="field-input",
        )
        yield Static("", id="conflict-hint")

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
            yield BillingWidget(self._config, self._models_service, id="billing-widget")

    def on_mount(self) -> None:
        """Focus the name input and load lists."""
        self.trap_focus = True
        self.query_one("#name-input", Input).focus()
        self._load_lists()
        self._set_initial_visibility()
        self._check_conflicts()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Check for conflicts when name changes."""
        if event.input.id == "name-input":
            self._check_conflicts()

    def _check_conflicts(self) -> None:
        """Check for conflicts and validation issues, update hint."""
        name = self.query_one("#name-input", Input).value.strip()
        type_select = self.query_one("#type-select", Select)
        session_type = type_select.value if type_select.value is not Select.BLANK else NewSessionType.AI

        # Use validator for name validation
        existing_names = {s.name for s in self._existing_sessions}
        validation = self._validator.validate_name(name, existing_names)

        # Convert NewSessionType to SessionType for conflict detection
        from ..models.session import SessionType
        session_type_map = {
            NewSessionType.AI: SessionType.AI,
            NewSessionType.SHELL: SessionType.SHELL,
        }

        conflicts = detect_conflicts(
            name=name,
            session_type=session_type_map.get(session_type, SessionType.AI),
            existing=self._existing_sessions,
        )

        self._update_conflict_display(conflicts, validation)

    def _update_conflict_display(
        self,
        conflicts: list,
        validation: ValidationResult | None = None,
    ) -> None:
        """Update the conflict hint display."""
        hint = self.query_one("#conflict-hint", Static)
        hint.remove_class("warning", "error")

        # Prioritize validation errors over conflicts
        if validation and not validation.is_valid:
            hint.update(validation.first_error or "")
            hint.add_class("error")
            return

        # Show validation warnings
        if validation and validation.first_warning:
            hint.update(validation.first_warning)
            hint.add_class("warning")
            return

        if not conflicts:
            hint.update("")
            return

        # Show highest priority conflict
        for severity in (ConflictSeverity.ERROR, ConflictSeverity.WARNING, ConflictSeverity.INFO):
            for c in conflicts:
                if c.severity == severity:
                    hint.update(c.message)
                    if severity == ConflictSeverity.WARNING:
                        hint.add_class("warning")
                    elif severity == ConflictSeverity.ERROR:
                        hint.add_class("error")
                    return

    def _load_lists(self) -> None:
        """Load attach and resume lists."""
        self._refresh_attach_list()
        self._refresh_resume_list()

    def _refresh_attach_list(self) -> None:
        """Refresh the attach list (reload from tmux)."""
        old_selected = self._attach_list.selected
        self._attach_list.load_sessions()
        # Preserve selection if still valid
        if old_selected < len(self._attach_list.sessions):
            self._attach_list.selected = old_selected
        else:
            self._attach_list.selected = 0
        self._attach_list.build_list(self.query_one("#attach-list", Vertical))

    def _refresh_resume_list(self) -> None:
        """Refresh the resume list (reload from Claude sessions)."""
        old_selected = self._resume_list.selected
        self._resume_list.load_sessions()
        # Preserve selection if still valid
        if old_selected < len(self._resume_list.sessions):
            self._resume_list.selected = old_selected
        else:
            self._resume_list.selected = 0
        self._resume_list.build_list(self.query_one("#resume-list", Vertical))

    def _set_initial_visibility(self) -> None:
        """Set initial visibility based on default type."""
        if not self._enabled_types:
            return

        default_type = self._enabled_types[0]
        is_ai = default_type == NewSessionType.AI
        is_shell = default_type == NewSessionType.SHELL

        # Show provider selector only for AI sessions
        self.query_one("#provider-label", Static).display = is_ai
        self.query_one("#provider-select", Select).display = is_ai

        # Show prompt for AI sessions
        self.query_one("#prompt-label", Static).display = is_ai
        self.query_one("#prompt-input", Input).display = is_ai

        # Show advanced config only for Claude provider
        provider_select = self.query_one("#provider-select", Select)
        is_claude = is_ai and provider_select.value == AIProvider.CLAUDE
        self.query_one("#advanced-config", Collapsible).display = is_claude

        # Show shell options only for shell sessions
        shell_options = self.query_one("#shell-options", Horizontal)
        shell_options.remove_class("hidden") if is_shell else shell_options.add_class("hidden")

    def _get_active_tab(self) -> str:
        """Get the currently active tab ID."""
        tabs = self.query_one("#tabs", TabbedContent)
        return tabs.active or "tab-new"

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "type-select":
            self._handle_type_change(event.value)
        elif event.select.id == "provider-select":
            self._handle_provider_change(event.value)

    def _handle_type_change(self, value) -> None:
        """Handle session type changes."""
        is_ai = value == NewSessionType.AI
        is_shell = value == NewSessionType.SHELL

        # Show/hide provider selector
        self.query_one("#provider-label", Static).display = is_ai
        self.query_one("#provider-select", Select).display = is_ai

        # Show/hide prompt for AI sessions
        self.query_one("#prompt-label", Static).display = is_ai
        self.query_one("#prompt-input", Input).display = is_ai

        # Show/hide advanced config (only for Claude)
        provider_select = self.query_one("#provider-select", Select)
        is_claude = is_ai and provider_select.value == AIProvider.CLAUDE
        self.query_one("#advanced-config", Collapsible).display = is_claude

        # Show/hide shell options
        shell_options = self.query_one("#shell-options", Horizontal)
        shell_options.remove_class("hidden") if is_shell else shell_options.add_class("hidden")

        # Auto-update name if not customized
        name_input = self.query_one("#name-input", Input)
        provider = provider_select.value if is_ai else None
        if name_input.value.startswith("session") or name_input.value.startswith(self._initial_dir.name):
            name_input.value = self._get_default_name(value, provider)

    def _handle_provider_change(self, value: AIProvider) -> None:
        """Handle AI provider changes."""
        # Show advanced config only for Claude
        is_claude = value == AIProvider.CLAUDE
        self.query_one("#advanced-config", Collapsible).display = is_claude

        # Auto-update name if not customized
        name_input = self.query_one("#name-input", Input)
        if name_input.value.startswith("session") or name_input.value.startswith(self._initial_dir.name):
            type_select = self.query_one("#type-select", Select)
            name_input.value = self._get_default_name(type_select.value, value)

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
        # Refresh lists when switching to attach/resume tabs to prevent stale data
        if event.pane.id == "tab-attach":
            self._refresh_attach_list()
        elif event.pane.id == "tab-resume":
            self._refresh_resume_list()
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

        # Validate name using SessionValidator
        existing_names = {s.name for s in self._existing_sessions}
        validation = self._validator.validate_name(name, existing_names)
        if not validation.is_valid:
            self.notify(validation.first_error or "invalid session name", severity="error")
            return

        type_select = self.query_one("#type-select", Select)
        session_type = type_select.value
        if session_type is Select.BLANK:
            session_type = NewSessionType.AI

        # Get provider for AI sessions
        provider_select = self.query_one("#provider-select", Select)
        provider = provider_select.value if provider_select.value is not Select.BLANK else AIProvider.CLAUDE

        prompt = ""
        model = None
        use_worktree = None

        if session_type == NewSessionType.AI:
            prompt = self.query_one("#prompt-input", Input).value.strip()

            # Advanced options only for Claude
            if provider == AIProvider.CLAUDE:
                model_select = self.query_one("#model-select", Select)
                model = model_select.value if model_select.value is not Select.BLANK else None
                worktree_check = self.query_one("#worktree-check", Checkbox)
                use_worktree = worktree_check.value if worktree_check.value else None

                # Handle billing mode / proxy settings
                try:
                    self.query_one("#billing-widget", BillingWidget).save_settings()
                except Exception:
                    pass

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
            self._config.update_project_features(FeatureSettings(working_dir=working_dir))

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
            provider=provider,
        ))

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
