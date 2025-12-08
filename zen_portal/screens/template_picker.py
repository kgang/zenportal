"""Template picker modal for quick session creation from templates.

Provides a searchable list of saved templates with actions
for creating sessions, editing, and deleting templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from .base import ZenModalScreen

if TYPE_CHECKING:
    from ..models.template import SessionTemplate
    from ..services.template_manager import TemplateManager


class TemplateAction(Enum):
    """Action to take with selected template."""

    CREATE = "create"  # Create session from template
    EDIT = "edit"      # Open editor to modify template
    DELETE = "delete"  # Delete the template


@dataclass
class TemplatePickerResult:
    """Result from template picker."""

    action: TemplateAction
    template: SessionTemplate


class TemplateItem(Static):
    """A single template entry in the picker list."""

    DEFAULT_CSS = """
    TemplateItem {
        width: 100%;
        height: 2;
        padding: 0 1;
    }

    TemplateItem:hover {
        background: $surface-lighten-1;
    }

    TemplateItem.selected {
        background: $surface-lighten-1;
    }

    TemplateItem .template-name {
        width: 100%;
    }

    TemplateItem .template-summary {
        color: $text-disabled;
        width: 100%;
    }
    """

    def __init__(self, template: SessionTemplate, **kwargs) -> None:
        super().__init__(**kwargs)
        self.template = template

    def compose(self) -> ComposeResult:
        yield Static(self.template.name, classes="template-name")
        yield Static(self.template.summary, classes="template-summary")


class TemplatePicker(ZenModalScreen[TemplatePickerResult | None]):
    """Modal for selecting a template to create a session from."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
        Binding("enter", "select_template", "Create"),
        Binding("e", "edit_template", "Edit"),
        Binding("d", "delete_template", "Delete"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
    ]

    DEFAULT_CSS = """
    TemplatePicker #dialog {
        border: round $primary;
    }

    TemplatePicker #search-input {
        width: 100%;
        margin-bottom: 1;
    }

    TemplatePicker #template-list {
        height: auto;
        max-height: 50vh;
        min-height: 5;
        overflow-y: auto;
    }

    TemplatePicker #empty-list {
        color: $text-disabled;
        text-align: center;
        padding: 2;
    }
    """

    selected_index: reactive[int] = reactive(0)

    def __init__(self, manager: TemplateManager) -> None:
        super().__init__()
        self._manager = manager
        self._templates: list[SessionTemplate] = []
        self._filtered: list[SessionTemplate] = []

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-md")

        with Vertical(id="dialog"):
            yield Static("templates", classes="dialog-title")
            yield Input(placeholder="search templates...", id="search-input")
            yield Vertical(id="template-list")
            yield Static("enter create · e edit · d delete · esc cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self._templates = self._manager.list()
        self._filtered = self._templates.copy()
        self._update_list()
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter templates as user types."""
        query = event.value.strip()
        self._filtered = self._manager.search(query)
        self.selected_index = 0
        self._update_list()

    def _update_list(self) -> None:
        """Rebuild the template list display."""
        list_container = self.query_one("#template-list", Vertical)
        list_container.remove_children()

        if not self._filtered:
            list_container.mount(Static("no templates found", id="empty-list"))
            return

        for i, template in enumerate(self._filtered):
            item = TemplateItem(template, id=f"tpl-{i}")
            if i == self.selected_index:
                item.add_class("selected")
            list_container.mount(item)

    def watch_selected_index(self, new_index: int) -> None:
        """Update visual selection."""
        try:
            list_container = self.query_one("#template-list", Vertical)
            for i, child in enumerate(list_container.children):
                if isinstance(child, TemplateItem):
                    if i == new_index:
                        child.add_class("selected")
                    else:
                        child.remove_class("selected")
        except Exception:
            pass

    def action_move_down(self) -> None:
        if self._filtered:
            self.selected_index = min(
                self.selected_index + 1,
                len(self._filtered) - 1
            )

    def action_move_up(self) -> None:
        if self._filtered:
            self.selected_index = max(self.selected_index - 1, 0)

    def _get_selected_template(self) -> SessionTemplate | None:
        """Get currently selected template."""
        if self._filtered and 0 <= self.selected_index < len(self._filtered):
            return self._filtered[self.selected_index]
        return None

    def action_select_template(self) -> None:
        """Create session from selected template."""
        template = self._get_selected_template()
        if template:
            self.dismiss(TemplatePickerResult(TemplateAction.CREATE, template))
        else:
            self.dismiss(None)

    def action_edit_template(self) -> None:
        """Edit selected template."""
        template = self._get_selected_template()
        if template:
            self.dismiss(TemplatePickerResult(TemplateAction.EDIT, template))

    def action_delete_template(self) -> None:
        """Delete selected template."""
        template = self._get_selected_template()
        if template:
            self.dismiss(TemplatePickerResult(TemplateAction.DELETE, template))
