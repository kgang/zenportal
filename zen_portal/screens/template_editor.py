"""Template editor modal for creating and editing session templates.

Provides a form interface for configuring template properties
including session type, provider, model, directory, and worktree settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, Select, Static, TextArea

from .base import ZenModalScreen
from ..models.template import SessionTemplate
from ..models.session import SessionType
from ..services.config import ALL_AI_PROVIDERS

if TYPE_CHECKING:
    pass


# Provider options for select
PROVIDER_OPTIONS = [(p, p) for p in ALL_AI_PROVIDERS]

# Session type options
SESSION_TYPE_OPTIONS = [
    (SessionType.AI.value, "AI"),
    (SessionType.SHELL.value, "Shell"),
]

# Model options (common models)
MODEL_OPTIONS = [
    ("", "default"),
    ("sonnet", "sonnet"),
    ("opus", "opus"),
    ("haiku", "haiku"),
]


class TemplateEditor(ZenModalScreen[SessionTemplate | None]):
    """Modal for creating or editing a session template."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    TemplateEditor #dialog {
        border: round $primary;
    }

    TemplateEditor .field-row {
        height: auto;
        margin-bottom: 1;
    }

    TemplateEditor .field-label {
        margin-bottom: 0;
    }

    TemplateEditor Input {
        width: 100%;
    }

    TemplateEditor Select {
        width: 100%;
    }

    TemplateEditor TextArea {
        width: 100%;
        height: 5;
    }

    TemplateEditor #buttons {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    TemplateEditor Button {
        margin: 0 1;
    }

    TemplateEditor #type-provider-row {
        height: auto;
    }

    TemplateEditor #type-provider-row > Vertical {
        width: 1fr;
    }

    TemplateEditor #worktree-row {
        height: auto;
        align: left middle;
    }
    """

    def __init__(self, template: SessionTemplate | None = None) -> None:
        super().__init__()
        self._template = template
        self._is_new = template is None

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-lg")

        title = "new template" if self._is_new else "edit template"

        with Vertical(id="dialog"):
            yield Static(title, classes="dialog-title")

            # Name field
            with Vertical(classes="field-row"):
                yield Static("name", classes="field-label")
                yield Input(
                    value=self._template.name if self._template else "",
                    placeholder="template name",
                    id="name-input",
                )

            # Type and Provider row
            with Horizontal(id="type-provider-row"):
                with Vertical():
                    yield Static("type", classes="field-label")
                    yield Select(
                        SESSION_TYPE_OPTIONS,
                        value=self._template.session_type.value if self._template else SessionType.AI.value,
                        id="type-select",
                    )
                with Vertical():
                    yield Static("provider", classes="field-label")
                    yield Select(
                        PROVIDER_OPTIONS,
                        value=self._template.provider if self._template and self._template.provider else "claude",
                        id="provider-select",
                    )

            # Model field
            with Vertical(classes="field-row"):
                yield Static("model", classes="field-label")
                yield Select(
                    MODEL_OPTIONS,
                    value=self._template.model if self._template and self._template.model else "",
                    id="model-select",
                )

            # Directory field
            with Vertical(classes="field-row"):
                yield Static("directory (use $CWD, $GIT_ROOT)", classes="field-label")
                yield Input(
                    value=self._template.directory if self._template and self._template.directory else "",
                    placeholder="$GIT_ROOT or /absolute/path",
                    id="directory-input",
                )

            # Worktree settings
            with Horizontal(id="worktree-row"):
                yield Checkbox(
                    "enable worktree",
                    value=self._template.worktree_enabled if self._template and self._template.worktree_enabled else False,
                    id="worktree-checkbox",
                )

            # Branch pattern (only if worktree enabled)
            with Vertical(classes="field-row"):
                yield Static("branch pattern", classes="field-label")
                yield Input(
                    value=self._template.worktree_branch_pattern if self._template and self._template.worktree_branch_pattern else "",
                    placeholder="feature/{name}",
                    id="branch-input",
                )

            # Initial prompt
            with Vertical(classes="field-row"):
                yield Static("initial prompt (optional)", classes="field-label")
                yield TextArea(
                    text=self._template.initial_prompt if self._template and self._template.initial_prompt else "",
                    id="prompt-input",
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

            yield Static("ctrl+s save · esc cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_save(self) -> None:
        """Validate and save the template."""
        # Gather values
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            # Could show notification here
            return

        type_select = self.query_one("#type-select", Select)
        provider_select = self.query_one("#provider-select", Select)
        model_select = self.query_one("#model-select", Select)
        directory = self.query_one("#directory-input", Input).value.strip()
        worktree = self.query_one("#worktree-checkbox", Checkbox).value
        branch_pattern = self.query_one("#branch-input", Input).value.strip()
        prompt = self.query_one("#prompt-input", TextArea).text.strip()

        # Parse session type
        try:
            session_type = SessionType(type_select.value)
        except ValueError:
            session_type = SessionType.AI

        # Build template
        template = SessionTemplate(
            id=self._template.id if self._template else None,
            name=name,
            session_type=session_type,
            provider=str(provider_select.value) if provider_select.value else None,
            model=str(model_select.value) if model_select.value else None,
            directory=directory if directory else None,
            worktree_enabled=worktree if worktree else None,
            worktree_branch_pattern=branch_pattern if branch_pattern else None,
            initial_prompt=prompt if prompt else None,
        )

        # Preserve created_at for existing templates
        if self._template:
            template.created_at = self._template.created_at

        self.dismiss(template)
