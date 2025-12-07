"""ConfigScreen: Settings configuration with keyboard navigation."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Static, Select, OptionList
from textual.widgets.option_list import Option

from ..services.config import ConfigManager, ExitBehavior, FeatureSettings, ALL_SESSION_TYPES
from ..services.profile import ProfileManager
from ..widgets.session_type_dropdown import SessionTypeDropdown
from ..widgets.path_input import PathInput
from ..widgets.zen_ai_dropdown import ZenAIDropdown


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
    /* Component-specific: settings layout */
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
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    ConfigScreen Button {
        margin: 0 1;
    }

    ConfigScreen SessionTypeDropdown {
        margin-bottom: 1;
    }

    ConfigScreen ZenAIDropdown {
        margin-bottom: 1;
    }
    """

    def __init__(self, config_manager: ConfigManager, profile_manager: ProfileManager | None = None):
        super().__init__()
        self._config_manager = config_manager
        self._profile_manager = profile_manager or ProfileManager()
        self._original_theme = None

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-lg")
        current_exit = self._config_manager.config.exit_behavior
        global_dir = self._config_manager.config.defaults.working_dir
        instance_dir = self._config_manager.config.project.working_dir
        enabled_types = self._config_manager.config.defaults.enabled_session_types
        zen_ai_config = self._config_manager.config.defaults.zen_ai

        with Vertical(id="dialog"):
            yield Static("settings", classes="dialog-title")

            # Session types section
            yield SessionTypeDropdown(enabled_types=enabled_types, id="session-types")

            # Zen AI section
            yield ZenAIDropdown(zen_ai_config=zen_ai_config, id="zen-ai")

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

            # Theme selection
            yield Static("theme", classes="section-title")
            yield OptionList(
                *[Option(display, id=theme_id) for theme_id, display in THEMES],
                id="theme-list",
            )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel", classes="flat")

            yield Static("h/l sections  j/k nav  f expand  esc cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        """Store original theme for cancel."""
        self.trap_focus = True
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

        # Save Zen AI settings
        zen_ai_dropdown = self.query_one("#zen-ai", ZenAIDropdown)
        zen_ai_config = zen_ai_dropdown.get_config()

        # Save global directory
        global_input = self.query_one("#global-dir-input", PathInput)
        global_path = global_input.get_path()

        config = self._config_manager.config
        config.defaults.working_dir = global_path
        config.defaults.enabled_session_types = enabled_types_to_save
        config.defaults.zen_ai = zen_ai_config
        self._config_manager.save_config(config)

        # Save instance directory (now as project setting)
        instance_input = self.query_one("#instance-dir-input", PathInput)
        instance_path = instance_input.get_path()
        if instance_path:
            features = FeatureSettings(working_dir=instance_path)
            self._config_manager.update_project_features(features)
        else:
            config.project.working_dir = None
            self._config_manager.save_config(config)

        # Save theme to profile
        theme_list = self.query_one("#theme-list", OptionList)
        if theme_list.highlighted is not None:
            theme_id, _ = THEMES[theme_list.highlighted]
            self._profile_manager.update_theme(theme_id)

        self.post_message(self.app.notification_service.success("settings saved"))
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
            "#zen-ai",
            "#exit-behavior",
            "#global-dir-input",
            "#instance-dir-input",
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
        """Expand the focused dropdown."""
        try:
            dropdown = self.query_one("#session-types", SessionTypeDropdown)
            if dropdown.has_focus:
                dropdown.expanded = not dropdown.expanded
                return
        except Exception:
            pass
        try:
            zen_ai = self.query_one("#zen-ai", ZenAIDropdown)
            if zen_ai.has_focus:
                zen_ai.expanded = not zen_ai.expanded
        except Exception:
            pass

    def _restore_theme(self) -> None:
        """Restore original theme on cancel."""
        if self._original_theme:
            self.app.theme = self._original_theme
