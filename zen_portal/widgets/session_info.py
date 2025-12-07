"""SessionInfoView widget for displaying session metadata."""

import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static, Sparkline

from ..models.session import Session, SessionState
from ..services.proxy_monitor import ProxyMonitor


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


class SessionInfoView(Static, can_focus=False):
    """Minimalist zen panel showing session metadata.

    Displayed when information mode is active instead of output view.
    This widget is intentionally non-focusable - all interactions
    are handled by MainScreen keybindings.
    """

    session: reactive[Session | None] = reactive(None)

    def __init__(self, proxy_monitor: ProxyMonitor | None = None, **kwargs):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor

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

    SessionInfoView #token-sparkline {
        height: 2;
        width: 100%;
        margin-top: 1;
    }

    SessionInfoView #token-sparkline > .sparkline--max-color {
        color: $text-muted;
    }

    SessionInfoView #token-sparkline > .sparkline--min-color {
        color: $surface-lighten-1;
    }
    """

    def compose(self) -> ComposeResult:
        if not self.session:
            yield Static("\n\n\n\n      ·\n\n    select a session", classes="empty-message")
            return

        yield Static("info", classes="title")
        yield Static(self._render_info(), classes="content")

        # Sparkline for Claude sessions with token history
        if (
            self.session
            and self.session.session_type.value == "claude"
            and self.session.token_history
            and len(self.session.token_history) > 1
        ):
            yield Sparkline(
                self.session.token_history,
                summary_function=max,
                id="token-sparkline",
            )

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

        # Tokens - zen breakdown for Claude sessions
        if s.session_type.value == "claude" and s.token_stats:
            lines.extend(self._render_token_section(s))

        # Enhanced proxy status - show for all sessions
        proxy_status = self._render_proxy_status(s)
        if proxy_status:
            lines.append("")
            lines.append(proxy_status)

        # Prompt preview - truncated
        if s.prompt:
            lines.append("")
            prompt_preview = s.prompt[:50].replace("\n", " ")
            if len(s.prompt) > 50:
                prompt_preview += "..."
            lines.append(f"[dim]prompt[/dim]")
            lines.append(f"  {prompt_preview}")

        # Error message for failed sessions
        if s.error_message:
            lines.append("")
            lines.append(f"[red]error[/red]  {s.error_message}")

        # Proxy warning (non-fatal issues) - legacy fallback
        if s.proxy_warning and not self._proxy_monitor:
            lines.append("")
            lines.append(f"[yellow]proxy[/yellow]  {s.proxy_warning}")

        return "\n".join(lines)

    def _render_token_section(self, s: Session) -> list[str]:
        """Render token analytics section with zen minimalism.

        Shows:
        - Token counts (input/output) in compact format
        - Cache efficiency when significant
        - Cost estimate when using proxy billing
        """
        lines = [""]
        ts = s.token_stats

        # Format helpers
        def fmt_tokens(n: int) -> str:
            """Format tokens: 1.2k for thousands, raw for small."""
            if n >= 1_000_000:
                return f"{n/1_000_000:.1f}M"
            if n >= 1000:
                return f"{n/1000:.1f}k"
            return str(n)

        def fmt_cost(cost: float) -> str:
            """Format cost: $0.00 or $0.000 for sub-cent."""
            if cost >= 0.01:
                return f"${cost:.2f}"
            if cost >= 0.001:
                return f"${cost:.3f}"
            return f"${cost:.4f}"

        # Main token line: total with breakdown
        # Format: "tokens  15.2k  (12.1k↓ 3.1k↑)"
        lines.append(
            f"[dim]tokens[/dim]  {fmt_tokens(ts.total_tokens)}  "
            f"[dim]({fmt_tokens(ts.input_tokens)}↓ {fmt_tokens(ts.output_tokens)}↑)[/dim]"
        )

        # Cache line - only if meaningful (>1k tokens)
        if ts.cache_tokens > 1000:
            # Show cache efficiency as ratio of reads to total
            cache_read = fmt_tokens(ts.cache_read_tokens)
            cache_write = fmt_tokens(ts.cache_creation_tokens)
            if ts.cache_read_tokens > 0 and ts.cache_creation_tokens > 0:
                lines.append(f"[dim]cache[/dim]  {cache_read} read / {cache_write} write")
            elif ts.cache_read_tokens > 0:
                lines.append(f"[dim]cache[/dim]  {cache_read} read")
            elif ts.cache_creation_tokens > 0:
                lines.append(f"[dim]cache[/dim]  {cache_write} write")

        # Cost estimate - only for proxy billing sessions
        if s.uses_proxy:
            model_name = s.resolved_model.value if s.resolved_model else ""
            cost = ts.estimate_cost(model_name)
            lines.append(f"[dim]cost[/dim]  ~{fmt_cost(cost)}  [dim]openrouter[/dim]")

        return lines

    def _render_proxy_status(self, s: Session) -> str:
        """Render enhanced proxy status for the session.

        Returns:
            Formatted proxy status line or empty string if not applicable
        """
        if not self._proxy_monitor:
            # Fallback to simple proxy display if monitor not available
            if s.uses_proxy:
                model_display = s.resolved_model.value if s.resolved_model else "openrouter"
                return f"[dim]proxy[/dim]  {model_display}"
            return ""

        # Use enhanced proxy monitor for detailed status
        model_name = s.resolved_model.value if s.resolved_model else None
        proxy_display = self._proxy_monitor.get_session_status(s.uses_proxy, model_name)

        if proxy_display == "direct":
            return f"[dim]proxy[/dim]  claude account"
        elif proxy_display.startswith("proxy"):
            # Disabled or error cases
            return f"[dim]proxy[/dim]  {proxy_display}"
        else:
            # Active proxy status with metrics
            return f"[dim]proxy[/dim]  {proxy_display}"

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
