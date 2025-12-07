"""ZenAIDropdown: Collapsible dropdown for Zen AI settings."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Checkbox, Select

from ..services.config import ZenAIConfig, ZenAIModel, ZenAIProvider
from .zen_dropdown import ZenDropdown


class ZenAIDropdown(ZenDropdown):
    """Collapsible dropdown for Zen AI configuration.

    Allows users to configure:
    - Whether Zen AI is enabled
    - Which model to use (haiku/sonnet/opus)
    - Which provider to use (claude cli/openrouter)
    """

    # Override IDs for this specific dropdown
    HEADER_ID = "zen-ai-header"
    CONTENT_ID = "zen-ai-content"

    def __init__(self, zen_ai_config: ZenAIConfig | None = None, **kwargs):
        super().__init__(**kwargs)
        self._config = zen_ai_config or ZenAIConfig()

    def _get_header_text(self) -> str:
        """Generate header text showing current config."""
        status = "on" if self._config.enabled else "off"
        model = self._config.model.value
        provider = self._config.provider.value
        return f"{self._get_expand_arrow()} zen ai: {status} · {model} · {provider}"

    def _compose_content(self) -> ComposeResult:
        """Compose Zen AI configuration widgets."""
        yield Checkbox("enabled", self._config.enabled, id="zen-ai-enabled")
        with Horizontal(classes="setting-row"):
            yield Select(
                [
                    ("haiku (fast)", ZenAIModel.HAIKU.value),
                    ("sonnet (balanced)", ZenAIModel.SONNET.value),
                    ("opus (deep)", ZenAIModel.OPUS.value),
                ],
                value=self._config.model.value,
                id="zen-ai-model",
                prompt="model",
            )
        with Horizontal(classes="setting-row"):
            yield Select(
                [
                    ("claude cli", ZenAIProvider.CLAUDE.value),
                    ("openrouter", ZenAIProvider.OPENROUTER.value),
                ],
                value=self._config.provider.value,
                id="zen-ai-provider",
                prompt="provider",
            )

    def _get_focusable_widgets(self) -> list[Widget]:
        """Get focusable widgets in order for navigation."""
        widgets = []
        for widget_id in ["#zen-ai-enabled", "#zen-ai-model", "#zen-ai-provider"]:
            try:
                widgets.append(self.query_one(widget_id))
            except Exception:
                pass
        return widgets

    def _update_header(self) -> None:
        """Update header text based on current selections."""
        try:
            self._config = self.get_config()
        except Exception:
            pass
        super()._update_header()

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
