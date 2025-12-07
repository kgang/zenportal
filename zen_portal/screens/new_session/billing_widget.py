"""Billing configuration widget for NewSessionModal."""

import os

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Select, Static

from ...services.config import ConfigManager, ProxySettings
from ...widgets.model_selector import ModelSelector


class BillingMode:
    """Billing mode for Claude sessions."""
    CLAUDE = "claude"  # Use Claude account (default)
    OPENROUTER = "openrouter"  # Pay-per-token via y-router


class BillingWidget(Static):
    """Widget for billing mode selection and proxy configuration."""

    DEFAULT_CSS = """
    BillingWidget {
        height: auto;
        min-height: 0;
    }

    BillingWidget #billing-section {
        margin-top: 0;
        height: auto;
        min-height: 0;
    }

    BillingWidget #proxy-config {
        height: auto;
        min-height: 0;
        margin-top: 1;
    }

    BillingWidget #proxy-config.hidden {
        display: none;
        height: 0;
    }

    BillingWidget .proxy-row {
        width: 100%;
        height: auto;
        min-height: 0;
        margin-bottom: 1;
    }

    BillingWidget .proxy-label {
        color: $text-muted;
        height: 1;
    }

    BillingWidget .proxy-input {
        width: 100%;
    }

    BillingWidget .proxy-status {
        height: 1;
        margin-top: 1;
    }

    BillingWidget .proxy-status-ok {
        color: $success;
    }

    BillingWidget .proxy-status-warning {
        color: $warning;
    }

    BillingWidget .proxy-status-error {
        color: $error;
    }

    BillingWidget .proxy-hint {
        color: $text-disabled;
        height: auto;
    }
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        models_service,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._config = config_manager
        self._models_service = models_service

    def compose(self) -> ComposeResult:
        resolved = self._config.resolve_features()
        proxy = resolved.openrouter_proxy
        proxy_enabled = proxy.enabled if proxy else False
        proxy_key = proxy.api_key if proxy else ""
        proxy_model = proxy.default_model if proxy else ""

        initial_billing = BillingMode.OPENROUTER if proxy_enabled else BillingMode.CLAUDE

        with Vertical(id="billing-section"):
            yield Static("billing", classes="field-label")
            yield Select(
                [
                    ("claude account", BillingMode.CLAUDE),
                    ("openrouter", BillingMode.OPENROUTER),
                ],
                value=initial_billing,
                id="billing-select",
            )

            with Vertical(id="proxy-config"):
                has_env_key = bool(os.environ.get("OPENROUTER_API_KEY"))
                has_config_key = bool(proxy_key)
                has_key = has_env_key or has_config_key

                if has_key:
                    yield Static("ready", id="proxy-status", classes="proxy-status proxy-status-ok")
                    yield Static("", id="proxy-hint", classes="proxy-hint")
                else:
                    yield Static("needs api key", id="proxy-status", classes="proxy-status proxy-status-warning")
                    yield Static("get key from openrouter.ai/keys", id="proxy-hint", classes="proxy-hint")

                with Vertical(classes="proxy-row"):
                    yield Static("api key (or set OPENROUTER_API_KEY env)", classes="proxy-label")
                    yield Input(
                        value=proxy_key,
                        placeholder="sk-or-...",
                        password=True,
                        id="proxy-key-input",
                        classes="proxy-input",
                    )

                with Vertical(classes="proxy-row"):
                    yield Static("model (optional)", classes="proxy-label")
                    yield ModelSelector(
                        models_service=self._models_service,
                        initial_value=proxy_model,
                        placeholder="anthropic/claude-sonnet-4",
                        id="proxy-model-selector",
                    )

    def on_mount(self) -> None:
        """Set initial visibility based on billing mode."""
        try:
            billing_select = self.query_one("#billing-select", Select)
            proxy_config = self.query_one("#proxy-config", Vertical)
            proxy_config.display = (billing_select.value == BillingMode.OPENROUTER)
        except Exception:
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle billing select changes."""
        if event.select.id == "billing-select":
            self._handle_billing_change(event.value)

    def _handle_billing_change(self, value) -> None:
        """Handle billing mode changes."""
        try:
            proxy_config = self.query_one("#proxy-config", Vertical)
            show = (value == BillingMode.OPENROUTER)
            proxy_config.display = show
            if show:
                self._update_proxy_status()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "proxy-key-input":
            self._update_proxy_status()

    def _update_proxy_status(self) -> None:
        """Update proxy status display based on current input."""
        try:
            status_widget = self.query_one("#proxy-status", Static)
            hint_widget = self.query_one("#proxy-hint", Static)

            api_key_input = self.query_one("#proxy-key-input", Input).value.strip()
            has_key = bool(api_key_input or os.environ.get("OPENROUTER_API_KEY"))

            status_widget.remove_class("proxy-status-ok", "proxy-status-warning", "proxy-status-error")

            if has_key:
                status_widget.update("ready")
                status_widget.add_class("proxy-status-ok")
                hint_widget.update("")
            else:
                status_widget.update("needs api key")
                status_widget.add_class("proxy-status-warning")
                hint_widget.update("get key from openrouter.ai/keys")
        except Exception:
            pass

    def get_billing_mode(self) -> str:
        """Get the current billing mode."""
        try:
            billing_select = self.query_one("#billing-select", Select)
            return billing_select.value
        except Exception:
            return BillingMode.CLAUDE

    def is_openrouter(self) -> bool:
        """Check if OpenRouter billing is selected."""
        return self.get_billing_mode() == BillingMode.OPENROUTER

    def get_api_key(self) -> str:
        """Get the API key from input."""
        try:
            return self.query_one("#proxy-key-input", Input).value.strip()
        except Exception:
            return ""

    def get_model(self) -> str:
        """Get the selected model."""
        try:
            model_selector = self.query_one("#proxy-model-selector", ModelSelector)
            return model_selector.get_value().strip()
        except Exception:
            return ""

    def save_settings(self) -> None:
        """Save billing/proxy settings to config."""
        try:
            if self.is_openrouter():
                proxy_settings = ProxySettings(
                    enabled=True,
                    api_key=self.get_api_key(),
                    default_model=self.get_model(),
                )
                config = self._config.config
                config.features.openrouter_proxy = proxy_settings
                self._config.save_config(config)
            else:
                config = self._config.config
                if config.features.openrouter_proxy:
                    config.features.openrouter_proxy.enabled = False
                    self._config.save_config(config)
        except Exception:
            pass  # Non-critical - continue with session creation
