"""Zen-styled command palette provider for zen-portal."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from textual.command import Provider, Hit, DiscoveryHit

if TYPE_CHECKING:
    from ..screens.main import MainScreen


class ZenCommandProvider(Provider):
    """Context-aware command provider with zen minimalism.

    Provides fuzzy-searchable commands that adapt based on:
    - Current screen (MainScreen vs modals)
    - Selected session state (running, completed, etc.)
    - Session properties (has worktree, etc.)
    """

    @property
    def _main_screen(self) -> MainScreen | None:
        """Get MainScreen if it's the active screen."""
        from ..screens.main import MainScreen

        screen = self.app.screen
        if isinstance(screen, MainScreen):
            return screen
        return None

    async def discover(self) -> DiscoveryHit:
        """Provide default commands shown when palette opens.

        Shows essential, always-available commands in zen style.
        """
        yield DiscoveryHit(
            "new session",
            partial(self._run_action, "new_session"),
            help="create a new session",
        )
        yield DiscoveryHit(
            "ask ai",
            partial(self._run_action, "zen_prompt"),
            help="open zen ai prompt",
        )
        yield DiscoveryHit(
            "config",
            partial(self._run_action, "config"),
            help="open settings",
        )
        yield DiscoveryHit(
            "help",
            partial(self._run_action, "show_help"),
            help="show keybindings",
        )

    async def search(self, query: str) -> Hit:
        """Search for commands matching query.

        Commands are context-aware:
        - Static commands always available
        - Session commands based on selected session state
        """
        matcher = self.matcher(query)

        # Static commands - always available
        static_commands = [
            ("new session", "new_session", "create new session"),
            ("attach session", "attach_existing", "attach external tmux"),
            ("config", "config", "open settings"),
            ("help", "show_help", "show keybindings"),
            ("toggle grab mode", "toggle_grab", "reorder sessions"),
            ("toggle info", "toggle_info", "toggle info panel"),
            ("toggle streaming", "toggle_streaming", "toggle output streaming"),
            ("refresh", "refresh_output", "refresh output"),
            ("ask ai", "zen_prompt", "open zen ai prompt"),
            ("quit", "quit", "exit application"),
        ]

        for cmd_text, action, help_text in static_commands:
            score = matcher.match(cmd_text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(cmd_text),
                    partial(self._run_action, action),
                    help=help_text,
                )

        # Context-aware commands based on selected session
        main_screen = self._main_screen
        if not main_screen:
            return

        # Get selected session via the session list widget
        try:
            from ..widgets.session_list import SessionList

            session_list = main_screen.query_one("#session-list", SessionList)
            selected = session_list.get_selected()
        except Exception:
            selected = None

        if selected:
            context_commands = []

            if selected.is_active:
                # Commands for running sessions
                context_commands = [
                    ("pause session", "pause", "pause without removing worktree"),
                    ("kill session", "kill", "kill and remove worktree"),
                    ("attach tmux", "attach_tmux", "attach to tmux session"),
                    ("send keys", "insert", "send keys to session"),
                    ("rename session", "rename", "rename selected session"),
                ]
            else:
                # Commands for inactive sessions
                context_commands = [
                    ("revive session", "revive", "restart the session"),
                    ("clean session", "clean", "remove from list"),
                    ("rename session", "rename", "rename selected session"),
                ]

                # Worktree navigation if available
                if selected.worktree_path:
                    context_commands.append(
                        ("open worktree", "nav_worktree", "open shell in worktree")
                    )

            for cmd_text, action, help_text in context_commands:
                score = matcher.match(cmd_text)
                if score > 0:
                    yield Hit(
                        score,
                        matcher.highlight(cmd_text),
                        partial(self._run_action, action),
                        help=help_text,
                    )

    def _run_action(self, action_name: str) -> None:
        """Execute an action on the main screen.

        Actions are mapped to MainScreen action_* methods.
        """
        main_screen = self._main_screen
        if main_screen:
            action = getattr(main_screen, f"action_{action_name}", None)
            if action:
                action()
