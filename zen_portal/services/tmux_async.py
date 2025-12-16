"""Async wrapper for TmuxService - non-blocking tmux operations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zen_portal.services.tmux import TmuxResult, TmuxService


class AsyncTmuxService:
    """Async wrapper for TmuxService.

    Wraps blocking subprocess calls with asyncio.to_thread() to prevent
    blocking the event loop during state polling.

    Example:
        async_tmux = AsyncTmuxService(tmux_service)
        exists = await async_tmux.session_exists("zen-abc123")
    """

    def __init__(self, tmux: TmuxService) -> None:
        """Initialize with underlying sync TmuxService."""
        self._tmux = tmux

    async def session_exists(self, name: str) -> bool:
        """Check if a tmux session exists (non-blocking)."""
        return await asyncio.to_thread(self._tmux.session_exists, name)

    async def is_pane_dead(self, name: str) -> bool:
        """Check if a session's pane is dead (non-blocking)."""
        return await asyncio.to_thread(self._tmux.is_pane_dead, name)

    async def get_pane_exit_status(self, name: str) -> int | None:
        """Get the exit status of a dead pane's process (non-blocking)."""
        return await asyncio.to_thread(self._tmux.get_pane_exit_status, name)

    async def capture_pane(self, name: str, lines: int = 100) -> TmuxResult:
        """Capture output from a session's pane (non-blocking)."""
        return await asyncio.to_thread(self._tmux.capture_pane, name, lines)

    async def list_sessions(self) -> list[str]:
        """List all tmux session names (non-blocking)."""
        return await asyncio.to_thread(self._tmux.list_sessions)

    async def get_pane_pid(self, name: str) -> int | None:
        """Get the PID of the process running in the pane (non-blocking)."""
        return await asyncio.to_thread(self._tmux.get_pane_pid, name)

    async def get_session_cwd(self, name: str) -> Path | None:
        """Get the current working directory of a session (non-blocking)."""
        return await asyncio.to_thread(self._tmux.get_session_cwd, name)

    async def get_pane_command(self, name: str) -> str | None:
        """Get the command running in a session's pane (non-blocking)."""
        return await asyncio.to_thread(self._tmux.get_pane_command, name)

    async def kill_session(self, name: str) -> TmuxResult:
        """Kill a tmux session (non-blocking)."""
        return await asyncio.to_thread(self._tmux.kill_session, name)
