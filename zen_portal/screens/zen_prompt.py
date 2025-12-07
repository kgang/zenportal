"""Zen Prompt - Quick AI query modal.

Provides a minimal modal for asking AI questions without leaving context.
Supports @output, @error, @git, @session context references.
"""

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Input, RichLog
from textual.reactive import reactive
from textual.worker import Worker, WorkerState

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
    """

    # Track response state
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
        self._is_querying = False

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-md")
        with Vertical(id="dialog"):
            yield Static("/", classes="dialog-title")
            yield Input(
                id="prompt-input",
                placeholder="ask anything... @output @error @git @session",
            )
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
        if self._is_querying:
            return

        self._execute_query(prompt)

    def _execute_query(self, prompt: str) -> None:
        """Execute the AI query with context using a worker."""
        self._is_querying = True
        self.has_response = False

        # Get UI elements
        title = self.query_one(".dialog-title", Static)
        response_log = self.query_one("#response", RichLog)
        response_log.clear()

        # Show loading state
        title.update("· · ·")

        # Parse context references (sync, fast)
        refs = parse_context_refs(prompt)

        # Gather context if we have a session
        system_prompt = ""
        if refs and self._session and self._session_manager:
            context = gather_context(refs, self._session, self._session_manager)
            system_prompt = context.to_system_prompt(refs)

        # Clean the prompt (remove @refs)
        clean_prompt = strip_refs_from_prompt(prompt) if refs else prompt

        # Run query in worker thread
        self.run_worker(
            self._do_query(clean_prompt, system_prompt),
            name="zen_ai_query",
            exclusive=True,
        )

    async def _do_query(self, prompt: str, system_prompt: str) -> str:
        """Worker task to execute the query."""
        chunks: list[str] = []
        async for chunk in self._zen_ai.stream_query(prompt, system_prompt):
            chunks.append(chunk)
        return "".join(chunks)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion."""
        if event.worker.name != "zen_ai_query":
            return

        title = self.query_one(".dialog-title", Static)
        response_log = self.query_one("#response", RichLog)

        if event.state == WorkerState.SUCCESS:
            self._is_querying = False
            title.update("/")
            self.has_response = True

            if event.worker.result:
                response_log.write(event.worker.result)
            else:
                response_log.write("[dim]no response[/dim]")

            self.query_one("#response-scroll", VerticalScroll).scroll_end()

        elif event.state == WorkerState.ERROR:
            self._is_querying = False
            title.update("/")
            self.has_response = True
            error = event.worker.error
            response_log.write(f"[red]error: {str(error)[:100]}[/red]")

        elif event.state == WorkerState.CANCELLED:
            self._is_querying = False
            title.update("/")
            self.has_response = True
            response_log.write("[dim]cancelled[/dim]")

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            # Close modal
            self.dismiss(None)
            event.prevent_default()
            event.stop()
