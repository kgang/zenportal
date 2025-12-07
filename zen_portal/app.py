"""Zen Portal: A contemplative multi-session Claude Code manager.

Main Textual application.
"""

import shutil
import sys
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from zen_portal.screens.main import MainScreen
from zen_portal.services.tmux import TmuxService
from zen_portal.services.session_manager import SessionManager
from zen_portal.services.config import ConfigManager
from zen_portal.services.worktree import WorktreeService
from zen_portal.services.profile import ProfileManager
from zen_portal.styles import BASE_CSS


def check_dependencies() -> None:
    """Check for required and optional dependencies on startup.

    Exits with error if critical dependencies (tmux) are missing.
    Prints warnings for optional dependencies (AI CLIs).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Critical: tmux is required for session management
    if not shutil.which("tmux"):
        errors.append("tmux is not installed or not in PATH")

    # Critical: git is required for worktree features
    if not shutil.which("git"):
        warnings.append("git is not installed - worktree isolation won't work")

    # Optional: AI assistant CLIs
    if not shutil.which("claude"):
        warnings.append("claude CLI not found - Claude Code sessions won't work")

    if not shutil.which("codex"):
        warnings.append("codex CLI not found - OpenAI Codex sessions won't work")

    if not shutil.which("gemini"):
        warnings.append("gemini CLI not found - Gemini CLI sessions won't work")

    if not shutil.which("orchat"):
        warnings.append("orchat not found - OpenRouter sessions won't work (pip install orchat)")

    # Exit with error if critical dependencies missing
    if errors:
        print("Error: Missing required dependencies:\n")
        for e in errors:
            print(f"  • {e}")
        print("\nPlease install the required dependencies and try again.")
        print("  - tmux: https://github.com/tmux/tmux")
        sys.exit(1)

    # Print warnings for optional dependencies
    if warnings:
        print("Dependency warnings:")
        for w in warnings:
            print(f"  • {w}")
        print()


def _create_worktree_service(
    config: ConfigManager, working_dir: Path
) -> WorktreeService | None:
    """Create WorktreeService from config if worktrees are configured.

    Returns None if working_dir is not a git repository.
    """
    resolved = config.resolve_features()

    # Determine source repo (config override or working_dir)
    source_repo = working_dir
    if resolved.worktree and resolved.worktree.source_repo:
        source_repo = resolved.worktree.source_repo

    # Determine base dir for worktrees
    base_dir = None
    if resolved.worktree and resolved.worktree.base_dir:
        base_dir = resolved.worktree.base_dir

    worktree_service = WorktreeService(source_repo=source_repo, base_dir=base_dir)

    # Only return service if source is a valid git repo
    if worktree_service.is_git_repo():
        return worktree_service

    return None


class ZenPortalApp(App):
    """The main Zen Portal application."""

    TITLE = "Zen Portal"
    CSS = BASE_CSS + """
    Screen {
        background: $background;
    }
    """

    # Disable built-in command palette
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+k", "keys", "Keys", show=False),
        Binding("ctrl+s", "screenshot", "Screenshot", show=False),
    ]

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        config_manager: ConfigManager | None = None,
        profile_manager: ProfileManager | None = None,
        working_dir: Path | None = None,
        focus_tmux_session: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Config manager must be created first (SessionManager depends on it)
        self._config = config_manager or ConfigManager()
        self._profile = profile_manager or ProfileManager()
        self._focus_tmux_session = focus_tmux_session

        # Use provided session manager or create one
        if session_manager:
            self._manager = session_manager
        else:
            working_dir = working_dir or Path.cwd()
            tmux = TmuxService()
            worktree = _create_worktree_service(self._config, working_dir)
            self._manager = SessionManager(
                tmux=tmux,
                config_manager=self._config,
                worktree_service=worktree,
                working_dir=working_dir,
            )

    def on_mount(self) -> None:
        """Push the main screen and apply saved theme."""
        # Apply theme from profile
        saved_theme = self._profile.profile.theme
        if saved_theme:
            self.theme = saved_theme

        self.push_screen(MainScreen(
            self._manager,
            self._config,
            self._profile,
            focus_tmux_session=self._focus_tmux_session,
        ))

def main():
    """Run the Zen Portal application."""
    import subprocess

    # Check dependencies before starting
    check_dependencies()

    # Create managers once - persist across attach/detach cycles
    working_dir = Path.cwd()
    config = ConfigManager()
    profile = ProfileManager()
    tmux = TmuxService()
    worktree = _create_worktree_service(config, working_dir)
    manager = SessionManager(
        tmux=tmux,
        config_manager=config,
        worktree_service=worktree,
        working_dir=working_dir,
    )

    focus_tmux_session = None
    while True:
        app = ZenPortalApp(
            session_manager=manager,
            config_manager=config,
            profile_manager=profile,
            focus_tmux_session=focus_tmux_session,
        )
        result = app.run()

        # Handle attach exit - attach to tmux then return to TUI
        if result and isinstance(result, str) and result.startswith("attach:"):
            tmux_name = result.split(":", 1)[1]
            # Run tmux attach, wait for detach, then loop back to TUI
            subprocess.run(["tmux", "attach", "-t", tmux_name])
            # Focus on the session we just detached from
            focus_tmux_session = tmux_name
            continue

        # Handle "keep all running" exit - show which sessions are still active
        if result and isinstance(result, dict) and "kept_sessions" in result:
            kept = result["kept_sessions"]
            if kept:
                print("\nSessions kept running:")
                for s in kept:
                    print(f"  • {s['display_name']} ({s['tmux_name']})")
                print("\nTo attach: tmux attach -t <session-name>")
                print("To list:   tmux ls")
            break

        # Any other exit breaks the loop
        break


if __name__ == "__main__":
    main()
