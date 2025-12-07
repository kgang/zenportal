"""Enhanced proxy status widget with real-time monitoring and quick actions."""

from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, Button, ProgressBar
from textual.widget import Widget

from ..services.proxy_monitor import ProxyMonitor, ProxyHealthStatus, ProxyStatusEvent
from ..services.billing_tracker import BillingTracker
from ..services.config import ProxySettings


class ProxyStatusWidget(Widget):
    """Real-time proxy status display with monitoring and quick actions.

    Features:
    - Live proxy health status with visual indicators
    - Response time and connectivity metrics
    - Billing information and usage stats
    - Quick recovery actions for common issues
    """

    # Reactive properties for real-time updates
    proxy_status: reactive[ProxyHealthStatus] = reactive(ProxyHealthStatus.UNKNOWN)
    response_time: reactive[float] = reactive(0.0)
    account_balance: reactive[float] = reactive(0.0)
    is_monitoring: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    ProxyStatusWidget {
        height: auto;
        border: round $surface-lighten-1;
        padding: 1;
        margin: 1 0;
    }

    ProxyStatusWidget .status-header {
        height: 1;
        margin-bottom: 1;
        text-align: center;
        color: $text-muted;
    }

    ProxyStatusWidget .status-main {
        height: auto;
        margin-bottom: 1;
    }

    ProxyStatusWidget .status-line {
        height: 1;
        margin: 0 1;
    }

    ProxyStatusWidget .metric-row {
        layout: horizontal;
        height: 1;
        align: left middle;
    }

    ProxyStatusWidget .metric-label {
        width: 12;
        color: $text-disabled;
        text-align: right;
    }

    ProxyStatusWidget .metric-value {
        width: 1fr;
        margin-left: 2;
    }

    ProxyStatusWidget .actions {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    ProxyStatusWidget Button {
        margin: 0 1;
        min-width: 12;
    }

    ProxyStatusWidget .status-excellent {
        color: $success;
    }

    ProxyStatusWidget .status-good {
        color: $success-darken-1;
    }

    ProxyStatusWidget .status-degraded {
        color: $warning;
    }

    ProxyStatusWidget .status-warning {
        color: $warning-darken-1;
    }

    ProxyStatusWidget .status-error {
        color: $error;
    }

    ProxyStatusWidget .status-unknown {
        color: $text-disabled;
    }
    """

    def __init__(
        self,
        proxy_monitor: ProxyMonitor | None = None,
        billing_tracker: BillingTracker | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor
        self._billing_tracker = billing_tracker

        # Subscribe to status change events
        if self._proxy_monitor:
            self._proxy_monitor.add_status_callback(self._on_status_change)

    def compose(self) -> ComposeResult:
        """Compose the proxy status widget."""
        with Vertical():
            yield Static("Proxy Status", classes="status-header")

            with Vertical(classes="status-main"):
                yield self._render_status_display()
                yield self._render_metrics_display()

            with Horizontal(classes="actions"):
                yield Button("Refresh", id="proxy-refresh", variant="default")
                yield Button("Configure", id="proxy-configure", variant="primary")
                yield Button("Dashboard", id="proxy-dashboard", variant="outline")

    def _render_status_display(self) -> Widget:
        """Render the main status indicator."""
        status_symbols = {
            ProxyHealthStatus.EXCELLENT: "●",
            ProxyHealthStatus.GOOD: "●",
            ProxyHealthStatus.DEGRADED: "◐",
            ProxyHealthStatus.WARNING: "⚠",
            ProxyHealthStatus.ERROR: "⚠",
            ProxyHealthStatus.UNKNOWN: "○",
        }

        status_colors = {
            ProxyHealthStatus.EXCELLENT: "status-excellent",
            ProxyHealthStatus.GOOD: "status-good",
            ProxyHealthStatus.DEGRADED: "status-degraded",
            ProxyHealthStatus.WARNING: "status-warning",
            ProxyHealthStatus.ERROR: "status-error",
            ProxyHealthStatus.UNKNOWN: "status-unknown",
        }

        symbol = status_symbols.get(self.proxy_status, "?")
        color_class = status_colors.get(self.proxy_status, "status-unknown")
        status_text = self._get_status_text()

        return Static(
            f"[{color_class}]{symbol}[/{color_class}] {status_text}",
            classes="status-line"
        )

    def _render_metrics_display(self) -> Widget:
        """Render proxy metrics information."""
        content = []

        # Response time metric
        if self.response_time > 0:
            response_display = f"{int(self.response_time)}ms"
            if self.response_time <= 200:
                response_display = f"[green]{response_display}[/green]"
            elif self.response_time <= 500:
                response_display = f"[yellow]{response_display}[/yellow]"
            else:
                response_display = f"[red]{response_display}[/red]"

            content.append(f"[dim]response:[/dim] {response_display}")

        # Account balance (if available)
        if self.account_balance > 0:
            balance_display = f"${self.account_balance:.2f}"
            if self.account_balance < 1.0:
                balance_display = f"[red]{balance_display}[/red]"
            elif self.account_balance < 5.0:
                balance_display = f"[yellow]{balance_display}[/yellow]"
            else:
                balance_display = f"[green]{balance_display}[/green]"

            content.append(f"[dim]balance:[/dim] {balance_display}")

        # Monitoring status
        monitor_status = "active" if self.is_monitoring else "paused"
        monitor_color = "green" if self.is_monitoring else "yellow"
        content.append(f"[dim]monitor:[/dim] [{monitor_color}]{monitor_status}[/{monitor_color}]")

        if not content:
            content = ["[dim]no metrics available[/dim]"]

        return Static("\n".join(content), classes="status-line")

    def _get_status_text(self) -> str:
        """Get human-readable status text."""
        status_messages = {
            ProxyHealthStatus.EXCELLENT: "OpenRouter (excellent)",
            ProxyHealthStatus.GOOD: "OpenRouter (good)",
            ProxyHealthStatus.DEGRADED: "OpenRouter (slow)",
            ProxyHealthStatus.WARNING: "OpenRouter (issues)",
            ProxyHealthStatus.ERROR: "OpenRouter (error)",
            ProxyHealthStatus.UNKNOWN: "OpenRouter (checking...)",
        }

        return status_messages.get(self.proxy_status, "OpenRouter (unknown)")

    def _on_status_change(self, event: ProxyStatusEvent) -> None:
        """Handle proxy status change events."""
        self.proxy_status = event.new_status
        self.response_time = event.metrics.response_time_ms
        if event.metrics.account_balance is not None:
            self.account_balance = event.metrics.account_balance

        # Refresh the display
        self.refresh(recompose=True)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "proxy-refresh":
            await self._refresh_status()
        elif event.button.id == "proxy-configure":
            await self._open_configuration()
        elif event.button.id == "proxy-dashboard":
            await self._open_dashboard()

    async def _refresh_status(self) -> None:
        """Manually refresh proxy status."""
        if self._proxy_monitor:
            await self._proxy_monitor.check_status_now()
            # Status will be updated via callback

    async def _open_configuration(self) -> None:
        """Open proxy configuration screen."""
        # This would trigger opening the config screen
        # For now, post a message to the parent
        self.post_message(ProxyConfigurationRequested())

    async def _open_dashboard(self) -> None:
        """Open detailed proxy dashboard."""
        # This would trigger opening the dashboard screen
        # For now, post a message to the parent
        self.post_message(ProxyDashboardRequested())

    async def start_monitoring(self) -> None:
        """Start proxy monitoring."""
        if self._proxy_monitor:
            await self._proxy_monitor.start_monitoring()
            self.is_monitoring = True

    async def stop_monitoring(self) -> None:
        """Stop proxy monitoring."""
        if self._proxy_monitor:
            await self._proxy_monitor.stop_monitoring()
            self.is_monitoring = False

    def watch_proxy_status(self, new_status: ProxyHealthStatus) -> None:
        """React to proxy status changes."""
        self.refresh(recompose=True)

    def watch_response_time(self, new_time: float) -> None:
        """React to response time changes."""
        self.refresh(recompose=True)

    def watch_account_balance(self, new_balance: float) -> None:
        """React to account balance changes."""
        self.refresh(recompose=True)


class ProxyConfigurationRequested:
    """Message sent when user requests proxy configuration."""

    def __init__(self):
        self.timestamp = datetime.now()


class ProxyDashboardRequested:
    """Message sent when user requests proxy dashboard."""

    def __init__(self):
        self.timestamp = datetime.now()


class CompactProxyStatus(Static):
    """Compact proxy status for inclusion in other widgets.

    Shows just the essential status in a single line:
    ● openrouter (12ms) $4.23
    """

    def __init__(
        self,
        proxy_monitor: ProxyMonitor | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor

        # Subscribe to status changes
        if self._proxy_monitor:
            self._proxy_monitor.add_status_callback(self._on_status_change)

    def on_mount(self) -> None:
        """Update display on mount."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the compact status display."""
        if not self._proxy_monitor:
            self.update("proxy: unknown")
            return

        status_display = self._proxy_monitor.get_status_display(include_details=True)
        self.update(status_display)

    def _on_status_change(self, event: ProxyStatusEvent) -> None:
        """Handle proxy status change events."""
        self._update_display()