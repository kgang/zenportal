"""Action handlers for MainScreen as a mixin.

Uses cached widget references from MainScreen via properties:
- self.session_list (SessionList)
- self.output_view (OutputView)
- self.info_view (SessionInfoView)
"""

from ..models.session import Session, SessionState, SessionType, SessionFeatures


class MainScreenActionsMixin:
    """Mixin providing action handlers for MainScreen."""

    def action_pause(self) -> None:
        """Pause selected session (ends tmux but preserves worktree)."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if not selected.is_active:
            self.zen_notify("session already ended", "warning")
            return

        had_worktree = selected.worktree_path is not None
        paused_name = selected.display_name

        self._manager.pause_session(selected.id)
        self._refresh_sessions()

        if had_worktree:
            self.zen_notify(f"paused: {paused_name} (worktree preserved)")
        else:
            self.zen_notify(f"paused: {paused_name}")

    def action_kill(self) -> None:
        """Kill selected session and remove its worktree."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if not selected.is_active:
            self.zen_notify("session already ended", "warning")
            return

        had_worktree = selected.worktree_path is not None
        self._manager.kill_session(selected.id)
        self._refresh_sessions()

        if had_worktree:
            self.zen_notify(f"killed: {selected.display_name} (worktree removed)")
        else:
            self.zen_notify(f"killed: {selected.display_name}")

    def action_clean(self) -> None:
        """Clean up an ended session (remove worktree and session from list)."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if selected.is_active:
            self.zen_notify("cannot clean active session - pause or kill first", "warning")
            return

        had_worktree = selected.worktree_path is not None
        self._manager.clean_session(selected.id)
        self._refresh_sessions()

        if had_worktree:
            self.zen_notify(f"cleaned: {selected.display_name} (worktree removed)")
        else:
            self.zen_notify(f"cleaned: {selected.display_name}")

    def action_nav_worktree(self) -> None:
        """Navigate to a session's worktree."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if selected.is_active:
            self.zen_notify("session still active - use 'a' to attach", "warning")
            return

        if not selected.worktree_path:
            self.zen_notify("session has no worktree", "warning")
            return

        new_session = self._manager.navigate_to_worktree(selected.id)
        if new_session:
            self._refresh_sessions()
            self.zen_notify(f"created shell in worktree: {new_session.display_name}")
        else:
            self.zen_notify("could not create session in worktree", "error")

    def action_view_worktrees(self) -> None:
        """Open worktrees view."""
        from .worktrees import WorktreesScreen, WorktreeAction

        if not self._manager._worktree:
            self.zen_notify("worktrees not configured", "warning")
            return

        def handle_result(result: WorktreeAction | None) -> None:
            if not result or result.action == "cancel":
                return

            wt = result.worktree
            if not wt:
                return

            if result.action == "shell":
                try:
                    features = SessionFeatures(working_dir=wt.path)
                    session = self._manager.create_session(
                        name=f"wt:{wt.branch[:12]}" if wt.branch else "worktree",
                        features=features,
                        session_type=SessionType.SHELL,
                    )
                    self._refresh_sessions()
                    self.session_list.selected_index = 0
                    self.session_list.refresh(recompose=True)
                    self._start_rapid_refresh()
                    self.zen_notify(f"shell in worktree: {wt.branch}")
                except Exception as e:
                    self.zen_notify(f"error: {e}", "error")

            elif result.action == "delete":
                wt_result = self._manager._worktree.remove_worktree(wt.path, force=True)
                if wt_result.success:
                    self.zen_notify(f"deleted worktree: {wt.branch}")
                else:
                    self.zen_notify(f"failed: {wt_result.error}", "error")

        self.app.push_screen(
            WorktreesScreen(
                worktree_service=self._manager._worktree,
                sessions=self._manager.sessions,
            ),
            handle_result,
        )

    def action_attach_tmux(self) -> None:
        """Attach to tmux session (leaves TUI)."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if not selected.is_active:
            self.zen_notify("cannot attach to ended session - revive first", "warning")
            return

        tmux_name = self._manager.get_tmux_session_name(selected.id)
        if tmux_name:
            self.app.exit(result=f"attach:{tmux_name}")

    def action_attach_existing(self) -> None:
        """Open modal to attach to an external tmux session."""
        from .attach_session import AttachSessionModal, AttachSessionResult
        from ..services.discovery import DiscoveryService

        discovery = DiscoveryService()
        prefix = f"{self._manager._get_session_prefix()}-"
        existing_ids = {s.id for s in self._manager.sessions}

        def handle_result(result: AttachSessionResult | None) -> None:
            if not result:
                return

            try:
                session = self._manager.adopt_external_tmux(
                    tmux_name=result.tmux_name,
                    claude_session_id=result.claude_session_id,
                    working_dir=result.cwd,
                )
                self._refresh_sessions()

                is_reconnection = session.id in existing_ids
                for i, s in enumerate(self._manager.sessions):
                    if s.id == session.id:
                        self.session_list.selected_index = i
                        break
                self.session_list.refresh(recompose=True)
                self._start_rapid_refresh()

                if is_reconnection:
                    self.zen_notify(f"reconnected: {session.display_name}")
                elif result.has_claude:
                    self.zen_notify(f"adopted: {session.display_name} (claude synced)")
                else:
                    self.zen_notify(f"adopted: {session.display_name}")
            except Exception as e:
                self.zen_notify(f"error: {e}", "error")

        self.app.push_screen(
            AttachSessionModal(
                discovery_service=discovery,
                tmux_service=self._manager._tmux,
                session_prefix=prefix,
            ),
            handle_result,
        )

    def action_revive(self) -> None:
        """Revive a bloomed/wilted session."""
        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if selected.is_active:
            self.zen_notify("session already running", "warning")
        elif self._manager.revive_session(selected.id):
            self._refresh_sessions()
            self._start_rapid_refresh()
            self.zen_notify(f"revived: {selected.display_name}")
        else:
            self.zen_notify("could not revive session", "error")

    def action_rename(self) -> None:
        """Rename the selected session."""
        from .rename_modal import RenameModal

        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        def handle_result(new_name: str | None) -> None:
            if new_name is None:
                return

            if self._manager.rename_session(selected.id, new_name):
                self._refresh_sessions()
                self.zen_notify(f"renamed to: {new_name}")
            else:
                self.zen_notify("could not rename session", "error")

        self.app.push_screen(RenameModal(selected.name), handle_result)

    def action_insert(self) -> None:
        """Open insert modal to send keys to session."""
        from .insert_modal import InsertModal, InsertResult

        selected = self.session_list.get_selected()
        if not selected:
            self.zen_notify("no session selected", "warning")
            return

        if not selected.is_active:
            self.zen_notify("session is not active", "warning")
            return

        def handle_result(result: InsertResult | None) -> None:
            if result is not None and result.keys:
                tmux_name = self._manager.get_tmux_session_name(selected.id)
                if tmux_name:
                    self._manager._tmux.send_keys(tmux_name, result.keys)
                    self._start_rapid_refresh()
                    preview_parts = []
                    for item in result.keys[:10]:
                        if item.is_special:
                            preview_parts.append(f"[{item.display}]")
                        elif item.value == "\n":
                            preview_parts.append("↵")
                        else:
                            preview_parts.append(item.display)
                    preview = "".join(preview_parts)[:20]
                    suffix = "..." if len(result.keys) > 10 or len(preview) > 20 else ""
                    self.zen_notify(f"sent: {preview}{suffix}")

        self.app.push_screen(InsertModal(selected.display_name), handle_result)

    def action_zen_prompt(self) -> None:
        """Open Zen AI prompt modal for quick queries."""
        self._open_zen_ai_modal()

    def action_analyze(self) -> None:
        """Analyze the selected session with AI reflection."""
        self._open_zen_ai_modal(
            preset_prompt="Analyze this session. What patterns do you see? Any suggestions?"
        )

    def _open_zen_ai_modal(self, preset_prompt: str | None = None) -> None:
        """Open Zen AI modal, optionally with a preset prompt."""
        from .zen_prompt import ZenPromptModal
        from ..services.zen_ai import ZenAI
        from ..services.config import ZenAIConfig

        # Get Zen AI config
        features = self._config.resolve_features()
        zen_ai_config = features.zen_ai or ZenAIConfig()

        # Check if Zen AI is available
        if not zen_ai_config.enabled:
            self.zen_notify("zen ai not enabled (configure in settings)", "warning")
            return

        # Create ZenAI service
        proxy_settings = features.openrouter_proxy
        zen_ai = ZenAI(zen_ai_config, proxy_settings)

        if not zen_ai.is_available:
            self.zen_notify("zen ai not available (check claude or api key)", "warning")
            return

        # Get current session for context
        selected = self.session_list.get_selected()

        def handle_result(result: str | None) -> None:
            pass  # Modal handles display

        self.app.push_screen(
            ZenPromptModal(zen_ai, selected, self._manager, preset_prompt),
            handle_result,
        )


class MainScreenExitMixin:
    """Mixin providing exit-related handlers for MainScreen."""

    def _exit_with_cleanup(
        self, cleanup_orphans: bool = False, keep_running: bool = False
    ) -> None:
        """Exit the application.

        Cleans up dead sessions (completed, failed, killed) on exit.
        Paused sessions are preserved by default to allow later revival.
        """
        # Clean up dead sessions except paused (which user explicitly preserved)
        dead_session_ids = [
            s.id for s in self._manager.sessions
            if not s.is_active and s.state != SessionState.PAUSED
        ]
        for session_id in dead_session_ids:
            self._manager.clean_session(session_id)

        if cleanup_orphans:
            self._manager.cleanup_dead_tmux_sessions()
        self._manager.save_state()

        if keep_running:
            running_sessions = []
            for session in self._manager.sessions:
                if session.is_active:
                    tmux_name = self._manager.get_tmux_session_name(session.id)
                    if tmux_name:
                        running_sessions.append({
                            "tmux_name": tmux_name,
                            "display_name": session.display_name,
                        })
            if running_sessions:
                self.app.exit(result={"kept_sessions": running_sessions})
                return

        self.app.exit()

    def action_quit(self) -> None:
        """Quit the application with optional cleanup."""
        from .exit_modal import ExitModal, ExitResult, ExitChoice
        from ..services.config import ExitBehavior

        behavior = self._config.config.exit_behavior
        active, dead = self._manager.count_by_state()

        if active == 0 and dead == 0:
            self._exit_with_cleanup()
            return

        if behavior == ExitBehavior.KILL_ALL:
            self._manager.kill_all_sessions()
            self._exit_with_cleanup(cleanup_orphans=True)
            return
        elif behavior == ExitBehavior.KILL_DEAD:
            self._manager.kill_dead_sessions()
            self._exit_with_cleanup()
            return
        elif behavior == ExitBehavior.KEEP_ALL:
            self._exit_with_cleanup(keep_running=True)
            return

        def handle_exit(result: ExitResult | None) -> None:
            if result is None:
                return

            if result.remember:
                if result.choice == ExitChoice.KILL_ALL:
                    self._config.update_exit_behavior(ExitBehavior.KILL_ALL)
                elif result.choice == ExitChoice.KILL_DEAD:
                    self._config.update_exit_behavior(ExitBehavior.KILL_DEAD)
                elif result.choice == ExitChoice.KEEP_ALL:
                    self._config.update_exit_behavior(ExitBehavior.KEEP_ALL)

            cleanup_orphans = result.choice == ExitChoice.KILL_ALL
            keep_running = result.choice == ExitChoice.KEEP_ALL
            if result.choice == ExitChoice.KILL_ALL:
                self._manager.kill_all_sessions()
            elif result.choice == ExitChoice.KILL_DEAD:
                self._manager.kill_dead_sessions()

            self._exit_with_cleanup(cleanup_orphans=cleanup_orphans, keep_running=keep_running)

        self.app.push_screen(ExitModal(active, dead), handle_exit)

    def action_restart_app(self) -> None:
        """Restart the application with cache clearing."""
        self._manager.save_state()
        self.app.exit(result="restart")
