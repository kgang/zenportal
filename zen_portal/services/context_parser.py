"""Context parser for Zen AI @ref syntax.

Parses prompts for context references like @output, @error, @git, @session
and gathers the referenced context from the current session.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.session import Session
    from .session_manager import SessionManager


# Pattern for @references in prompts
# Matches @word at word boundaries
REF_PATTERN = re.compile(r'@(output|error|git|session|all)\b', re.IGNORECASE)


@dataclass
class SessionContext:
    """Context gathered from a session for AI queries."""

    session_name: str = ""
    session_type: str = ""
    session_state: str = ""
    session_age: str = ""
    model: str = ""
    working_dir: str = ""

    # Content fields (populated on demand)
    output_tail: str = ""  # Last N lines of output
    error_message: str = ""  # Most recent error
    git_branch: str = ""
    git_status: str = ""
    git_recent_commits: str = ""

    def to_system_prompt(self, refs: set[str]) -> str:
        """Convert context to system prompt based on requested refs.

        Args:
            refs: Set of reference types to include

        Returns:
            Formatted system prompt with context
        """
        sections = []

        # Always include basic session info if any ref is present
        if refs:
            sections.append(f"Session: {self.session_name} ({self.session_type})")
            sections.append(f"State: {self.session_state}, Age: {self.session_age}")
            if self.working_dir:
                sections.append(f"Working directory: {self.working_dir}")
            if self.model:
                sections.append(f"Model: {self.model}")

        # Add requested content
        if "output" in refs or "all" in refs:
            if self.output_tail:
                sections.append(f"\n--- Session Output (last 100 lines) ---\n{self.output_tail}")
            else:
                sections.append("\n--- Session Output ---\n(no output available)")

        if "error" in refs or "all" in refs:
            if self.error_message:
                sections.append(f"\n--- Error ---\n{self.error_message}")
            else:
                sections.append("\n--- Error ---\n(no error detected)")

        if "git" in refs or "all" in refs:
            git_info = []
            if self.git_branch:
                git_info.append(f"Branch: {self.git_branch}")
            if self.git_status:
                git_info.append(f"Status:\n{self.git_status}")
            if self.git_recent_commits:
                git_info.append(f"Recent commits:\n{self.git_recent_commits}")
            if git_info:
                sections.append("\n--- Git ---\n" + "\n".join(git_info))
            else:
                sections.append("\n--- Git ---\n(not a git repository)")

        if "session" in refs or "all" in refs:
            # Session info already included above
            pass

        return "\n".join(sections)


def parse_context_refs(prompt: str) -> set[str]:
    """Extract @references from a prompt.

    Args:
        prompt: User's prompt text

    Returns:
        Set of reference types found (lowercase)

    Example:
        >>> parse_context_refs("why is @error happening?")
        {'error'}
        >>> parse_context_refs("explain @output and check @git")
        {'output', 'git'}
    """
    matches = REF_PATTERN.findall(prompt)
    return {m.lower() for m in matches}


def gather_context(
    refs: set[str],
    session: "Session",
    manager: "SessionManager",
) -> SessionContext:
    """Gather context from a session based on requested refs.

    Args:
        refs: Set of reference types to gather
        session: Current session
        manager: Session manager for output access

    Returns:
        SessionContext with requested data populated
    """
    context = SessionContext(
        session_name=session.display_name,
        session_type=session.session_type.value,
        session_state=session.state.value,
        session_age=session.age_display,
        model=session.resolved_model.value if session.resolved_model else "",
        working_dir=str(session.resolved_working_dir) if session.resolved_working_dir else "",
    )

    # Gather output if requested
    if "output" in refs or "all" in refs:
        try:
            output = manager.get_output(session.id, lines=100)
            context.output_tail = output.strip() if output else ""
        except Exception:
            context.output_tail = ""

    # Get error message
    if "error" in refs or "all" in refs:
        context.error_message = session.error_message or ""

    # Gather git info if requested
    if "git" in refs or "all" in refs:
        working_dir = session.resolved_working_dir
        if working_dir and working_dir.exists():
            context.git_branch = _get_git_branch(working_dir)
            context.git_status = _get_git_status(working_dir)
            context.git_recent_commits = _get_git_log(working_dir)

    return context


def strip_refs_from_prompt(prompt: str) -> str:
    """Remove @references from prompt text.

    This cleans up the prompt after refs have been parsed,
    so the AI sees a natural question.

    Args:
        prompt: Original prompt with @refs

    Returns:
        Cleaned prompt without @refs
    """
    # Replace refs with empty string, clean up extra spaces
    cleaned = REF_PATTERN.sub("", prompt)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _get_git_branch(working_dir: Path) -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _get_git_status(working_dir: Path) -> str:
    """Get git status --short output."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            status = result.stdout.strip()
            # Limit to first 20 lines
            lines = status.split("\n")[:20]
            if len(lines) == 20:
                lines.append("...")
            return "\n".join(lines)
    except Exception:
        pass
    return ""


def _get_git_log(working_dir: Path, count: int = 5) -> str:
    """Get recent git commits."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{count}"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
