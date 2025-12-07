"""SessionInfoView widget for displaying session metadata."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState
from ..services.proxy_monitor import ProxyMonitor


class SessionInfoView(Static, can_focus=False):
    """Minimalist zen panel showing session metadata.

    Displayed when information mode is active instead of output view.
    This widget is intentionally non-focusable - all interactions
    are handled by MainScreen keybindings.
    """

    session: reactive[Session | None] = reactive(None)

    def __init__(self, proxy_monitor: ProxyMonitor | None = None, **kwargs):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor

    DEFAULT_CSS = """
    SessionInfoView {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0 1;
    }

    SessionInfoView .title {
        height: 1;
        color: $text-disabled;
        text-align: left;
        margin-bottom: 1;
    }

    SessionInfoView .content {
        height: 1fr;
        padding: 0;
    }

    SessionInfoView .empty-message {
        content-align: center middle;
        color: $text-disabled;
        height: 1fr;
    }

    """

    def compose(self) -> ComposeResult:
        if not self.session:
            yield Static("\n\n\n\n      ·\n\n    select a session", classes="empty-message")
            return

        yield Static("info", classes="title")
        yield Static(self._render_info(), classes="content")

    def _render_info(self) -> str:
        """Render session metadata as minimal formatted text."""
        s = self.session
        if not s:
            return ""

        lines = []

        # Single line: name, state, time
        state_display = self._format_state(s.state)
        lines.append(f"{s.status_glyph} {s.display_name}  {state_display}  {s.age_display}")
        lines.append("")

        # Session identifiers section
        lines.append("[dim]identifiers[/dim]")
        if s.tmux_name:
            lines.append(f"  tmux     {s.tmux_name}")
        lines.append(f"  zen id   {s.id[:8]}")
        if s.claude_session_id:
            lines.append(f"  claude   {s.claude_session_id[:8]}")
        lines.append("")

        # Session type and provider
        lines.append("[dim]type[/dim]")
        if s.session_type.value == "ai":
            lines.append(f"  provider  {s.provider}")
            if s.resolved_model:
                lines.append(f"  model     {s.resolved_model.value}")
        else:
            lines.append(f"  {s.session_type.value}")
        lines.append("")

        # Directory
        working_path = s.worktree_path or s.resolved_working_dir
        if working_path:
            lines.append("[dim]directory[/dim]")
            path_str = str(working_path)
            # Show just the last 2 path components for brevity
            parts = path_str.split("/")
            if len(parts) > 2:
                path_str = ".../" + "/".join(parts[-2:])
            lines.append(f"  {path_str}")
            if s.worktree_branch:
                lines.append(f"  branch  {s.worktree_branch}")
            lines.append("")

        # Token stats if available
        if s.token_stats:
            lines.append("[dim]tokens[/dim]")
            lines.append(f"  input   {s.token_stats.input_tokens:,}")
            lines.append(f"  output  {s.token_stats.output_tokens:,}")
            lines.append(f"  total   {s.token_stats.total_tokens:,}")
            # Cache efficiency - percentage of context served from cache
            if s.token_stats.cache_read_tokens > 0:
                total_context = s.token_stats.input_tokens + s.token_stats.cache_read_tokens
                cache_pct = int(100 * s.token_stats.cache_read_tokens / max(total_context, 1))
                lines.append(f"  cache   {cache_pct}%")
            if s.message_count:
                lines.append(f"  turns   {s.message_count}")
            # Sparkline for token usage pattern
            if s.token_history and len(s.token_history) > 1:
                sparkline = self._render_sparkline(s.token_history)
                lines.append(f"  [dim]{sparkline}[/dim]")
            # Estimated cost for proxy sessions
            if s.uses_proxy:
                model = s.resolved_model.value if s.resolved_model else ""
                cost = s.token_stats.estimate_cost(model)
                lines.append(f"  ~${cost:.3f}")
            lines.append("")

        # Error message for failed sessions
        if s.error_message:
            lines.append(f"[red]error[/red]  {s.error_message}")
            lines.append("")

        # Timestamps
        lines.append("[dim]created[/dim]")
        lines.append(f"  {s.created_at.strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)


    def _render_proxy_status(self, s: Session) -> str:
        """Render enhanced proxy status for the session.

        Returns:
            Formatted proxy status line or empty string if not applicable
        """
        return ""

    def _format_state(self, state: SessionState) -> str:
        """Format state with description."""
        descriptions = {
            SessionState.RUNNING: "active",
            SessionState.COMPLETED: "complete",
            SessionState.FAILED: "failed",
            SessionState.PAUSED: "paused",
            SessionState.KILLED: "killed",
        }
        return descriptions.get(state, str(state.value))

    def _render_sparkline(self, history: list[int], width: int = 16) -> str:
        """Render token history as a minimal sparkline.

        Uses Unicode block characters to show token usage pattern.
        """
        if not history:
            return ""

        # Sample history to fit width
        if len(history) > width:
            step = len(history) / width
            sampled = [history[int(i * step)] for i in range(width)]
        else:
            sampled = history

        # Normalize to 0-7 range for block characters
        min_val = min(sampled)
        max_val = max(sampled)
        if max_val == min_val:
            return "▄" * len(sampled)  # Flat line

        blocks = "▁▂▃▄▅▆▇█"
        sparkline = ""
        for val in sampled:
            idx = int(7 * (val - min_val) / (max_val - min_val))
            sparkline += blocks[idx]

        return sparkline

    def watch_session(self, new_session: Session | None) -> None:
        """Update display when session changes."""
        self.refresh(recompose=True)

    def update_session(self, session: Session | None) -> None:
        """Update the displayed session."""
        self.session = session
