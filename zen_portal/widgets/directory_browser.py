"""DirectoryBrowser widget for selecting working directories."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static, ListView, ListItem, Label


class PathEntry(ListItem):
    """A single entry in the directory listing."""

    def __init__(self, name: str, path: Path, is_dir: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entry_name = name
        self.entry_path = path
        self.is_dir = is_dir

    def compose(self) -> ComposeResult:
        icon = "/" if self.is_dir else " "
        yield Label(f"{icon} {self.entry_name}")


class DirectoryBrowser(Widget, can_focus=True):
    """Minimalist directory browser with keyboard and mouse support.

    Keyboard:
        j/down  - Move selection down
        k/up    - Move selection up
        enter/l - Enter directory or confirm selection
        h/bksp  - Go to parent directory
        /       - Focus path input for direct editing

    Mouse:
        Click   - Select item
        DblClick- Enter directory
    """

    current_path: reactive[Path] = reactive(Path.home())

    class DirectorySelected(Message):
        """Emitted when a directory is confirmed (user picks it as working dir)."""

        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    class PathChanged(Message):
        """Emitted when navigation changes the current path."""

        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    DEFAULT_CSS = """
    DirectoryBrowser {
        height: auto;
        max-height: 16;
        border: round $surface-lighten-1;
    }

    DirectoryBrowser:focus-within {
        border: round $primary;
    }

    DirectoryBrowser #path-bar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    DirectoryBrowser #path-display {
        width: 1fr;
    }

    DirectoryBrowser #path-input {
        display: none;
        width: 1fr;
        height: 1;
        border: none;
        padding: 0;
        margin: 0;
        background: $surface;
    }

    DirectoryBrowser #path-input.visible {
        display: block;
    }

    DirectoryBrowser #path-display.hidden {
        display: none;
    }

    DirectoryBrowser ListView {
        height: auto;
        max-height: 12;
        background: transparent;
    }

    DirectoryBrowser ListItem {
        padding: 0 1;
        height: 1;
    }

    DirectoryBrowser ListItem > Label {
        width: 100%;
    }

    DirectoryBrowser ListItem.is-dir > Label {
        color: $primary;
    }

    DirectoryBrowser .empty {
        color: $text-disabled;
        text-style: italic;
        padding: 1;
        text-align: center;
    }

    DirectoryBrowser #hint {
        height: 1;
        color: $text-muted;
        text-align: center;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("up", "move_up", "Up"),
        ("l", "enter_item", "Enter"),
        ("enter", "enter_item", "Enter"),
        ("h", "go_parent", "Parent"),
        ("backspace", "go_parent", "Parent"),
        ("slash", "focus_input", "Path"),
    ]

    def __init__(self, initial_path: Path | None = None, show_hint: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self._show_hint = show_hint
        self._entries: list[tuple[str, Path, bool]] = []
        self._editing_path = False
        if initial_path and initial_path.exists() and initial_path.is_dir():
            self._initial_path = initial_path
        else:
            self._initial_path = Path.home()

    def compose(self) -> ComposeResult:
        with Horizontal(id="path-bar"):
            yield Static(str(self._initial_path), id="path-display")
            yield Input(value=str(self._initial_path), id="path-input")
        yield ListView(id="file-list")
        if self._show_hint:
            yield Static("j/k nav  enter select  h parent  / edit path", id="hint")

    def on_mount(self) -> None:
        self.current_path = self._initial_path
        self._load_directory()

    def watch_current_path(self, path: Path) -> None:
        """Update display when path changes."""
        try:
            self.query_one("#path-display", Static).update(str(path))
            self.query_one("#path-input", Input).value = str(path)
        except Exception:
            pass

    def _load_directory(self) -> None:
        """Load and display directory contents."""
        self._entries = []
        list_view = self.query_one("#file-list", ListView)
        list_view.clear()

        try:
            # Parent directory entry (if not at root)
            if self.current_path.parent != self.current_path:
                self._entries.append(("..", self.current_path.parent, True))

            # Directory contents
            items = []
            for item in self.current_path.iterdir():
                if item.name.startswith("."):
                    continue  # Skip hidden
                try:
                    is_dir = item.is_dir()
                    items.append((item.name, item, is_dir))
                except PermissionError:
                    continue

            # Sort: directories first, then alphabetically
            items.sort(key=lambda x: (not x[2], x[0].lower()))
            self._entries.extend(items)

        except PermissionError:
            list_view.mount(Static("permission denied", classes="empty"))
            return
        except OSError as e:
            list_view.mount(Static(f"error: {e}", classes="empty"))
            return

        if not self._entries:
            list_view.mount(Static("empty directory", classes="empty"))
            return

        # Populate list
        for name, path, is_dir in self._entries:
            entry = PathEntry(name, path, is_dir)
            if is_dir:
                entry.add_class("is-dir")
            list_view.mount(entry)

        # Select first item
        if self._entries:
            list_view.index = 0

    def action_move_down(self) -> None:
        """Move selection down."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None and list_view.index < len(self._entries) - 1:
            list_view.index += 1

    def action_move_up(self) -> None:
        """Move selection up."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1

    def action_enter_item(self) -> None:
        """Enter selected directory or confirm file selection."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is None or list_view.index >= len(self._entries):
            return

        name, path, is_dir = self._entries[list_view.index]
        if is_dir:
            self.current_path = path.resolve()
            self._load_directory()
            self.post_message(self.PathChanged(self.current_path))
        else:
            # File selected - confirm current directory
            self.post_message(self.DirectorySelected(self.current_path))

    def action_go_parent(self) -> None:
        """Navigate to parent directory."""
        if self.current_path.parent != self.current_path:
            self.current_path = self.current_path.parent
            self._load_directory()
            self.post_message(self.PathChanged(self.current_path))

    def action_focus_input(self) -> None:
        """Focus the path input for direct editing."""
        self._show_path_input()

    def _show_path_input(self) -> None:
        """Show and focus the path input."""
        self._editing_path = True
        path_display = self.query_one("#path-display", Static)
        path_input = self.query_one("#path-input", Input)
        path_display.add_class("hidden")
        path_input.add_class("visible")
        path_input.focus()

    def _hide_path_input(self) -> None:
        """Hide path input, show static display."""
        self._editing_path = False
        path_display = self.query_one("#path-display", Static)
        path_input = self.query_one("#path-input", Input)
        path_display.remove_class("hidden")
        path_input.remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle path input submission."""
        if event.input.id != "path-input":
            return

        path_str = event.value.strip()
        if path_str.startswith("~"):
            path_str = str(Path.home()) + path_str[1:]

        try:
            new_path = Path(path_str).expanduser().resolve()
            if new_path.is_dir():
                self.current_path = new_path
                self._load_directory()
                self.post_message(self.PathChanged(self.current_path))
            elif new_path.parent.is_dir():
                # If file, go to parent
                self.current_path = new_path.parent
                self._load_directory()
                self.post_message(self.PathChanged(self.current_path))
        except Exception:
            pass

        self._hide_path_input()
        self.query_one("#file-list", ListView).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle escape from input."""
        pass

    def on_blur(self, event) -> None:
        """Hide path input when focus leaves."""
        if self._editing_path:
            self._hide_path_input()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection (double-click or enter)."""
        if not self._entries:
            return

        list_view = self.query_one("#file-list", ListView)
        if list_view.index is None or list_view.index >= len(self._entries):
            return

        name, path, is_dir = self._entries[list_view.index]
        if is_dir:
            self.current_path = path.resolve()
            self._load_directory()
            self.post_message(self.PathChanged(self.current_path))

    def get_selected_path(self) -> Path:
        """Get the current directory path."""
        return self.current_path

    def set_path(self, path: Path) -> None:
        """Set the current path programmatically."""
        if path.exists() and path.is_dir():
            self.current_path = path
            self._load_directory()

    def confirm_selection(self) -> None:
        """Explicitly confirm the current directory as the selection."""
        self.post_message(self.DirectorySelected(self.current_path))
