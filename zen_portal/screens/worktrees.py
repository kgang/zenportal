"""WorktreesScreen: Minimalist view for managing git worktrees."""

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Static

from ..services.worktree import WorktreeService, WorktreeInfo
from ..models.session import Session


@dataclass
class WorktreeAction:
    """Result from worktree selection."""

    action: str  # "shell", "delete", "cancel"
    worktree: WorktreeInfo | None = None


class WorktreesScreen(ModalScreen[WorktreeAction | None]):
    """Minimalist worktree management view.

    Shows all worktrees with their branches and allows:
    - Opening a shell in a worktree
    - Deleting a worktree
    """

    DEFAULT_CSS = """
    /* Component-specific: worktree list styling */
    WorktreesScreen #worktree-list {
        height: auto;
        padding: 0;
    }

    WorktreesScreen .worktree-row {
        height: 2;
        padding: 0 1;
    }

    WorktreesScreen .worktree-row:hover {
        background: $surface-lighten-1;
    }

    WorktreesScreen .worktree-row.selected {
        background: $surface-lighten-1;
    }

    WorktreesScreen .worktree-row.main-repo {
        color: $text-muted;
    }

    WorktreesScreen .empty {
        color: $text-disabled;
        text-style: italic;
        padding: 1;
        text-align: center;
    }

    WorktreesScreen .session-indicator {
        color: $success;
    }
    """

    BINDINGS = [
        ("j", "move_down", "down"),
        ("k", "move_up", "up"),
        ("down", "move_down", "down"),
        ("up", "move_up", "up"),
        ("enter", "open_shell", "shell"),
        ("o", "open_shell", "shell"),
        ("d", "delete", "delete"),
        ("escape", "cancel", "cancel"),
        ("q", "cancel", "cancel"),
    ]

    def __init__(
        self,
        worktree_service: WorktreeService,
        sessions: list[Session] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._worktree = worktree_service
        self._sessions = sessions or []
        self._worktrees: list[WorktreeInfo] = []
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-xl")
        with Vertical(id="dialog"):
            yield Static("worktrees", classes="dialog-title")
            yield Vertical(id="worktree-list")
            yield Static("j/k move · enter/o shell · d delete · q close", classes="dialog-hint")

    def on_mount(self) -> None:
        self._load_worktrees()

    def _load_worktrees(self) -> None:
        """Load worktrees from the service."""
        self._worktrees = self._worktree.list_worktrees()
        # Filter out bare repositories
        self._worktrees = [wt for wt in self._worktrees if not wt.is_bare]
        self._refresh_list()

    def _get_session_for_worktree(self, worktree_path: Path) -> Session | None:
        """Find a zen-portal session associated with this worktree."""
        for session in self._sessions:
            if session.worktree_path and session.worktree_path == worktree_path:
                return session
        return None

    def _is_main_repo(self, worktree: WorktreeInfo) -> bool:
        """Check if this worktree is the main repository (not a worktree)."""
        return worktree.path == self._worktree.source_repo

    def _refresh_list(self) -> None:
        """Refresh the worktree list display."""
        worktree_list = self.query_one("#worktree-list", Vertical)
        worktree_list.remove_children()

        if not self._worktrees:
            worktree_list.mount(Static("no worktrees", classes="empty"))
            return

        for i, wt in enumerate(self._worktrees):
            is_main = self._is_main_repo(wt)
            session = self._get_session_for_worktree(wt.path)

            # Build display: branch, path, session indicator
            branch_display = wt.branch or "(detached)"
            path_display = str(wt.path)

            # Truncate path if too long
            max_path_len = 50
            if len(path_display) > max_path_len:
                path_display = "..." + path_display[-(max_path_len - 3):]

            # Session indicator
            session_mark = ""
            if session:
                status_glyph = session.status_glyph
                session_mark = f" [green]{status_glyph}[/green]"

            # Main repo indicator
            if is_main:
                label = f"  {branch_display:<20} {path_display} (main){session_mark}\n"
            else:
                label = f"  {branch_display:<20} {path_display}{session_mark}\n"

            classes = "worktree-row"
            if i == self._selected_index:
                classes += " selected"
            if is_main:
                classes += " main-repo"

            worktree_list.mount(
                Static(label, classes=classes, id=f"worktree-{i}", markup=True)
            )

    def _update_selection(self) -> None:
        """Update visual selection."""
        for i in range(len(self._worktrees)):
            try:
                item = self.query_one(f"#worktree-{i}", Static)
                if i == self._selected_index:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    def action_move_down(self) -> None:
        if self._worktrees and self._selected_index < len(self._worktrees) - 1:
            self._selected_index += 1
            self._update_selection()

    def action_move_up(self) -> None:
        if self._worktrees and self._selected_index > 0:
            self._selected_index -= 1
            self._update_selection()

    def action_open_shell(self) -> None:
        if not self._worktrees:
            return

        if self._selected_index >= len(self._worktrees):
            return

        wt = self._worktrees[self._selected_index]
        self.dismiss(WorktreeAction(action="shell", worktree=wt))

    def action_delete(self) -> None:
        if not self._worktrees:
            return

        if self._selected_index >= len(self._worktrees):
            return

        wt = self._worktrees[self._selected_index]

        # Don't allow deleting main repo
        if self._is_main_repo(wt):
            self.post_message(self.app.notifications.warning("cannot delete main repository"))
            return

        self.dismiss(WorktreeAction(action="delete", worktree=wt))

    def action_cancel(self) -> None:
        self.dismiss(None)
