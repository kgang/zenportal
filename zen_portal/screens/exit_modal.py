"""ExitModal: Confirmation dialog on exit with keyboard navigation."""

from dataclasses import dataclass
from enum import Enum
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Checkbox
from textual.reactive import reactive


class ExitChoice(Enum):
    CANCEL = "cancel"
    KILL_ALL = "kill_all"
    KILL_DEAD = "kill_dead"
    KEEP_ALL = "keep_all"


@dataclass
class ExitResult:
    """Result from exit modal."""

    choice: ExitChoice
    remember: bool = False


class ExitModal(ModalScreen[ExitResult | None]):
    """Modal asking what to do with sessions on exit.

    Keyboard:
        j/down  - Move selection down
        k/up    - Move selection up
        enter   - Select highlighted option
        space   - Toggle remember checkbox
        esc     - Cancel
    """

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("up", "move_up", "Up"),
        ("escape", "cancel", "Cancel"),
        ("enter", "select", "Select"),
        ("space", "toggle_remember", "Toggle"),
    ]

    selected_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    ExitModal {
        align: center middle;
    }

    ExitModal #dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $warning;
    }

    ExitModal #title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    ExitModal .status-line {
        color: $text-muted;
        margin-bottom: 0;
    }

    ExitModal .option-btn {
        width: 100%;
        margin: 1 0 0 0;
    }

    ExitModal .option-btn.highlighted {
        border: thick $primary;
    }

    ExitModal #remember-row {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    ExitModal #cancel-row {
        width: 100%;
        height: 3;
        align: center middle;
    }

    ExitModal .hint {
        text-align: center;
        color: $text-disabled;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, active_count: int = 0, dead_count: int = 0):
        super().__init__()
        self._active_count = active_count
        self._dead_count = dead_count
        self._button_ids: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("exit zen portal", id="title")

            if self._active_count > 0:
                yield Static(f"  {self._active_count} active session(s) running", classes="status-line")
            if self._dead_count > 0:
                yield Static(f"  {self._dead_count} finished session(s)", classes="status-line")

            yield Button(
                "Kill all sessions",
                variant="error",
                id="kill-all",
                classes="option-btn",
            )
            self._button_ids.append("kill-all")

            if self._dead_count > 0:
                yield Button(
                    "Kill dead only",
                    variant="warning",
                    id="kill-dead",
                    classes="option-btn",
                )
                self._button_ids.append("kill-dead")

            yield Button(
                "Keep all running",
                variant="success",
                id="keep-all",
                classes="option-btn",
            )
            self._button_ids.append("keep-all")

            yield Button(
                "Cancel",
                variant="default",
                id="cancel",
                classes="option-btn",
            )
            self._button_ids.append("cancel")

            with Horizontal(id="remember-row"):
                yield Checkbox("Remember my choice", id="remember")

            yield Static("j/k nav  enter select  space toggle  esc cancel", classes="hint")

    def on_mount(self) -> None:
        """Highlight the first button."""
        self._update_highlight()

    def watch_selected_index(self, index: int) -> None:
        """Update visual highlight when selection changes."""
        self._update_highlight()

    def _update_highlight(self) -> None:
        """Update which button is highlighted."""
        for i, btn_id in enumerate(self._button_ids):
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                if i == self.selected_index:
                    btn.add_class("highlighted")
                else:
                    btn.remove_class("highlighted")
            except Exception:
                pass

    def action_move_down(self) -> None:
        """Move selection down."""
        if self.selected_index < len(self._button_ids) - 1:
            self.selected_index += 1

    def action_move_up(self) -> None:
        """Move selection up."""
        if self.selected_index > 0:
            self.selected_index -= 1

    def action_select(self) -> None:
        """Select the highlighted option."""
        if not self._button_ids or self.selected_index >= len(self._button_ids):
            return

        btn_id = self._button_ids[self.selected_index]
        self._handle_choice(btn_id)

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)

    def action_toggle_remember(self) -> None:
        """Toggle the remember checkbox."""
        checkbox = self.query_one("#remember", Checkbox)
        checkbox.value = not checkbox.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click."""
        if event.button.id:
            self._handle_choice(event.button.id)

    def _handle_choice(self, btn_id: str) -> None:
        """Handle a choice selection."""
        remember = self.query_one("#remember", Checkbox).value

        if btn_id == "cancel":
            self.dismiss(None)
        elif btn_id == "kill-all":
            self.dismiss(ExitResult(ExitChoice.KILL_ALL, remember))
        elif btn_id == "kill-dead":
            self.dismiss(ExitResult(ExitChoice.KILL_DEAD, remember))
        elif btn_id == "keep-all":
            self.dismiss(ExitResult(ExitChoice.KEEP_ALL, remember))
