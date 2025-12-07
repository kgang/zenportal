"""ModelSelector widget for selecting OpenRouter models with autocomplete."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static, ListView, ListItem, Label

from ..services.openrouter_models import OpenRouterModel, OpenRouterModelsService


class ModelOption(ListItem):
    """A single model option in the dropdown."""

    def __init__(self, model: OpenRouterModel, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model = model

    def compose(self) -> ComposeResult:
        # Format: provider/model-name  $0.15/$0.60  128k
        ctx = f"{self.model.context_length // 1000}k" if self.model.context_length else ""
        price = f"${self.model.pricing_prompt:.2f}/${self.model.pricing_completion:.2f}"
        yield Label(f"{self.model.id}  {price}  {ctx}")


class ModelSelector(Widget, can_focus=True):
    """Model selector with autocomplete dropdown.

    Features:
    - Type to filter models by ID or name
    - Fuzzy matching (all chars in order)
    - Keyboard navigation (j/k or arrows)
    - Shows pricing and context length
    - Caches model list for fast lookup

    Keyboard:
        j/down  - Move selection down
        k/up    - Move selection up
        enter   - Select highlighted model
        escape  - Close dropdown / clear selection
        tab     - Select and move to next field

    Messages:
        ModelSelected(model_id): Emitted when a model is selected
    """

    value: reactive[str] = reactive("")
    expanded: reactive[bool] = reactive(False)

    class ModelSelected(Message):
        """Emitted when a model is selected."""

        def __init__(self, model_id: str, model: OpenRouterModel | None = None) -> None:
            self.model_id = model_id
            self.model = model
            super().__init__()

    DEFAULT_CSS = """
    ModelSelector {
        height: auto;
        max-height: 20;
    }

    ModelSelector #model-input {
        width: 100%;
        margin: 0;
    }

    ModelSelector #dropdown {
        display: none;
        height: auto;
        max-height: 12;
        border: round $surface-lighten-1;
        background: $surface;
        margin-top: 0;
        overflow-y: auto;
    }

    ModelSelector #dropdown.visible {
        display: block;
    }

    ModelSelector ListView {
        height: auto;
        max-height: 10;
        background: transparent;
    }

    ModelSelector ListItem {
        padding: 0 1;
        height: 1;
    }

    ModelSelector ListItem > Label {
        width: 100%;
        color: $text-muted;
    }

    ModelSelector ListItem.-highlight > Label,
    ModelSelector ListItem:hover > Label {
        color: $text;
        background: $surface-lighten-1;
    }

    ModelSelector #status {
        height: 1;
        color: $text-disabled;
        padding: 0 1;
    }

    ModelSelector #status.hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("up", "move_up", "Up"),
        ("enter", "select_item", "Select"),
        ("escape", "close_dropdown", "Close"),
    ]

    def __init__(
        self,
        models_service: OpenRouterModelsService | None = None,
        initial_value: str = "",
        placeholder: str = "anthropic/claude-sonnet-4",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._service = models_service or OpenRouterModelsService()
        self._initial_value = initial_value
        self._placeholder = placeholder
        self._filtered_models: list[OpenRouterModel] = []
        self._loading = False

    def compose(self) -> ComposeResult:
        yield Input(
            value=self._initial_value,
            placeholder=self._placeholder,
            id="model-input",
        )
        with Vertical(id="dropdown"):
            yield ListView(id="model-list")
        yield Static("", id="status", classes="hidden")

    def on_mount(self) -> None:
        """Load models on mount."""
        self.value = self._initial_value
        # Start loading models in background
        self._start_model_fetch()

    def _start_model_fetch(self) -> None:
        """Fetch models (non-blocking initial load)."""
        self._loading = True
        self._update_status("loading models...")

        # Use call_later to avoid blocking UI
        self.call_later(self._fetch_models)

    def _fetch_models(self) -> None:
        """Actually fetch models (called via call_later)."""
        try:
            self._service.get_models()
            self._loading = False
            self._update_status("")
            # If there's already input, filter
            if self.value:
                self._filter_models(self.value)
        except Exception as e:
            self._loading = False
            self._update_status(f"error: {e}")

    def _update_status(self, text: str) -> None:
        """Update status text."""
        try:
            status = self.query_one("#status", Static)
            if text:
                status.update(text)
                status.remove_class("hidden")
            else:
                status.add_class("hidden")
        except Exception:
            pass

    def _filter_models(self, query: str) -> None:
        """Filter models based on query."""
        self._filtered_models = self._service.search_models(query, limit=15)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Rebuild the dropdown list."""
        try:
            list_view = self.query_one("#model-list", ListView)
            list_view.clear()

            for model in self._filtered_models:
                list_view.mount(ModelOption(model))

            if self._filtered_models:
                list_view.index = 0
        except Exception:
            pass

    def _show_dropdown(self) -> None:
        """Show the dropdown."""
        self.expanded = True
        dropdown = self.query_one("#dropdown", Vertical)
        dropdown.add_class("visible")

    def _hide_dropdown(self) -> None:
        """Hide the dropdown."""
        self.expanded = False
        dropdown = self.query_one("#dropdown", Vertical)
        dropdown.remove_class("visible")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes - filter models."""
        if event.input.id != "model-input":
            return

        self.value = event.value
        if event.value:
            self._filter_models(event.value)
            self._show_dropdown()
        else:
            self._filtered_models = []
            self._rebuild_list()
            self._hide_dropdown()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter on input."""
        if event.input.id != "model-input":
            return

        # If dropdown is open and has selection, use that
        if self.expanded and self._filtered_models:
            self._select_current()
        else:
            # Just use the raw value
            self._emit_selection(event.value, None)

    def on_focus(self, event) -> None:
        """Focus the input when widget receives focus."""
        try:
            self.query_one("#model-input", Input).focus()
        except Exception:
            pass

    def action_move_down(self) -> None:
        """Move selection down."""
        if not self.expanded:
            if self.value:
                self._show_dropdown()
            return

        list_view = self.query_one("#model-list", ListView)
        if list_view.index is not None and list_view.index < len(self._filtered_models) - 1:
            list_view.index += 1

    def action_move_up(self) -> None:
        """Move selection up."""
        if not self.expanded:
            return

        list_view = self.query_one("#model-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1

    def action_select_item(self) -> None:
        """Select the current item."""
        if self.expanded and self._filtered_models:
            self._select_current()
        else:
            # Just emit current value
            self._emit_selection(self.value, None)

    def action_close_dropdown(self) -> None:
        """Close dropdown or clear value."""
        if self.expanded:
            self._hide_dropdown()
        else:
            # Clear value
            self.value = ""
            self.query_one("#model-input", Input).value = ""
            self._emit_selection("", None)

    def _select_current(self) -> None:
        """Select the currently highlighted model."""
        list_view = self.query_one("#model-list", ListView)
        if list_view.index is None or list_view.index >= len(self._filtered_models):
            return

        model = self._filtered_models[list_view.index]
        self.value = model.id
        self.query_one("#model-input", Input).value = model.id
        self._hide_dropdown()
        self._emit_selection(model.id, model)

    def _emit_selection(self, model_id: str, model: OpenRouterModel | None) -> None:
        """Emit selection message."""
        self.post_message(self.ModelSelected(model_id, model))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item click."""
        self._select_current()

    def on_key(self, event) -> None:
        """Handle key events when input has focus."""
        # Let j/k work in dropdown even when input focused
        input_widget = self.query_one("#model-input", Input)
        if input_widget.has_focus and self.expanded:
            if event.key in ("j", "down"):
                event.prevent_default()
                event.stop()
                self.action_move_down()
            elif event.key in ("k", "up"):
                event.prevent_default()
                event.stop()
                self.action_move_up()

    def set_value(self, value: str) -> None:
        """Set value programmatically."""
        self.value = value
        try:
            self.query_one("#model-input", Input).value = value
        except Exception:
            pass

    def get_value(self) -> str:
        """Get current value."""
        return self.value
