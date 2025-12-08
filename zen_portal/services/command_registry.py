"""Command registry for the command palette.

Centralized command definitions with metadata for searchable access.
Commands are registered with labels, keybindings, and context requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CommandCategory(Enum):
    """Categories for organizing commands."""

    SESSION = "session"      # Session-specific actions
    NAVIGATION = "navigation"  # Navigation and movement
    VIEW = "view"            # View modes and toggles
    APP = "app"              # Application-level actions


@dataclass
class Command:
    """A command that can be executed from the palette."""

    id: str                              # Unique identifier (e.g., "rename_session")
    label: str                           # Display label (e.g., "Rename session")
    action: str                          # Action method name (e.g., "action_rename")
    category: CommandCategory = CommandCategory.APP
    keybinding: str | None = None        # Keyboard shortcut (e.g., "e")
    requires_selection: bool = False     # Requires a session to be selected
    description: str | None = None       # Optional longer description
    hidden: bool = False                 # Hide from palette (for internal commands)


@dataclass
class CommandRegistry:
    """Registry of all available commands."""

    _commands: dict[str, Command] = field(default_factory=dict)

    def register(self, command: Command) -> None:
        """Register a command."""
        self._commands[command.id] = command

    def register_all(self, commands: list[Command]) -> None:
        """Register multiple commands."""
        for command in commands:
            self.register(command)

    def get(self, command_id: str) -> Command | None:
        """Get a command by ID."""
        return self._commands.get(command_id)

    def get_all(self) -> list[Command]:
        """Get all non-hidden commands."""
        return [c for c in self._commands.values() if not c.hidden]

    def get_contextual(self, has_selection: bool) -> list[Command]:
        """Get commands available in current context.

        Args:
            has_selection: Whether a session is currently selected
        """
        return [
            c for c in self._commands.values()
            if not c.hidden and (not c.requires_selection or has_selection)
        ]

    def search(self, query: str) -> list[tuple[str, str]]:
        """Get searchable (id, label) tuples for all commands."""
        return [(c.id, c.label) for c in self.get_all()]

    def search_contextual(self, has_selection: bool) -> list[tuple[str, str]]:
        """Get searchable (id, label) tuples for contextual commands."""
        return [(c.id, c.label) for c in self.get_contextual(has_selection)]


def create_default_registry() -> CommandRegistry:
    """Create registry with all built-in commands."""
    registry = CommandRegistry()

    # Session actions (require selection)
    registry.register_all([
        Command(
            id="attach_tmux",
            label="Attach to tmux session",
            action="action_attach_tmux",
            category=CommandCategory.SESSION,
            keybinding="a",
            requires_selection=True,
            description="Attach to the tmux session for this session",
        ),
        Command(
            id="pause",
            label="Pause session",
            action="action_pause",
            category=CommandCategory.SESSION,
            keybinding="p",
            requires_selection=True,
            description="Pause the running session (preserves worktree)",
        ),
        Command(
            id="kill",
            label="Kill session",
            action="action_kill",
            category=CommandCategory.SESSION,
            keybinding="x",
            requires_selection=True,
            description="Kill the running session",
        ),
        Command(
            id="clean",
            label="Clean session",
            action="action_clean",
            category=CommandCategory.SESSION,
            keybinding="d",
            requires_selection=True,
            description="Clean up completed/killed session",
        ),
        Command(
            id="revive",
            label="Revive session",
            action="action_revive",
            category=CommandCategory.SESSION,
            keybinding="v",
            requires_selection=True,
            description="Revive a paused or completed session",
        ),
        Command(
            id="rename",
            label="Rename session",
            action="action_rename",
            category=CommandCategory.SESSION,
            keybinding="e",
            requires_selection=True,
            description="Change the session name",
        ),
        Command(
            id="insert",
            label="Send keys to session",
            action="action_insert",
            category=CommandCategory.SESSION,
            keybinding="i",
            requires_selection=True,
            description="Send keystrokes to the tmux session",
        ),
        Command(
            id="nav_worktree",
            label="Open worktree shell",
            action="action_nav_worktree",
            category=CommandCategory.SESSION,
            keybinding="w",
            requires_selection=True,
            description="Open a shell in the session's worktree",
        ),
        Command(
            id="analyze",
            label="Analyze session",
            action="action_analyze",
            category=CommandCategory.SESSION,
            keybinding="A",
            requires_selection=True,
            description="Run AI analysis on the session output",
        ),
    ])

    # Navigation actions
    registry.register_all([
        Command(
            id="move_down",
            label="Move down",
            action="action_move_down",
            category=CommandCategory.NAVIGATION,
            keybinding="j",
            hidden=True,  # Basic navigation, not needed in palette
        ),
        Command(
            id="move_up",
            label="Move up",
            action="action_move_up",
            category=CommandCategory.NAVIGATION,
            keybinding="k",
            hidden=True,
        ),
        Command(
            id="toggle_move",
            label="Reorder sessions",
            action="action_toggle_move",
            category=CommandCategory.NAVIGATION,
            keybinding="l",
            description="Enter move mode to reorder sessions",
        ),
    ])

    # View actions
    registry.register_all([
        Command(
            id="refresh_output",
            label="Refresh output",
            action="action_refresh_output",
            category=CommandCategory.VIEW,
            keybinding="r",
            description="Refresh the output display",
        ),
        Command(
            id="toggle_streaming",
            label="Toggle streaming mode",
            action="action_toggle_streaming",
            category=CommandCategory.VIEW,
            keybinding="s",
            description="Toggle automatic output streaming",
        ),
        Command(
            id="search_output",
            label="Search output",
            action="action_search_output",
            category=CommandCategory.VIEW,
            keybinding="S",
            description="Search within the output view",
        ),
        Command(
            id="toggle_info",
            label="Toggle info panel",
            action="action_toggle_info",
            category=CommandCategory.VIEW,
            keybinding="I",
            description="Switch between output and info views",
        ),
        Command(
            id="toggle_completed",
            label="Toggle completed sessions",
            action="action_toggle_completed",
            category=CommandCategory.VIEW,
            keybinding="C",
            description="Show or hide completed sessions",
        ),
        Command(
            id="view_worktrees",
            label="View all worktrees",
            action="action_view_worktrees",
            category=CommandCategory.VIEW,
            keybinding="W",
            description="Show all worktrees in the current project",
        ),
    ])

    # App actions
    registry.register_all([
        Command(
            id="new_session",
            label="New session",
            action="action_new_session",
            category=CommandCategory.APP,
            keybinding="n",
            description="Create a new AI or shell session",
        ),
        Command(
            id="attach_existing",
            label="Attach existing tmux",
            action="action_attach_existing",
            category=CommandCategory.APP,
            keybinding="o",
            description="Attach an existing tmux session",
        ),
        Command(
            id="zen_prompt",
            label="Ask AI (Zen AI)",
            action="action_zen_prompt",
            category=CommandCategory.APP,
            keybinding="/",
            description="Quick AI query without creating a session",
        ),
        Command(
            id="config",
            label="Settings",
            action="action_config",
            category=CommandCategory.APP,
            keybinding="c",
            description="Open configuration screen",
        ),
        Command(
            id="show_help",
            label="Help",
            action="action_show_help",
            category=CommandCategory.APP,
            keybinding="?",
            description="Show help screen",
        ),
        Command(
            id="restart_app",
            label="Restart application",
            action="action_restart_app",
            category=CommandCategory.APP,
            keybinding="R",
            description="Restart zenportal",
        ),
        Command(
            id="quit",
            label="Quit",
            action="action_quit",
            category=CommandCategory.APP,
            keybinding="q",
            description="Exit zenportal",
        ),
    ])

    # Template actions
    registry.register_all([
        Command(
            id="templates",
            label="Templates",
            action="action_templates",
            category=CommandCategory.APP,
            keybinding="T",
            description="Open template picker for quick session creation",
        ),
        Command(
            id="new_template",
            label="New template",
            action="action_new_template",
            category=CommandCategory.APP,
            description="Create a new session template",
        ),
    ])

    return registry
