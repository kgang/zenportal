"""SessionInfoView widget for displaying session metadata."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState


class SessionInfoView(Static):
    """Minimalist zen panel showing session metadata.

    Displayed when information mode is active instead of output view.
    """

    session: reactive[Session | None] = reactive(None)

    DEFAULT_CSS = """
    SessionInfoView {
        width: 100%;
        height: 100%;
        border: round $surface-lighten-1;
    }

    SessionInfoView .title {
        height: 1;
        background: $surface;
        color: $text-muted;
        text-align: center;
    }

    SessionInfoView .content {
        height: 1fr;
        padding: 1 2;
    }

    SessionInfoView .empty-message {
        content-align: center middle;
        color: $text-muted;
        height: 1fr;
    }

    SessionInfoView .field {
        height: 1;
        margin-bottom: 0;
    }

    SessionInfoView .field-label {
        color: $text-muted;
    }

    SessionInfoView .field-value {
        color: $text;
    }

    SessionInfoView .section {
        margin-top: 1;
        color: $text-disabled;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("info", classes="title")

        if not self.session:
            yield Static("\n\n\n\n      ·\n\n   select a session", classes="empty-message")
        else:
            yield Static(self._render_info(), classes="content")

    def _render_info(self) -> str:
        """Render session metadata as formatted text."""
        s = self.session
        if not s:
            return ""

        lines = []

        # Identity section
        lines.append(f"[dim]identity[/dim]")
        lines.append(f"  name          {s.display_name}")
        lines.append(f"  id            {s.id[:8]}...")
        if s.session_type.value == "claude" and s.claude_session_id:
            lines.append(f"  claude        {s.claude_session_id[:8]}...")
        lines.append(f"  type          {s.session_type.value}")

        # State section
        lines.append("")
        lines.append(f"[dim]state[/dim]")
        state_display = self._format_state(s.state)
        lines.append(f"  status        {s.status_glyph} {state_display}")
        lines.append(f"  created       {s.created_at.strftime('%H:%M:%S')}")
        lines.append(f"  age           {s.age_display}")
        if s.ended_at:
            lines.append(f"  ended         {s.ended_at.strftime('%H:%M:%S')}")

        # Location section
        lines.append("")
        lines.append(f"[dim]location[/dim]")
        if s.resolved_working_dir:
            path_str = str(s.resolved_working_dir)
            if len(path_str) > 40:
                path_str = "..." + path_str[-37:]
            lines.append(f"  directory     {path_str}")
        if s.worktree_path:
            wt_str = str(s.worktree_path)
            if len(wt_str) > 40:
                wt_str = "..." + wt_str[-37:]
            lines.append(f"  worktree      {wt_str}")
        if s.worktree_branch:
            lines.append(f"  branch        {s.worktree_branch}")

        # Config section (if relevant)
        if s.resolved_model or s.dangerously_skip_permissions:
            lines.append("")
            lines.append(f"[dim]config[/dim]")
            if s.resolved_model:
                lines.append(f"  model         {s.resolved_model.value}")
            if s.dangerously_skip_permissions:
                lines.append(f"  dangerous     yes")

        # Prompt section (if any)
        if s.prompt:
            lines.append("")
            lines.append(f"[dim]prompt[/dim]")
            prompt_preview = s.prompt[:60]
            if len(s.prompt) > 60:
                prompt_preview += "..."
            # Handle multiline
            prompt_preview = prompt_preview.replace("\n", " ")
            lines.append(f"  {prompt_preview}")

        return "\n".join(lines)

    def _format_state(self, state: SessionState) -> str:
        """Format state with description."""
        descriptions = {
            SessionState.GROWING: "active",
            SessionState.BLOOMED: "complete",
            SessionState.WILTED: "failed",
            SessionState.PAUSED: "paused",
            SessionState.KILLED: "killed",
        }
        return descriptions.get(state, str(state.value))

    def watch_session(self, new_session: Session | None) -> None:
        """Update display when session changes."""
        self.refresh(recompose=True)

    def update_session(self, session: Session | None) -> None:
        """Update the displayed session."""
        self.session = session
