"""Status bar widget showing session info."""

from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Minimal status bar showing session time and AAU budget."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    duration = reactive(0)
    aau_spent = reactive(0.0)
    aau_total = reactive(1.0)

    def render(self) -> str:
        """Render the status bar."""
        # Format duration
        if self.duration < 60:
            time_str = f"{self.duration}m"
        else:
            hours = self.duration // 60
            mins = self.duration % 60
            time_str = f"{hours}h{mins}m"

        # Format AAU with simple bar
        remaining = self.aau_total - self.aau_spent
        bar_width = 5
        filled = int((self.aau_spent / self.aau_total) * bar_width) if self.aau_total > 0 else 0
        bar = "●" * filled + "○" * (bar_width - filled)

        return f"  {time_str}  │  AAU [{bar}] {remaining:.2f}  │  ? help"

    def update_from_app(self, info: dict) -> None:
        """Update from app session info."""
        self.duration = info.get("duration_minutes", 0)
        self.aau_spent = info.get("aau_spent", 0.0)
        self.aau_total = info.get("aau_total", 1.0)
