"""Zen Prompt - Quick AI query modal.

Provides a minimal modal for asking AI questions without leaving context.
Supports @output, @error, @git, @session context references.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Input, RichLog
from textual.reactive import reactive

from ..services.config import ZenAIConfig, ZenAIProvider
from ..services.zen_ai import ZenAI
from ..services.context_parser import parse_context_refs, gather_context, strip_refs_from_prompt
from ..models.session import Session


class ZenPromptModal(ModalScreen[str | None]):
    """Minimal AI query modal with streaming response.

    Triggered by `/` key. Supports @output, @error, @git, @session references
    for including session context in queries.
    """

    DEFAULT_CSS = """
    /* Component-specific: response area styling */
    ZenPromptModal #response-scroll {
        width: 100%;
        height: auto;
        min-height: 0;
        max-height: 50vh;
        padding: 0 1;
        background: $surface-darken-1;
        border: none;
    }

    ZenPromptModal #response-scroll.hidden {
        display: none;
    }

    ZenPromptModal #response {
        width: 100%;
        height: auto;
        min-height: 3;
        color: $text-muted;
    }

    ZenPromptModal #prompt-input {
        width: 100%;
        margin-top: 1;
    }

    ZenPromptModal #thinking {
        width: 100%;
        text-align: center;
        color: $text-disabled;
        margin: 1 0;
    }

    ZenPromptModal #thinking.hidden {
        display: none;
    }
    """

    # Track query state
    is_querying: reactive[bool] = reactive(False)
    has_response: reactive[bool] = reactive(False)

    def __init__(
        self,
        zen_ai: ZenAI,
        session: Session | None = None,
        session_manager=None,
    ) -> None:
        super().__init__()
        self._zen_ai = zen_ai
        self._session = session
        self._session_manager = session_manager

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-md")
        with Vertical(id="dialog"):
            yield Static("/", classes="dialog-title")
            yield Input(
                id="prompt-input",
                placeholder="ask anything... @output @error @git @session",
            )
            yield Static("thinking...", id="thinking", classes="hidden")
            with VerticalScroll(id="response-scroll", classes="hidden"):
                yield RichLog(id="response", wrap=True, markup=True)
            yield Static(
                "enter ask  esc close  @output @error @git @session",
                classes="dialog-hint",
            )

    def on_mount(self) -> None:
        """Setup modal."""
        self.trap_focus = True
        # Focus the input
        self.query_one("#prompt-input", Input).focus()

    def watch_is_querying(self, querying: bool) -> None:
        """Update UI when query state changes."""
        thinking = self.query_one("#thinking", Static)
        if querying:
            thinking.remove_class("hidden")
        else:
            thinking.add_class("hidden")

    def watch_has_response(self, has_response: bool) -> None:
        """Show response area when we have a response."""
        response_scroll = self.query_one("#response-scroll", VerticalScroll)
        if has_response:
            response_scroll.remove_class("hidden")
        else:
            response_scroll.add_class("hidden")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle prompt submission."""
        if event.input.id != "prompt-input":
            return

        prompt = event.value.strip()
        if not prompt:
            return

        # Don't allow multiple concurrent queries
        if self.is_querying:
            return

        await self._execute_query(prompt)

    async def _execute_query(self, prompt: str) -> None:
        """Execute the AI query with context."""
        self.is_querying = True

        # Parse context references
        refs = parse_context_refs(prompt)

        # Gather context if we have a session
        system_prompt = ""
        if refs and self._session and self._session_manager:
            context = gather_context(refs, self._session, self._session_manager)
            system_prompt = context.to_system_prompt(refs)

        # Clean the prompt (remove @refs)
        clean_prompt = strip_refs_from_prompt(prompt) if refs else prompt

        # Clear previous response
        response_log = self.query_one("#response", RichLog)
        response_log.clear()
        self.has_response = True

        try:
            # Stream the response
            async for chunk in self._zen_ai.stream_query(clean_prompt, system_prompt):
                response_log.write(chunk, scroll_end=True)

        except Exception as e:
            response_log.write(f"[red]error: {str(e)[:100]}[/red]")

        finally:
            self.is_querying = False
            # Scroll to end
            self.query_one("#response-scroll", VerticalScroll).scroll_end()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            # Close modal
            self.dismiss(None)
            event.prevent_default()
            event.stop()
