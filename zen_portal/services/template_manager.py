"""Template manager for session template persistence.

Handles CRUD operations and JSON file storage for templates.
Templates are stored in ~/.config/zen-portal/templates.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models.template import SessionTemplate


class TemplateManager:
    """Manages session template storage and retrieval."""

    def __init__(self, config_dir: Path | None = None) -> None:
        if config_dir is None:
            config_dir = Path.home() / ".config" / "zen-portal"
        self._config_dir = config_dir
        self._templates_path = config_dir / "templates.json"
        self._templates: dict[str, SessionTemplate] = {}
        self._load()

    def _load(self) -> None:
        """Load templates from disk."""
        if not self._templates_path.exists():
            return

        try:
            data = json.loads(self._templates_path.read_text())
            templates_data = data.get("templates", [])
            for template_data in templates_data:
                template = SessionTemplate.from_dict(template_data)
                self._templates[template.id] = template
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted file - start fresh
            self._templates = {}

    def _save(self) -> None:
        """Save templates to disk."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "templates": [t.to_dict() for t in self._templates.values()]
        }
        self._templates_path.write_text(json.dumps(data, indent=2))

    def list(self) -> list[SessionTemplate]:
        """Get all templates, sorted by name."""
        return sorted(self._templates.values(), key=lambda t: t.name.lower())

    def get(self, template_id: str) -> SessionTemplate | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def get_by_name(self, name: str) -> SessionTemplate | None:
        """Get a template by name (case-insensitive)."""
        name_lower = name.lower()
        for template in self._templates.values():
            if template.name.lower() == name_lower:
                return template
        return None

    def create(self, template: SessionTemplate) -> None:
        """Create a new template."""
        self._templates[template.id] = template
        self._save()

    def update(self, template: SessionTemplate) -> bool:
        """Update an existing template. Returns True if found."""
        if template.id not in self._templates:
            return False
        self._templates[template.id] = template
        self._save()
        return True

    def delete(self, template_id: str) -> bool:
        """Delete a template. Returns True if found."""
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        self._save()
        return True

    def create_from_session_config(
        self,
        name: str,
        session_type: str,
        provider: str | None = None,
        model: str | None = None,
        directory: str | None = None,
        worktree_enabled: bool | None = None,
        initial_prompt: str | None = None,
    ) -> SessionTemplate:
        """Create a template from session configuration.

        Convenience method for creating templates from new session modal.
        """
        from ..models.session import SessionType as ModelSessionType

        # Parse session type
        try:
            s_type = ModelSessionType(session_type)
        except ValueError:
            s_type = ModelSessionType.AI

        template = SessionTemplate(
            name=name,
            session_type=s_type,
            provider=provider,
            model=model,
            directory=directory,
            worktree_enabled=worktree_enabled,
            initial_prompt=initial_prompt,
        )
        self.create(template)
        return template

    def search(self, query: str) -> list[SessionTemplate]:
        """Search templates by name (fuzzy match)."""
        if not query:
            return self.list()

        query_lower = query.lower()
        results = []
        for template in self._templates.values():
            if query_lower in template.name.lower():
                results.append(template)
        return sorted(results, key=lambda t: t.name.lower())
