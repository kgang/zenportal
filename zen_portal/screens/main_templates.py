"""Template and palette actions for MainScreen.

Extracted to keep main.py under 500 lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.template import SessionTemplate


class MainScreenPaletteMixin:
    """Command palette action for MainScreen."""

    def action_command_palette(self) -> None:
        """Open the command palette for searchable command execution."""
        from .command_palette import CommandPalette
        from ..widgets.session_list import SessionList

        # Check if a session is selected for context-aware commands
        session_list = self.query_one("#session-list", SessionList)
        has_selection = session_list.get_selected() is not None

        def handle_command(command_id: str | None) -> None:
            if not command_id:
                return
            # Look up the command and execute its action
            command = self._command_registry.get(command_id)
            if command:
                action_method = getattr(self, command.action, None)
                if action_method:
                    action_method()

        self.app.push_screen(
            CommandPalette(self._command_registry, has_selection=has_selection),
            handle_command,
        )


class MainScreenTemplateMixin:
    """Template management actions for MainScreen."""

    def action_templates(self) -> None:
        """Open template picker for quick session creation."""
        from .template_picker import TemplatePicker, TemplatePickerResult, TemplateAction

        def handle_picker_result(result: TemplatePickerResult | None) -> None:
            if not result:
                return

            if result.action == TemplateAction.CREATE:
                self._create_session_from_template(result.template)

            elif result.action == TemplateAction.EDIT:
                self._edit_template(result.template)

            elif result.action == TemplateAction.DELETE:
                self._delete_template(result.template)

        self.app.push_screen(
            TemplatePicker(self._template_manager),
            handle_picker_result,
        )

    def _create_session_from_template(self, template: SessionTemplate) -> None:
        """Create a new session using template configuration."""
        from ..models.session import SessionFeatures, SessionType
        from ..services.config import ClaudeModel
        from ..services.git import GitService
        from ..widgets.session_list import SessionList
        from pathlib import Path

        # Resolve directory placeholders
        cwd = str(Path.cwd())
        git_root = None
        info = GitService.get_info(Path.cwd())
        if info:
            git_root = str(info.root)
        working_dir = template.resolve_directory(cwd, git_root)

        # Build session features
        model = None
        if template.model:
            try:
                model = ClaudeModel(template.model)
            except ValueError:
                pass

        features = SessionFeatures(
            working_dir=Path(working_dir) if working_dir else None,
            model=model,
            use_worktree=template.worktree_enabled,
            worktree_branch=template.worktree_branch_pattern,
        )

        try:
            session_type = template.session_type
            provider = template.provider or "claude"
            session = self._manager.create_session(
                template.name,
                template.initial_prompt or "",
                features=features,
                session_type=session_type,
                provider=provider,
            )
            self._refresh_sessions()
            session_list = self.query_one("#session-list", SessionList)
            session_list.selected_index = 0
            session_list.refresh(recompose=True)
            self._start_rapid_refresh()
            display_type = provider if session_type == SessionType.AI else session_type.value
            self.zen_notify(f"created {display_type}: {session.display_name}")
        except Exception as e:
            # Log unexpected errors during session creation
            self.zen_notify(f"error: {e}", "error")

    def _edit_template(self, template: SessionTemplate) -> None:
        """Open editor for an existing template."""
        from .template_editor import TemplateEditor

        def handle_save(updated: SessionTemplate | None) -> None:
            if updated:
                self._template_manager.update(updated)
                self.zen_notify(f"template saved: {updated.name}")

        self.app.push_screen(TemplateEditor(template), handle_save)

    def _delete_template(self, template: SessionTemplate) -> None:
        """Delete a template after confirmation."""
        if self._template_manager.delete(template.id):
            self.zen_notify(f"template deleted: {template.name}")
        else:
            self.zen_notify("could not delete template", "error")

    def action_new_template(self) -> None:
        """Open editor to create a new template."""
        from .template_editor import TemplateEditor

        def handle_save(template: SessionTemplate | None) -> None:
            if template:
                self._template_manager.create(template)
                self.zen_notify(f"template created: {template.name}")

        self.app.push_screen(TemplateEditor(), handle_save)
