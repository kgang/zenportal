"""ZenAIDropdown: Collapsible dropdown for Zen AI settings."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Checkbox, Select, Static

from ..services.config import ZenAIConfig, ZenAIModel, ZenAIProvider


class ZenAIDropdown(Static):
    """Collapsible dropdown for Zen AI configuration."""

    expanded: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    ZenAIDropdown {
        width: 100%;
        height: auto;
    }

    ZenAIDropdown .dropdown-header {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }

    ZenAIDropdown .dropdown-header:focus {
        background: $surface-lighten-1;
    }

    ZenAIDropdown .dropdown-header:hover {
        background: $surface-lighten-1;
    }

    ZenAIDropdown .dropdown-content {
        width: 100%;
        height: auto;
        padding: 0 2;
        background: $surface-darken-1;
        display: none;
    }

    ZenAIDropdown .dropdown-content.expanded {
        display: block;
    }

    ZenAIDropdown .dropdown-content Checkbox {
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    ZenAIDropdown .dropdown-content Checkbox:focus {
        background: $surface-lighten-1;
    }

    ZenAIDropdown .setting-row {
        width: 100%;
        height: 3;
        margin: 0;
    }

    ZenAIDropdown .setting-label {
        width: 10;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }

    ZenAIDropdown Select {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("f", "toggle_expand", "Expand", show=False),
        Binding("enter", "toggle_expand", "Expand", show=False),
        Binding("space", "toggle_expand", "Expand", show=False),
    ]

    def __init__(self, zen_ai_config: ZenAIConfig | None = None, **kwargs):
        super().__init__(**kwargs)
        self._config = zen_ai_config or ZenAIConfig()
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield Static(self._get_header_text(), id="zen-ai-header", classes="dropdown-header")
        with Vertical(id="zen-ai-content", classes="dropdown-content"):
            yield Checkbox("enabled", self._config.enabled, id="zen-ai-enabled")
            with Horizontal(classes="setting-row"):
                yield Static("model", classes="setting-label")
                yield Select(
                    [
                        ("haiku (fast)", ZenAIModel.HAIKU.value),
                        ("sonnet (balanced)", ZenAIModel.SONNET.value),
                        ("opus (deep)", ZenAIModel.OPUS.value),
                    ],
                    value=self._config.model.value,
                    id="zen-ai-model",
                )
            with Horizontal(classes="setting-row"):
                yield Static("provider", classes="setting-label")
                yield Select(
                    [
                        ("claude cli", ZenAIProvider.CLAUDE.value),
                        ("openrouter", ZenAIProvider.OPENROUTER.value),
                    ],
                    value=self._config.provider.value,
                    id="zen-ai-provider",
                )

    def _get_header_text(self) -> str:
        """Generate header text showing current config."""
        status = "on" if self._config.enabled else "off"
        model = self._config.model.value
        provider = self._config.provider.value
        arrow = "▼" if self.expanded else "▶"
        return f"{arrow} zen ai: {status} · {model} · {provider}"

    def watch_expanded(self, expanded: bool) -> None:
        """Update visibility when expanded changes."""
        try:
            content = self.query_one("#zen-ai-content")
            if expanded:
                content.add_class("expanded")
                cb = self.query_one("#zen-ai-enabled", Checkbox)
                cb.focus()
            else:
                content.remove_class("expanded")
            self._update_header()
        except Exception:
            pass

    def _update_header(self) -> None:
        """Update header text based on current selections."""
        try:
            self._config = self.get_config()
            header = self.query_one("#zen-ai-header", Static)
            header.update(self._get_header_text())
        except Exception:
            pass

    def action_toggle_expand(self) -> None:
        """Toggle dropdown expansion."""
        self.expanded = not self.expanded

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Update header when enabled state changes."""
        self._update_header()
        event.stop()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Update header when model/provider changes."""
        self._update_header()
        event.stop()

    def get_config(self) -> ZenAIConfig:
        """Get current Zen AI configuration from UI state."""
        try:
            enabled_cb = self.query_one("#zen-ai-enabled", Checkbox)
            model_select = self.query_one("#zen-ai-model", Select)
            provider_select = self.query_one("#zen-ai-provider", Select)

            model = ZenAIModel.HAIKU
            if model_select.value:
                try:
                    model = ZenAIModel(model_select.value)
                except ValueError:
                    pass

            provider = ZenAIProvider.CLAUDE
            if provider_select.value:
                try:
                    provider = ZenAIProvider(provider_select.value)
                except ValueError:
                    pass

            return ZenAIConfig(
                enabled=enabled_cb.value,
                model=model,
                provider=provider,
            )
        except Exception:
            return self._config

    def on_click(self, event) -> None:
        """Toggle dropdown on header click."""
        try:
            if not self.expanded:
                self.expanded = True
                event.stop()
            elif event.y <= 1:
                self.expanded = False
                event.stop()
        except Exception:
            pass

    def on_focus(self) -> None:
        """Handle focus on the dropdown."""
        pass

    def on_key(self, event) -> None:
        """Handle navigation within dropdown."""
        if not self.expanded:
            return

        if event.key in ("h", "escape"):
            self.expanded = False
            self.focus()
            event.stop()
            return

        # Navigation between elements when expanded
        focusable_ids = ["#zen-ai-enabled", "#zen-ai-model", "#zen-ai-provider"]
        if event.key in ("j", "k", "down", "up"):
            focused_idx = None
            for i, selector in enumerate(focusable_ids):
                try:
                    widget = self.query_one(selector)
                    if widget.has_focus:
                        focused_idx = i
                        break
                except Exception:
                    pass

            if focused_idx is not None:
                if event.key in ("j", "down"):
                    next_idx = (focused_idx + 1) % len(focusable_ids)
                else:
                    next_idx = (focused_idx - 1) % len(focusable_ids)
                try:
                    self.query_one(focusable_ids[next_idx]).focus()
                except Exception:
                    pass
                event.stop()
