"""Command palette for searchable command execution.

A modal overlay providing fuzzy search across all available commands.
Inspired by VS Code's command palette (Ctrl+Shift+P).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from .base import ZenModalScreen
from ..services.command_registry import Command, CommandRegistry
from ..services.fuzzy import rank_commands


class CommandItem(Static):
    """A single command entry in the palette list."""

    DEFAULT_CSS = """
    CommandItem {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    CommandItem:hover {
        background: $surface-lighten-1;
    }

    CommandItem.selected {
        background: $surface-lighten-1;
    }

    CommandItem .label {
        width: 1fr;
    }

    CommandItem .keybinding {
        color: $text-disabled;
        text-align: right;
        width: auto;
    }
    """

    def __init__(self, command: Command, **kwargs) -> None:
        super().__init__(**kwargs)
        self.command = command

    def compose(self) -> ComposeResult:
        # Single line with label and keybinding
        kb = self.command.keybinding or ""
        label = self.command.label
        # Pad to align keybindings
        yield Static(f"{label}{'':>{30 - len(label)}}{kb:>4}")


class CommandPalette(ZenModalScreen[str | None]):
    """Searchable command palette modal."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
        Binding("enter", "execute", "Run"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("ctrl+p", "move_up", "Up", show=False),
        Binding("ctrl+n", "move_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    CommandPalette #dialog {
        border: round $primary;
    }

    CommandPalette #palette-input {
        width: 100%;
        margin-bottom: 1;
    }

    CommandPalette #palette-input:focus {
        border: tall $primary;
    }

    CommandPalette #results {
        height: auto;
        max-height: 50vh;
        min-height: 5;
        overflow-y: auto;
    }

    CommandPalette .empty-results {
        color: $text-disabled;
        text-align: center;
        padding: 1;
    }
    """

    selected_index: reactive[int] = reactive(0)

    def __init__(
        self,
        registry: CommandRegistry,
        has_selection: bool = False,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._has_selection = has_selection
        self._commands: list[Command] = []
        self._filtered_commands: list[Command] = []
        self._updating = False  # Guard flag for DOM updates

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-md")

        with Vertical(id="dialog"):
            yield Static("commands", classes="dialog-title")
            yield Input(placeholder="type to search...", id="palette-input")
            yield Vertical(id="results")
            yield Static("↑↓ navigate  enter execute  esc cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        super().on_mount()
        # Get contextual commands
        self._commands = self._registry.get_contextual(self._has_selection)
        self._filtered_commands = self._commands.copy()
        self._update_results()
        # Focus the input
        self.query_one("#palette-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter commands as user types."""
        query = event.value.strip()
        if not query:
            self._filtered_commands = self._commands.copy()
        else:
            # Use fuzzy matching to rank commands
            searchable = [(c.id, c.label) for c in self._commands]
            ranked = rank_commands(query, searchable)
            # Map back to Command objects
            id_to_command = {c.id: c for c in self._commands}
            self._filtered_commands = [
                id_to_command[id_] for id_, _, score in ranked if id_ in id_to_command
            ]
        self._update_results()
        self.selected_index = 0

    def _update_results(self) -> None:
        """Rebuild the results list."""
        self._updating = True
        try:
            results = self.query_one("#results", Vertical)
            results.remove_children()

            if not self._filtered_commands:
                results.mount(Static("no matching commands", classes="empty-results"))
                return

            for i, command in enumerate(self._filtered_commands):
                item = CommandItem(command, id=f"cmd-{i}")
                if i == self.selected_index:
                    item.add_class("selected")
                results.mount(item)
        finally:
            self._updating = False

    def watch_selected_index(self, new_index: int) -> None:
        """Update visual selection."""
        if self._updating:
            return  # Skip during DOM rebuild
        try:
            results = self.query_one("#results", Vertical)
            for i, child in enumerate(results.children):
                if isinstance(child, CommandItem):
                    if i == new_index:
                        child.add_class("selected")
                    else:
                        child.remove_class("selected")
        except Exception:
            pass

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._filtered_commands:
            self.selected_index = min(
                self.selected_index + 1,
                len(self._filtered_commands) - 1
            )

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._filtered_commands:
            self.selected_index = max(self.selected_index - 1, 0)

    def action_execute(self) -> None:
        """Execute selected command and dismiss."""
        if self._filtered_commands and 0 <= self.selected_index < len(self._filtered_commands):
            command = self._filtered_commands[self.selected_index]
            self.dismiss(command.id)
        else:
            self.dismiss(None)

    def on_command_item_click(self, event) -> None:
        """Handle click on command item."""
        # Find which item was clicked
        for i, child in enumerate(self.query_one("#results", Vertical).children):
            if isinstance(child, CommandItem) and child == event.widget:
                self.selected_index = i
                self.action_execute()
                break
