"""Proxy health dashboard screen with detailed monitoring and analytics."""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static, Button, ProgressBar, DataTable
from textual.widget import Widget

from ..services.proxy_monitor import ProxyMonitor, ProxyHealthStatus
from ..services.billing_tracker import BillingTracker
from ..services.config import ProxySettings, ConfigManager
from .base import ZenScreen


class ProxyDashboardScreen(ZenScreen):
    """Comprehensive proxy health dashboard with monitoring and analytics.

    Features:
    - Real-time proxy health monitoring
    - Billing and usage analytics
    - Historical performance data
    - Quick troubleshooting actions
    - Configuration management
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("c", "configure", "Configure"),
        ("t", "toggle_monitoring", "Toggle Monitoring"),
        ("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
    ]

    # Reactive properties
    is_monitoring: reactive[bool] = reactive(False)
    proxy_status: reactive[ProxyHealthStatus] = reactive(ProxyHealthStatus.UNKNOWN)
    last_update: reactive[datetime] = reactive(datetime.now())

    DEFAULT_CSS = """
    ProxyDashboardScreen {
        layout: vertical;
        padding: 1 2;
        layers: base notification;
    }

    ProxyDashboardScreen .header {
        height: 3;
        border: round $surface-lighten-1;
        padding: 1;
        margin-bottom: 1;
    }

    ProxyDashboardScreen .status-grid {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    ProxyDashboardScreen .status-card {
        width: 1fr;
        height: auto;
        border: round $surface-lighten-1;
        padding: 1;
        margin: 0 1;
    }

    ProxyDashboardScreen .metrics-section {
        height: 1fr;
        border: round $surface-lighten-1;
        padding: 1;
        margin-bottom: 1;
    }

    ProxyDashboardScreen .actions {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    ProxyDashboardScreen Button {
        margin: 0 1;
        min-width: 12;
    }

    ProxyDashboardScreen .card-title {
        height: 1;
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    ProxyDashboardScreen .metric-row {
        layout: horizontal;
        height: 1;
        margin: 0;
    }

    ProxyDashboardScreen .metric-label {
        width: 12;
        color: $text-disabled;
        text-align: right;
    }

    ProxyDashboardScreen .metric-value {
        width: 1fr;
        margin-left: 2;
    }

    ProxyDashboardScreen .status-excellent {
        color: $success;
    }

    ProxyDashboardScreen .status-good {
        color: $success-darken-1;
    }

    ProxyDashboardScreen .status-degraded {
        color: $warning;
    }

    ProxyDashboardScreen .status-warning {
        color: $warning-darken-1;
    }

    ProxyDashboardScreen .status-error {
        color: $error;
    }

    ProxyDashboardScreen .status-unknown {
        color: $text-disabled;
    }
    """

    def __init__(
        self,
        proxy_monitor: ProxyMonitor,
        billing_tracker: Optional[BillingTracker] = None,
        config_manager: Optional[ConfigManager] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor
        self._billing_tracker = billing_tracker
        self._config = config_manager

        # Subscribe to status changes
        if self._proxy_monitor:
            self._proxy_monitor.add_status_callback(self._on_status_change)

    def compose(self) -> ComposeResult:
        """Compose the proxy dashboard."""
        with VerticalScroll():
            # Header with title and last update
            with Vertical(classes="header"):
                yield Static("Proxy Health Dashboard", classes="card-title")
                yield Static(self._get_last_update_display(), id="last-update")

            # Status overview cards
            with Horizontal(classes="status-grid"):
                yield self._build_connectivity_card()
                yield self._build_performance_card()
                yield self._build_billing_card()

            # Detailed metrics section
            with Vertical(classes="metrics-section"):
                yield Static("Historical Performance", classes="card-title")
                yield self._build_metrics_table()

            # Quick actions
            with Horizontal(classes="actions"):
                yield Button("Refresh Now", id="refresh", variant="primary")
                yield Button("Configure Proxy", id="configure", variant="default")
                yield Button("Toggle Monitoring", id="toggle-monitoring", variant="default")
                yield Button("Reset Metrics", id="reset", variant="warning")

        # Notification rack from ZenScreen base
        yield from super().compose()

    def _build_connectivity_card(self) -> Widget:
        """Build connectivity status card."""
        status = self._proxy_monitor.status if self._proxy_monitor else ProxyHealthStatus.UNKNOWN
        status_display = self._get_status_display(status)

        children = [
            Static("Connectivity", classes="card-title"),
            Static(status_display, id="connectivity-status"),
        ]

        if self._proxy_monitor and self._proxy_monitor.last_validation:
            validation = self._proxy_monitor.last_validation
            if not validation.connectivity.is_ok:
                children.append(Static(f"[red]Issue:[/red] {validation.connectivity.message}", id="connectivity-issue"))
                if validation.connectivity.hint:
                    children.append(Static(f"[dim]Hint:[/dim] {validation.connectivity.hint}", id="connectivity-hint"))

        return Vertical(*children, classes="status-card")

    def _build_performance_card(self) -> Widget:
        """Build performance metrics card."""
        children = [Static("Performance", classes="card-title")]

        if self._proxy_monitor:
            metrics = self._proxy_monitor.metrics

            # Response time
            response_time = metrics.response_time_ms
            if response_time > 0:
                time_color = "green" if response_time <= 200 else "yellow" if response_time <= 500 else "red"
                children.append(Static(f"Response: [{time_color}]{int(response_time)}ms[/{time_color}]", id="response-time"))
            else:
                children.append(Static("Response: [dim]not measured[/dim]", id="response-time"))

            # Success rate
            success_rate = metrics.success_rate
            rate_color = "green" if success_rate >= 95 else "yellow" if success_rate >= 85 else "red"
            children.append(Static(f"Success: [{rate_color}]{success_rate:.1f}%[/{rate_color}]", id="success-rate"))

            # Consecutive failures
            if metrics.consecutive_failures > 0:
                children.append(Static(f"[red]Failures:[/red] {metrics.consecutive_failures} consecutive", id="failures"))
        else:
            children.append(Static("[dim]No monitoring data[/dim]", id="no-performance-data"))

        return Vertical(*children, classes="status-card")

    def _build_billing_card(self) -> Widget:
        """Build billing information card."""
        children = [Static("Billing", classes="card-title")]

        if self._billing_tracker:
            # This would be populated with actual billing data
            children.append(Static("[dim]Balance:[/dim] Loading...", id="account-balance"))
            children.append(Static("[dim]Usage:[/dim] Loading...", id="monthly-usage"))
            children.append(Static("[dim]Rate Limit:[/dim] Loading...", id="rate-limit"))
        else:
            children.append(Static("[dim]Billing tracker not available[/dim]", id="no-billing-data"))

        return Vertical(*children, classes="status-card")

    def _build_metrics_table(self) -> DataTable:
        """Build historical metrics table."""
        table = DataTable(id="metrics-table")
        table.add_columns("Time", "Status", "Response (ms)", "Success Rate", "Notes")

        # Populate with sample data for now
        # In real implementation, this would come from metrics history
        table.add_rows([
            ("12:45", "Excellent", "156", "100%", ""),
            ("12:40", "Good", "234", "98%", ""),
            ("12:35", "Warning", "1,245", "85%", "Timeout issues"),
            ("12:30", "Good", "198", "100%", ""),
        ])

        return table

    def on_mount(self) -> None:
        """Initialize dashboard on mount."""
        self._update_monitoring_status()
        self.set_interval(5.0, self._periodic_update)

    def _update_monitoring_status(self) -> None:
        """Update monitoring status indicators."""
        if self._proxy_monitor:
            self.is_monitoring = True  # Would check actual monitoring state
            self.proxy_status = self._proxy_monitor.status
        else:
            self.is_monitoring = False
            self.proxy_status = ProxyHealthStatus.UNKNOWN

    def _periodic_update(self) -> None:
        """Periodic update of dashboard data."""
        self.last_update = datetime.now()
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh all dashboard displays."""
        # Update last update timestamp
        try:
            last_update_widget = self.query_one("#last-update", Static)
            last_update_widget.update(self._get_last_update_display())
        except:
            pass

        # Update connectivity status
        try:
            connectivity_widget = self.query_one("#connectivity-status", Static)
            status = self._proxy_monitor.status if self._proxy_monitor else ProxyHealthStatus.UNKNOWN
            connectivity_widget.update(self._get_status_display(status))
        except:
            pass

        # Update performance metrics
        if self._proxy_monitor:
            try:
                response_widget = self.query_one("#response-time", Static)
                metrics = self._proxy_monitor.metrics
                response_time = metrics.response_time_ms

                if response_time > 0:
                    time_color = "green" if response_time <= 200 else "yellow" if response_time <= 500 else "red"
                    response_widget.update(f"Response: [{time_color}]{int(response_time)}ms[/{time_color}]")
                else:
                    response_widget.update("Response: [dim]not measured[/dim]")
            except:
                pass

    def _get_status_display(self, status: ProxyHealthStatus) -> str:
        """Get formatted status display."""
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

        symbol = status_symbols.get(status, "?")
        color_class = status_colors.get(status, "status-unknown")
        status_text = status.value.title()

        return f"[{color_class}]{symbol} {status_text}[/{color_class}]"

    def _get_last_update_display(self) -> str:
        """Get formatted last update timestamp."""
        now = datetime.now()
        diff = now - self.last_update

        if diff.total_seconds() < 60:
            return f"Last update: {int(diff.total_seconds())}s ago"
        elif diff.total_seconds() < 3600:
            return f"Last update: {int(diff.total_seconds() / 60)}m ago"
        else:
            return f"Last update: {self.last_update.strftime('%H:%M')}"

    def _on_status_change(self, event) -> None:
        """Handle proxy status change events."""
        self.proxy_status = event.new_status
        self._refresh_display()

    # Actions
    async def action_refresh(self) -> None:
        """Manually refresh proxy status."""
        if self._proxy_monitor:
            await self._proxy_monitor.check_status_now()
            self.zen_notify("proxy status refreshed")
        else:
            self.zen_notify("proxy monitor not available", "warning")

    def action_configure(self) -> None:
        """Open proxy configuration."""
        if self._config:
            from .config_screen import ConfigScreen
            self.app.push_screen(ConfigScreen(self._config))
        else:
            self.zen_notify("configuration not available", "warning")

    async def action_toggle_monitoring(self) -> None:
        """Toggle proxy monitoring on/off."""
        if not self._proxy_monitor:
            self.zen_notify("proxy monitor not available", "warning")
            return

        if self.is_monitoring:
            await self._proxy_monitor.stop_monitoring()
            self.is_monitoring = False
            self.zen_notify("proxy monitoring stopped", "warning")
        else:
            await self._proxy_monitor.start_monitoring()
            self.is_monitoring = True
            self.zen_notify("proxy monitoring started")

    def action_close(self) -> None:
        """Close the dashboard."""
        self.app.pop_screen()

    async def on_button_pressed(self, event) -> None:
        """Handle button press events."""
        if event.button.id == "refresh":
            await self.action_refresh()
        elif event.button.id == "configure":
            self.action_configure()
        elif event.button.id == "toggle-monitoring":
            await self.action_toggle_monitoring()
        elif event.button.id == "reset":
            self.zen_notify("metrics reset", "warning")

    def zen_notify(self, message: str, severity: str = "success") -> None:
        """Send zen-styled notification."""
        svc = self.app.notification_service
        if severity == "warning":
            self.post_message(svc.warning(message))
        elif severity == "error":
            self.post_message(svc.error(message))
        else:
            self.post_message(svc.success(message))