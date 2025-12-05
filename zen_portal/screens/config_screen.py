"""ConfigScreen: Settings configuration with keyboard navigation."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Static, Select, OptionList, Input
from textual.widgets.option_list import Option

from ..services.config import ConfigManager, ExitBehavior, FeatureSettings
from ..services.profile import ProfileManager


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


class PathInput(Input):
    """Path input with validation and autocomplete hint."""

    DEFAULT_CSS = """
    PathInput {
        width: 100%;
        height: 1;
        border: none;
        background: $surface-darken-1;
        padding: 0 1;
    }

    PathInput:focus {
        border: none;
        background: $surface-darken-2;
    }

    PathInput.-valid {
        color: $success;
    }

    PathInput.-invalid {
        color: $error;
    }
    """

    def __init__(self, initial_path: Path | None = None, placeholder: str = "", **kwargs):
        value = str(initial_path) if initial_path else ""
        super().__init__(value=value, placeholder=placeholder, **kwargs)
        self._validate_path()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate path as user types."""
        self._validate_path()

    def _validate_path(self) -> None:
        """Update styling based on path validity."""
        self.remove_class("-valid", "-invalid")
        path_str = self.value.strip()
        if not path_str:
            return
        try:
            path = Path(path_str).expanduser()
            if path.is_dir():
                self.add_class("-valid")
            else:
                self.add_class("-invalid")
        except Exception:
            self.add_class("-invalid")

    def get_path(self) -> Path | None:
        """Get the path if valid, None otherwise."""
        path_str = self.value.strip()
        if not path_str:
            return None
        try:
            path = Path(path_str).expanduser().resolve()
            if path.is_dir():
                return path
        except Exception:
            pass
        return None


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
        Binding("tab", "next_section", "Next section", show=False),
    ]

    DEFAULT_CSS = """
    ConfigScreen {
        align: center middle;
    }

    ConfigScreen #dialog {
        width: 70;
        height: auto;
        max-height: 45;
        padding: 1 2;
        background: $surface;
        border: round $surface-lighten-1;
    }

    ConfigScreen #title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    ConfigScreen .section-title {
        color: $text-muted;
        margin-top: 1;
        text-style: bold;
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
        width: 24;
        height: 3;
        content-align: left middle;
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
        color: $text-muted;
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

        with Vertical(id="dialog"):
            yield Static("settings", id="title")

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
                yield Button("Cancel", variant="default", id="cancel")

            yield Static("tab sections  j/k nav  enter select  esc cancel", classes="hint")

    def on_mount(self) -> None:
        """Store original theme for cancel."""
        self._original_theme = self.app.theme

        # Highlight current theme in list (from profile)
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
        button_id = event.button.id

        if button_id == "cancel":
            self._restore_theme()
            self.dismiss(None)

        elif button_id == "save":
            self._save_settings()

    def _save_settings(self) -> None:
        """Save all settings."""
        # Save exit behavior
        select = self.query_one("#exit-behavior", Select)
        behavior = ExitBehavior(select.value)
        self._config_manager.update_exit_behavior(behavior)

        # Save global directory from input
        global_input = self.query_one("#global-dir-input", PathInput)
        global_path = global_input.get_path()
        config = self._config_manager.config
        config.features.working_dir = global_path
        self._config_manager.save_config(config)

        # Save instance directory from input
        instance_input = self.query_one("#instance-dir-input", PathInput)
        instance_path = instance_input.get_path()
        if instance_path:
            features = FeatureSettings(working_dir=instance_path)
            self._config_manager.update_portal_features(features)
        else:
            # Clear instance directory
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

    def action_next_section(self) -> None:
        """Move focus to next section."""
        focusables = [
            "#exit-behavior",
            "#global-dir-input",
            "#instance-dir-input",
            "#theme-list",
            "#save",
        ]

        # Find current focus and move to next
        for i, selector in enumerate(focusables):
            try:
                widget = self.query_one(selector)
                if widget.has_focus:
                    next_idx = (i + 1) % len(focusables)
                    self.query_one(focusables[next_idx]).focus()
                    return
            except Exception:
                continue

        # Default to first focusable
        try:
            self.query_one(focusables[0]).focus()
        except Exception:
            pass

    def _restore_theme(self) -> None:
        """Restore original theme on cancel."""
        if self._original_theme:
            self.app.theme = self._original_theme
