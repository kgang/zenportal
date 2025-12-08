"""Session template model for reusable session configurations.

Templates capture preferred session settings for quick session creation.
Supports directory placeholders ($CWD, $GIT_ROOT) for portable templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import uuid

from .session import SessionType


@dataclass
class SessionTemplate:
    """A reusable session configuration template."""

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # Session configuration
    session_type: SessionType = SessionType.AI
    provider: str | None = None  # "claude", "codex", "gemini", "openrouter"
    model: str | None = None     # Model identifier (e.g., "sonnet", "opus")

    # Execution environment
    directory: str | None = None  # Path with $CWD, $GIT_ROOT placeholders
    worktree_enabled: bool | None = None
    worktree_branch_pattern: str | None = None  # e.g., "feature/{name}"

    # Initialization
    initial_prompt: str | None = None

    def resolve_directory(self, cwd: str, git_root: str | None = None) -> str:
        """Replace directory placeholders with actual paths.

        Placeholders:
            $CWD - Current working directory
            $GIT_ROOT - Git repository root (falls back to $CWD)
        """
        if self.directory is None:
            return cwd

        result = self.directory
        result = result.replace("$CWD", cwd)
        result = result.replace("$GIT_ROOT", git_root or cwd)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary, omitting None values."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "session_type": self.session_type.value,
        }

        if self.provider is not None:
            result["provider"] = self.provider
        if self.model is not None:
            result["model"] = self.model
        if self.directory is not None:
            result["directory"] = self.directory
        if self.worktree_enabled is not None:
            result["worktree_enabled"] = self.worktree_enabled
        if self.worktree_branch_pattern is not None:
            result["worktree_branch_pattern"] = self.worktree_branch_pattern
        if self.initial_prompt is not None:
            result["initial_prompt"] = self.initial_prompt

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionTemplate":
        """Deserialize from dictionary."""
        # Parse session type with fallback
        session_type = SessionType.AI
        if data.get("session_type"):
            try:
                session_type = SessionType(data["session_type"])
            except ValueError:
                pass

        # Parse created_at
        created_at = datetime.now()
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except ValueError:
                pass

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            created_at=created_at,
            session_type=session_type,
            provider=data.get("provider"),
            model=data.get("model"),
            directory=data.get("directory"),
            worktree_enabled=data.get("worktree_enabled"),
            worktree_branch_pattern=data.get("worktree_branch_pattern"),
            initial_prompt=data.get("initial_prompt"),
        )

    @property
    def display_type(self) -> str:
        """Human-readable type for display."""
        if self.session_type == SessionType.SHELL:
            return "shell"
        return self.provider or "ai"

    @property
    def summary(self) -> str:
        """Brief description of template configuration."""
        parts = [self.display_type]
        if self.model:
            parts.append(self.model)
        if self.worktree_enabled:
            parts.append("worktree")
        return " · ".join(parts)
