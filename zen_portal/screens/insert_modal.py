"""Insert modal - capture keys to send to tmux session."""

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


# Special key mappings: Textual key name -> (tmux key name, display symbol)
SPECIAL_KEYS = {
    "up": ("Up", "↑"),
    "down": ("Down", "↓"),
    "left": ("Left", "←"),
    "right": ("Right", "→"),
    "home": ("Home", "⇱"),
    "end": ("End", "⇲"),
    "pageup": ("PageUp", "PgUp"),
    "pagedown": ("PageDown", "PgDn"),
    "delete": ("DC", "Del"),
    "insert": ("IC", "Ins"),
    "f1": ("F1", "F1"),
    "f2": ("F2", "F2"),
    "f3": ("F3", "F3"),
    "f4": ("F4", "F4"),
    "f5": ("F5", "F5"),
    "f6": ("F6", "F6"),
    "f7": ("F7", "F7"),
    "f8": ("F8", "F8"),
    "f9": ("F9", "F9"),
    "f10": ("F10", "F10"),
    "f11": ("F11", "F11"),
    "f12": ("F12", "F12"),
    # Shift combinations
    "shift+up": ("S-Up", "⇧↑"),
    "shift+down": ("S-Down", "⇧↓"),
    "shift+left": ("S-Left", "⇧←"),
    "shift+right": ("S-Right", "⇧→"),
    "shift+enter": ("S-Enter", "⇧↵"),
    "shift+tab": ("BTab", "⇧⇥"),
    # Ctrl combinations
    "ctrl+c": ("C-c", "^C"),
    "ctrl+d": ("C-d", "^D"),
    "ctrl+z": ("C-z", "^Z"),
    "ctrl+l": ("C-l", "^L"),
    "ctrl+a": ("C-a", "^A"),
    "ctrl+e": ("C-e", "^E"),
    "ctrl+t": ("C-t", "^T"),
    "ctrl+up": ("C-Up", "^↑"),
    "ctrl+down": ("C-Down", "^↓"),
    "ctrl+left": ("C-Left", "^←"),
    "ctrl+right": ("C-Right", "^→"),
    # Alt combinations
    "alt+up": ("M-Up", "⌥↑"),
    "alt+down": ("M-Down", "⌥↓"),
    "alt+left": ("M-Left", "⌥←"),
    "alt+right": ("M-Right", "⌥→"),
}


@dataclass
class KeyItem:
    """A single key or special key in the buffer."""

    # For literal text, this is the character(s)
    # For special keys, this is the tmux key name (e.g., "Up", "S-Enter")
    value: str
    # Display representation
    display: str
    # True if this is a special key (needs send-keys without -l)
    is_special: bool = False


@dataclass
class InsertResult:
    """Result from insert modal."""

    # List of key items to send
    keys: list[KeyItem] = field(default_factory=list)


class InsertModal(ModalScreen[InsertResult | None]):
    """Capture keys to send to a tmux session.

    Keys are captured character-by-character and displayed.
    Press ESC to finish and send, or ESC with no input to cancel.
    Supports special keys like arrows, shift+enter, etc.
    """

    DEFAULT_CSS = """
    /* Component-specific: buffer styling */
    InsertModal #buffer-scroll {
        width: 100%;
        height: 5;
        padding: 0 1;
        background: $surface-darken-1;
        border: none;
    }

    InsertModal #buffer {
        width: 100%;
        height: auto;
        color: $text;
    }
    """

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name
        self._buffer: list[KeyItem] = []

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-md")
        with Vertical(id="dialog"):
            yield Static(f"insert  {self._session_name}", classes="dialog-title")
            with VerticalScroll(id="buffer-scroll"):
                yield Static("", id="buffer")
            yield Static("type keys  esc send", classes="dialog-hint")

    def _get_display_text(self) -> str:
        """Get the display representation of the buffer."""
        if not self._buffer:
            return "(empty)"
        parts = []
        for item in self._buffer:
            if item.value == "\n":
                parts.append("↵\n")
            elif item.is_special:
                parts.append(f"[{item.display}]")
            else:
                parts.append(item.display)
        return "".join(parts)

    def _update_buffer_display(self) -> None:
        """Update the buffer display and auto-scroll to bottom."""
        self.query_one("#buffer", Static).update(self._get_display_text())
        self.query_one("#buffer-scroll", VerticalScroll).scroll_end(animate=False)

    def _add_literal(self, char: str, display: str | None = None) -> None:
        """Add a literal character to the buffer."""
        self._buffer.append(KeyItem(value=char, display=display or char, is_special=False))
        self._update_buffer_display()

    def _add_special(self, tmux_key: str, display: str) -> None:
        """Add a special key to the buffer."""
        self._buffer.append(KeyItem(value=tmux_key, display=display, is_special=True))
        self._update_buffer_display()

    def on_key(self, event) -> None:
        """Capture key presses."""
        key = event.key

        if key == "escape":
            # ESC with content = send, ESC with empty = cancel
            if self._buffer:
                self.dismiss(InsertResult(keys=self._buffer.copy()))
            else:
                self.dismiss(None)
            event.prevent_default()
            event.stop()
            return

        if key == "backspace":
            if self._buffer:
                self._buffer.pop()
                self._update_buffer_display()
            event.prevent_default()
            event.stop()
            return

        # Check for special keys (arrows, function keys, modifiers)
        if key in SPECIAL_KEYS:
            tmux_key, display = SPECIAL_KEYS[key]
            self._add_special(tmux_key, display)
            event.prevent_default()
            event.stop()
            return

        if key == "enter":
            # Enter adds newline to buffer (will be sent as Enter to tmux)
            self._add_special("Enter", "↵")
            event.prevent_default()
            event.stop()
            return

        if key == "tab":
            self._add_special("Tab", "⇥")
            event.prevent_default()
            event.stop()
            return

        if key == "space":
            self._add_literal(" ")
            event.prevent_default()
            event.stop()
            return

        # Single character keys
        if len(key) == 1 and key.isprintable():
            self._add_literal(key)
            event.prevent_default()
            event.stop()
            return

        # Handle character attribute for special keys
        if hasattr(event, "character") and event.character:
            self._add_literal(event.character)
            event.prevent_default()
            event.stop()
