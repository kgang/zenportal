"""Zen Portal: A contemplative multi-session Claude Code manager.

Main Textual application.
"""

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from zen_portal.screens.main import MainScreen
from zen_portal.services.tmux import TmuxService
from zen_portal.services.session_manager import SessionManager
from zen_portal.services.session_state import SessionStateService
from zen_portal.services.config import ConfigManager
from zen_portal.services.worktree import WorktreeService
from zen_portal.services.profile import ProfileManager
from zen_portal.services.notification import NotificationService
from zen_portal.services.discovery import DiscoveryService
from zen_portal.styles import BASE_CSS


@dataclass
class Services:
    """Application service container for dependency injection."""

    tmux: TmuxService
    config: ConfigManager
    profile: ProfileManager
    notification: NotificationService
    sessions: SessionManager
    state: SessionStateService
    worktree: WorktreeService | None
    discovery: DiscoveryService

    @classmethod
    def create(cls, working_dir: Path | None = None) -> "Services":
        """Wire up all services with proper dependencies.

        Args:
            working_dir: Working directory for session creation (defaults to cwd)

        Returns:
            Services container with all dependencies injected
        """
        working_dir = working_dir or Path.cwd()

        # Core services (no dependencies)
        tmux = TmuxService()
        config = ConfigManager()
        profile = ProfileManager()
        notification = NotificationService()
        discovery = DiscoveryService(working_dir)

        # State directory
        base_dir = Path.home() / ".zen_portal"
        state = SessionStateService(base_dir)

        # Worktree service (conditional on git repo)
        worktree = _create_worktree_service(config, working_dir)

        # Session manager (depends on tmux, config, state, worktree)
        sessions = SessionManager(
            tmux=tmux,
            config_manager=config,
            worktree_service=worktree,
            working_dir=working_dir,
            state_service=state,
        )

        return cls(
            tmux=tmux,
            config=config,
            profile=profile,
            notification=notification,
            sessions=sessions,
            state=state,
            worktree=worktree,
            discovery=discovery,
        )


def _clear_pycache() -> None:
    """Clear Python bytecode cache to ensure fresh code on restart."""
    package_dir = Path(__file__).parent
    for cache_dir in package_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


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

    BINDINGS = [
        Binding("ctrl+k", "keys", "Keys", show=False),
        Binding("ctrl+s", "screenshot", "Screenshot", show=False),
    ]

    def __init__(
        self,
        services: Services | None = None,
        focus_tmux_session: str | None = None,
        **kwargs,
    ):
        """Initialize the app with injected services.

        Args:
            services: Service container (created if not provided for backward compat)
            focus_tmux_session: Optional tmux session to focus on mount
            **kwargs: Additional Textual app arguments
        """
        super().__init__(**kwargs)

        # Use injected services or create for backward compatibility
        self.services = services or Services.create()
        self._focus_tmux_session = focus_tmux_session

    def on_mount(self) -> None:
        """Push the main screen and apply saved theme."""
        # Apply theme from profile
        saved_theme = self.services.profile.profile.theme
        if saved_theme:
            self.theme = saved_theme

        self.push_screen(MainScreen(
            self.services.sessions,
            self.services.config,
            self.services.profile,
            focus_tmux_session=self._focus_tmux_session,
        ))

    @property
    def notification_service(self) -> NotificationService:
        """Access notification service."""
        return self.services.notification


def main():
    """Run the Zen Portal application."""
    import subprocess

    # Check dependencies before starting
    check_dependencies()

    # Create services once - persist across attach/detach cycles
    services = Services.create(working_dir=Path.cwd())

    focus_tmux_session = None
    while True:
        app = ZenPortalApp(
            services=services,
            focus_tmux_session=focus_tmux_session,
        )
        result = app.run()

        # Handle restart - re-exec process for fresh code
        if result == "restart":
            _clear_pycache()
            os.execv(sys.executable, [sys.executable] + sys.argv)

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
