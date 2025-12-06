"""SessionInfoView widget for displaying session metadata."""

import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState


def _get_git_info(working_dir: Path) -> dict | None:
    """Get git info for a directory (branch, commit, dirty state)."""
    try:
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()

        # Get short commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit = result.stdout.strip() if result.returncode == 0 else ""

        # Check if dirty (uncommitted changes)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        is_dirty = bool(result.stdout.strip()) if result.returncode == 0 else False

        return {"branch": branch, "commit": commit, "dirty": is_dirty}
    except Exception:
        return None


def _get_git_repo_name(working_dir: Path) -> str | None:
    """Get git repo name from remote URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        # Extract repo name from URL (handles both HTTPS and SSH formats)
        # e.g., "git@github.com:user/repo.git" or "https://github.com/user/repo.git"
        name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name or None
    except Exception:
        return None


def _get_env_symlinks(working_dir: Path) -> list[str]:
    """Get list of env file symlinks in the directory."""
    env_patterns = [".env", ".env.local", ".env.secrets", ".env.development"]
    symlinks = []
    try:
        for pattern in env_patterns:
            path = working_dir / pattern
            if path.is_symlink():
                symlinks.append(pattern)
    except Exception:
        pass
    return symlinks


class SessionInfoView(Static):
    """Minimalist zen panel showing session metadata.

    Displayed when information mode is active instead of output view.
    """

    session: reactive[Session | None] = reactive(None)

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

        # Core identity - compact single section
        state_display = self._format_state(s.state)
        lines.append(f"{s.status_glyph} {s.display_name}")
        lines.append(f"[dim]{s.session_type.value}  {state_display}  {s.age_display}[/dim]")

        # Location - only if meaningful
        working_path = s.worktree_path or s.resolved_working_dir
        if working_path:
            lines.append("")
            path_str = str(working_path)
            # Show just the last 2 path components for brevity
            parts = path_str.split("/")
            if len(parts) > 2:
                path_str = ".../" + "/".join(parts[-2:])
            lines.append(f"[dim]dir[/dim]  {path_str}")

        # Git info - single line summary
        if working_path and working_path.exists():
            git_info = _get_git_info(working_path)
            if git_info:
                branch = git_info["branch"]
                commit = git_info["commit"][:7] if git_info["commit"] else ""
                dirty = "*" if git_info["dirty"] else ""
                lines.append(f"[dim]git[/dim]  {branch}{dirty} {commit}")

            # Repo name - only for worktree sessions
            if s.worktree_path:
                repo_name = _get_git_repo_name(working_path)
                if repo_name:
                    lines.append(f"[dim]repo[/dim]  {repo_name}")

        # Model - only for AI sessions with explicit model
        if s.resolved_model:
            lines.append(f"[dim]model[/dim]  {s.resolved_model.value}")

        # Tokens - detailed breakdown for Claude
        if s.session_type.value == "claude" and s.token_stats:
            lines.append("")
            ts = s.token_stats
            # Format token counts (K for thousands)
            def fmt(n: int) -> str:
                return f"{n/1000:.1f}k" if n >= 1000 else str(n)

            # Main line: total with input/output breakdown
            lines.append(f"[dim]tokens[/dim]  {fmt(ts.total_tokens)}  [dim]({fmt(ts.input_tokens)}↓ {fmt(ts.output_tokens)}↑)[/dim]")

            # Cache line - only if cache tokens exist
            if ts.cache_tokens > 0:
                cache_parts = []
                if ts.cache_read_tokens > 0:
                    cache_parts.append(f"{fmt(ts.cache_read_tokens)} read")
                if ts.cache_creation_tokens > 0:
                    cache_parts.append(f"{fmt(ts.cache_creation_tokens)} write")
                lines.append(f"[dim]cache[/dim]  {' / '.join(cache_parts)}")

        # Prompt preview - truncated
        if s.prompt:
            lines.append("")
            prompt_preview = s.prompt[:50].replace("\n", " ")
            if len(s.prompt) > 50:
                prompt_preview += "..."
            lines.append(f"[dim]prompt[/dim]")
            lines.append(f"  {prompt_preview}")

        return "\n".join(lines)

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

    def watch_session(self, new_session: Session | None) -> None:
        """Update display when session changes."""
        self.refresh(recompose=True)

    def update_session(self, session: Session | None) -> None:
        """Update the displayed session."""
        self.session = session
