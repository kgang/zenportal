"""SessionStateWatcher: Async session state monitoring.

Replaces polling with event-driven async state updates.
Uses asyncio.to_thread() to prevent blocking the event loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from ...models.session import Session, SessionState, SessionType
from ..tmux_async import AsyncTmuxService

if TYPE_CHECKING:
    from ..session_manager import SessionManager


@dataclass
class StateChangeEvent:
    """Event emitted when session state changes."""

    session: Session
    old_state: SessionState
    new_state: SessionState
    timestamp: datetime


async def detect_session_state_async(
    async_tmux: AsyncTmuxService,
    tmux_name: str,
) -> tuple[SessionState, int | None, str]:
    """Async version of detect_session_state.

    Returns:
        Tuple of (state, exit_code, error_message)
    """
    # Session doesn't exist at all
    if not await async_tmux.session_exists(tmux_name):
        return SessionState.COMPLETED, None, ""

    # Session exists but pane is dead (process exited)
    if await async_tmux.is_pane_dead(tmux_name):
        exit_code = await async_tmux.get_pane_exit_status(tmux_name)
        if exit_code is not None and exit_code != 0:
            return SessionState.FAILED, exit_code, f"Process exited with code {exit_code}"
        return SessionState.COMPLETED, exit_code, ""

    # Session exists and pane is alive
    return SessionState.RUNNING, None, ""


class SessionStateWatcher:
    """Async session state monitoring - replaces polling.

    Instead of polling every 1s with blocking calls, this watcher:
    1. Uses async tmux calls (non-blocking via asyncio.to_thread)
    2. Runs with a longer heartbeat interval (10s vs 1s)
    3. Provides immediate refresh on demand (for user actions)

    Example:
        watcher = SessionStateWatcher(async_tmux, manager)
        await watcher.start()

        # On user action (e.g., after creating session):
        changed = await watcher.refresh_now()
        if changed:
            signal.set(manager.sessions)

        # Cleanup:
        await watcher.stop()
    """

    HEARTBEAT_INTERVAL = 10.0  # Much longer than previous 1s polling

    def __init__(
        self,
        async_tmux: AsyncTmuxService,
        manager: SessionManager,
        on_state_change: Callable[[StateChangeEvent], None] | None = None,
    ) -> None:
        """Initialize watcher.

        Args:
            async_tmux: Async tmux service for non-blocking operations
            manager: Session manager for session access
            on_state_change: Optional callback when state changes
        """
        self._async_tmux = async_tmux
        self._manager = manager
        self._on_state_change = on_state_change
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background state watching."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop background watching."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def refresh_now(self) -> list[Session]:
        """Trigger immediate async refresh.

        Returns:
            List of sessions whose state changed
        """
        return await self._refresh_all_async()

    async def _watch_loop(self) -> None:
        """Background heartbeat loop.

        Runs at a much longer interval than previous polling (10s vs 1s).
        Most updates come from event-triggered refresh_now() calls.
        """
        while self._running:
            try:
                await self._refresh_all_async()
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception:
                # Don't crash the loop on errors
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _refresh_all_async(self) -> list[Session]:
        """Non-blocking state refresh for all sessions.

        Returns:
            List of sessions whose state changed
        """
        changed: list[Session] = []

        for session in self._manager.sessions:
            if session.state != SessionState.RUNNING:
                continue

            tmux_name = self._manager.get_tmux_session_name(session.id)
            if not tmux_name:
                continue

            # Clear revival marker if present
            if session.revived_at:
                session.revived_at = None

            # Async state detection
            new_state, exit_code, error_msg = await detect_session_state_async(
                self._async_tmux,
                tmux_name,
            )

            if new_state != session.state:
                old_state = session.state
                session.state = new_state
                session.ended_at = datetime.now() if new_state != SessionState.RUNNING else None
                session.error_message = error_msg
                changed.append(session)

                # Emit change event
                if self._on_state_change:
                    self._on_state_change(StateChangeEvent(
                        session=session,
                        old_state=old_state,
                        new_state=new_state,
                        timestamp=datetime.now(),
                    ))

            # Update tokens for running Claude AI sessions
            if (session.state == SessionState.RUNNING
                    and session.session_type == SessionType.AI
                    and getattr(session, 'provider', 'claude') == 'claude'):
                self._manager.tokens.update_session(session)

        # Persist state if anything changed
        if changed:
            self._manager.persist()

        return changed
