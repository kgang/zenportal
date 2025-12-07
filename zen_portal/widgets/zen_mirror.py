"""Zen Mirror - Context-aware AI companion panel.

An optional sidebar that shows AI's understanding of the current session
and provides a persistent prompt input for deeper interactions.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static, Input, RichLog

from ..models.session import Session


class ZenMirror(Static, can_focus=False):
    """Context-aware AI companion panel.

    Displays session context and provides a persistent prompt input.
    Toggled via `Z` key from MainScreen.
    """

    DEFAULT_CSS = """
    ZenMirror {
        height: 100%;
        width: 100%;
        padding: 1;
    }

    ZenMirror #context-header {
        color: $text-muted;
        margin-bottom: 1;
    }

    ZenMirror #context-display {
        height: auto;
        min-height: 3;
        max-height: 50%;
        color: $text;
        overflow-y: auto;
    }

    ZenMirror #context-display.empty {
        color: $text-disabled;
    }

    ZenMirror #mirror-prompt-container {
        dock: bottom;
        height: auto;
        margin-top: 1;
    }

    ZenMirror #mirror-prompt {
        width: 100%;
    }

    ZenMirror #mirror-prompt.hidden {
        display: none;
    }
    """

    # Session context summary
    context_text: reactive[str] = reactive("")
    prompt_active: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self._current_session: Session | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("zen", id="context-header")
            yield Static("no session selected", id="context-display", classes="empty")
            with Vertical(id="mirror-prompt-container"):
                yield Input(
                    id="mirror-prompt",
                    placeholder="/",
                    classes="hidden",
                )

    def update_context(self, session: Session | None) -> None:
        """Update the context display for the given session.

        Args:
            session: Current session or None if no selection
        """
        self._current_session = session
        display = self.query_one("#context-display", Static)

        if not session:
            display.update("no session selected")
            display.add_class("empty")
            return

        display.remove_class("empty")

        # Build context summary
        lines = [
            f"{session.status_glyph} {session.display_name}",
            f"[dim]{session.session_type.value}  {session.state.value}  {session.age_display}[/dim]",
        ]

        if session.working_dir:
            lines.append(f"[dim]dir[/dim]  {session.working_dir.name}")

        if session.git_branch:
            lines.append(f"[dim]git[/dim]  {session.git_branch}")

        if session.resolved_model:
            lines.append(f"[dim]model[/dim]  {session.resolved_model.value}")

        if session.error_message:
            lines.append(f"[red]error[/red]  {session.error_message[:50]}")

        if session.token_stats:
            total = session.token_stats.get("total", 0)
            if total > 0:
                if total >= 1000:
                    total_str = f"{total / 1000:.1f}k"
                else:
                    total_str = str(total)
                lines.append(f"[dim]tokens[/dim]  {total_str}")

        display.update("\n".join(lines))

    def activate_prompt(self) -> None:
        """Show and focus the prompt input."""
        prompt = self.query_one("#mirror-prompt", Input)
        prompt.remove_class("hidden")
        prompt.can_focus = True
        prompt.focus()
        self.prompt_active = True

    def deactivate_prompt(self) -> None:
        """Hide the prompt input."""
        prompt = self.query_one("#mirror-prompt", Input)
        prompt.blur()
        prompt.can_focus = False
        prompt.add_class("hidden")
        self.prompt_active = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle prompt submission."""
        if event.input.id != "mirror-prompt":
            return

        # For now, just clear the input
        # Future: trigger AI query
        event.input.value = ""
        self.deactivate_prompt()
