"""ConfigScreen: Settings configuration with keyboard navigation."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Static, Select, OptionList, Checkbox, Input, Collapsible
from textual.widgets.option_list import Option

from ..services.config import ConfigManager, ExitBehavior, FeatureSettings, OpenRouterProxySettings, ALL_SESSION_TYPES
from ..services.profile import ProfileManager
from ..widgets.session_type_dropdown import SessionTypeDropdown
from ..widgets.path_input import PathInput


# Available themes
THEMES = [
    ("textual-dark", "Dark (default)"),
    ("textual-light", "Light"),
    ("nord", "Nord"),
    ("gruvbox", "Gruvbox"),
    ("catppuccin-mocha", "Catppuccin Mocha"),
    ("dracula", "Dracula"),
    ("monokai", "Monokai"),
    ("tokyo-night", "Tokyo Night"),
    ("solarized-light", "Solarized Light"),
]


class ConfigScreen(ModalScreen[None]):
    """Configuration settings screen with keyboard navigation.

    Keyboard:
        j/down  - Move selection down
        k/up    - Move selection up
        tab     - Next section
        enter   - Select/toggle
        esc     - Cancel
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("up", "move_up", "Up"),
        Binding("h", "prev_section", "Prev section", show=False),
        Binding("l", "next_section", "Next section", show=False),
        Binding("left", "prev_section", "Prev section", show=False),
        Binding("right", "next_section", "Next section", show=False),
        Binding("tab", "next_section", "Next section", show=False),
        Binding("f", "focus_expand", "Expand", show=False),
    ]

    DEFAULT_CSS = """
    ConfigScreen {
        align: center middle;
    }

    ConfigScreen #dialog {
        width: 60;
        height: auto;
        max-height: 40;
        padding: 1 2;
        background: $surface;
        border: round $surface-lighten-1;
    }

    ConfigScreen #title {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        color: $text-muted;
    }

    ConfigScreen .section-title {
        color: $text-disabled;
        margin-top: 1;
    }

    ConfigScreen .section-desc {
        color: $text-disabled;
        margin-bottom: 0;
    }

    ConfigScreen .setting-row {
        width: 100%;
        height: 3;
        margin: 0;
    }

    ConfigScreen .setting-label {
        width: 20;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }

    ConfigScreen Select {
        width: 1fr;
    }

    ConfigScreen OptionList {
        width: 100%;
        height: 6;
        margin-top: 0;
    }

    ConfigScreen .path-row {
        width: 100%;
        height: auto;
        margin: 0;
    }

    ConfigScreen .path-label {
        color: $text-disabled;
        height: 1;
        margin-bottom: 0;
    }

    ConfigScreen #button-row {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    ConfigScreen Button {
        margin: 0 1;
    }

    ConfigScreen .hint {
        text-align: center;
        color: $text-disabled;
        height: 1;
    }

    ConfigScreen SessionTypeDropdown {
        margin-bottom: 1;
    }

    ConfigScreen Collapsible {
        margin-top: 1;
        padding: 0;
    }

    ConfigScreen Collapsible CollapsibleTitle {
        color: $text-disabled;
        padding: 0 1;
    }

    ConfigScreen .openrouter-content {
        padding: 0 1;
    }

    ConfigScreen .openrouter-row {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    ConfigScreen .openrouter-label {
        color: $text-muted;
        height: 1;
    }

    ConfigScreen .openrouter-input {
        width: 100%;
    }
    """

    def __init__(self, config_manager: ConfigManager, profile_manager: ProfileManager | None = None):
        super().__init__()
        self._config_manager = config_manager
        self._profile_manager = profile_manager or ProfileManager()
        self._original_theme = None

    def compose(self) -> ComposeResult:
        current_exit = self._config_manager.config.exit_behavior
        global_dir = self._config_manager.config.features.working_dir
        instance_dir = self._config_manager.portal.features.working_dir
        enabled_types = self._config_manager.config.features.enabled_session_types

        with Vertical(id="dialog"):
            yield Static("settings", id="title")

            # Session types section
            yield SessionTypeDropdown(enabled_types=enabled_types, id="session-types")

            # Exit behavior section
            yield Static("exit behavior", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Static("On quit:", classes="setting-label")
                yield Select(
                    [
                        ("Ask every time", ExitBehavior.ASK.value),
                        ("Kill all sessions", ExitBehavior.KILL_ALL.value),
                        ("Kill dead only", ExitBehavior.KILL_DEAD.value),
                        ("Keep all running", ExitBehavior.KEEP_ALL.value),
                    ],
                    value=current_exit.value,
                    id="exit-behavior",
                )

            # Global working directory
            yield Static("global directory", classes="section-title")
            with Vertical(classes="path-row"):
                yield Static("default for all zen-portal instances", classes="path-label")
                yield PathInput(
                    initial_path=global_dir,
                    placeholder="~/path/to/projects (empty = current directory)",
                    id="global-dir-input",
                )

            # Instance working directory
            yield Static("instance directory", classes="section-title")
            with Vertical(classes="path-row"):
                yield Static("override for this session only", classes="path-label")
                yield PathInput(
                    initial_path=instance_dir,
                    placeholder="(empty = use global)",
                    id="instance-dir-input",
                )

            # y-router proxy settings (collapsible)
            openrouter_proxy = self._config_manager.config.features.openrouter_proxy
            proxy_enabled = openrouter_proxy.enabled if openrouter_proxy else False
            proxy_url = openrouter_proxy.base_url if openrouter_proxy else "http://localhost:8787"
            proxy_key = openrouter_proxy.api_key if openrouter_proxy else ""
            proxy_model = openrouter_proxy.default_model if openrouter_proxy else ""

            with Collapsible(title="y-router proxy", id="openrouter-collapsible", collapsed=True):
                with Vertical(classes="openrouter-content"):
                    yield Checkbox("Route Claude through y-router", proxy_enabled, id="openrouter-enabled")
                    yield Static("docker-compose up -d in y-router dir", classes="openrouter-label")
                    with Vertical(classes="openrouter-row"):
                        yield Static("proxy url", classes="openrouter-label")
                        yield Input(
                            value=proxy_url,
                            placeholder="http://localhost:8787",
                            id="openrouter-url",
                            classes="openrouter-input",
                        )
                    with Vertical(classes="openrouter-row"):
                        yield Static("api key (or set OPENROUTER_API_KEY)", classes="openrouter-label")
                        yield Input(
                            value=proxy_key,
                            placeholder="sk-or-...",
                            password=True,
                            id="openrouter-key",
                            classes="openrouter-input",
                        )
                    with Vertical(classes="openrouter-row"):
                        yield Static("model (optional)", classes="openrouter-label")
                        yield Input(
                            value=proxy_model,
                            placeholder="anthropic/claude-sonnet-4",
                            id="openrouter-model",
                            classes="openrouter-input",
                        )

            # Theme selection
            yield Static("theme", classes="section-title")
            yield OptionList(
                *[Option(display, id=theme_id) for theme_id, display in THEMES],
                id="theme-list",
            )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

            yield Static("h/l sections  j/k nav  f expand  esc cancel", classes="hint")

    def on_mount(self) -> None:
        """Store original theme for cancel."""
        self._original_theme = self.app.theme

        current_theme = self._profile_manager.profile.theme or "textual-dark"
        theme_list = self.query_one("#theme-list", OptionList)
        for i, (theme_id, _) in enumerate(THEMES):
            if theme_id == current_theme:
                theme_list.highlighted = i
                break

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Preview theme when hovering over option."""
        if event.option and event.option.id:
            self.app.theme = event.option.id

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Apply theme when selected."""
        if event.option and event.option.id:
            self.app.theme = event.option.id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self._restore_theme()
            self.dismiss(None)
        elif event.button.id == "save":
            self._save_settings()

    def _save_settings(self) -> None:
        """Save all settings."""
        # Save exit behavior
        select = self.query_one("#exit-behavior", Select)
        behavior = ExitBehavior(select.value)
        self._config_manager.update_exit_behavior(behavior)

        # Save enabled session types
        dropdown = self.query_one("#session-types", SessionTypeDropdown)
        enabled_types = dropdown.get_enabled_types()
        enabled_types_to_save = None if set(enabled_types) == set(ALL_SESSION_TYPES) else enabled_types

        # Save global directory
        global_input = self.query_one("#global-dir-input", PathInput)
        global_path = global_input.get_path()

        # Save y-router proxy settings
        openrouter_enabled = self.query_one("#openrouter-enabled", Checkbox).value
        openrouter_url = self.query_one("#openrouter-url", Input).value.strip()
        openrouter_key = self.query_one("#openrouter-key", Input).value.strip()
        openrouter_model = self.query_one("#openrouter-model", Input).value.strip()

        openrouter_proxy = None
        if openrouter_enabled or openrouter_key or openrouter_model:
            openrouter_proxy = OpenRouterProxySettings(
                enabled=openrouter_enabled,
                base_url=openrouter_url or "http://localhost:8787",
                api_key=openrouter_key,
                default_model=openrouter_model,
            )

        config = self._config_manager.config
        config.features.working_dir = global_path
        config.features.enabled_session_types = enabled_types_to_save
        config.features.openrouter_proxy = openrouter_proxy
        self._config_manager.save_config(config)

        # Save instance directory
        instance_input = self.query_one("#instance-dir-input", PathInput)
        instance_path = instance_input.get_path()
        if instance_path:
            features = FeatureSettings(working_dir=instance_path)
            self._config_manager.update_portal_features(features)
        else:
            portal = self._config_manager.portal
            portal.features.working_dir = None
            self._config_manager.save_portal(portal)

        # Save theme to profile
        theme_list = self.query_one("#theme-list", OptionList)
        if theme_list.highlighted is not None:
            theme_id, _ = THEMES[theme_list.highlighted]
            self._profile_manager.update_theme(theme_id)

        self.app.notify("Settings saved", timeout=2)
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel and restore original theme."""
        self._restore_theme()
        self.dismiss(None)

    def action_move_down(self) -> None:
        """Move selection down in the focused list."""
        try:
            theme_list = self.query_one("#theme-list", OptionList)
            if theme_list.has_focus:
                if theme_list.highlighted is not None and theme_list.highlighted < len(THEMES) - 1:
                    theme_list.highlighted += 1
        except Exception:
            pass

    def action_move_up(self) -> None:
        """Move selection up in the focused list."""
        try:
            theme_list = self.query_one("#theme-list", OptionList)
            if theme_list.has_focus:
                if theme_list.highlighted is not None and theme_list.highlighted > 0:
                    theme_list.highlighted -= 1
        except Exception:
            pass

    def _get_focusables(self) -> list[str]:
        """Get list of focusable widget selectors."""
        return [
            "#session-types",
            "#exit-behavior",
            "#global-dir-input",
            "#instance-dir-input",
            "#openrouter-collapsible",
            "#theme-list",
            "#save",
        ]

    def action_next_section(self) -> None:
        """Move focus to next section (l/right/tab)."""
        focusables = self._get_focusables()
        for i, selector in enumerate(focusables):
            try:
                widget = self.query_one(selector)
                if widget.has_focus:
                    next_idx = (i + 1) % len(focusables)
                    self.query_one(focusables[next_idx]).focus()
                    return
            except Exception:
                continue
        try:
            self.query_one(focusables[0]).focus()
        except Exception:
            pass

    def action_prev_section(self) -> None:
        """Move focus to previous section (h/left)."""
        focusables = self._get_focusables()
        for i, selector in enumerate(focusables):
            try:
                widget = self.query_one(selector)
                if widget.has_focus:
                    prev_idx = (i - 1) % len(focusables)
                    self.query_one(focusables[prev_idx]).focus()
                    return
            except Exception:
                continue
        try:
            self.query_one(focusables[0]).focus()
        except Exception:
            pass

    def action_focus_expand(self) -> None:
        """Expand the session types dropdown if focused."""
        try:
            dropdown = self.query_one("#session-types", SessionTypeDropdown)
            if dropdown.has_focus:
                dropdown.expanded = not dropdown.expanded
        except Exception:
            pass

    def _restore_theme(self) -> None:
        """Restore original theme on cancel."""
        if self._original_theme:
            self.app.theme = self._original_theme
