"""PathInput: Path input with validation and styling."""

from pathlib import Path

from textual.widgets import Input


class PathInput(Input):
    """Path input with validation and autocomplete hint."""

    DEFAULT_CSS = """
    PathInput {
        width: 100%;
        height: 1;
        border: none;
        background: $surface-darken-1;
        padding: 0 1;
    }

    PathInput:focus {
        border: none;
        background: $surface-darken-2;
    }

    PathInput.-valid {
        color: $success;
    }

    PathInput.-invalid {
        color: $error;
    }
    """

    def __init__(self, initial_path: Path | None = None, placeholder: str = "", **kwargs):
        value = str(initial_path) if initial_path else ""
        super().__init__(value=value, placeholder=placeholder, **kwargs)
        self._validate_path()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate path as user types."""
        self._validate_path()

    def _validate_path(self) -> None:
        """Update styling based on path validity."""
        self.remove_class("-valid", "-invalid")
        path_str = self.value.strip()
        if not path_str:
            return
        try:
            path = Path(path_str).expanduser()
            if path.is_dir():
                self.add_class("-valid")
            else:
                self.add_class("-invalid")
        except Exception:
            self.add_class("-invalid")

    def get_path(self) -> Path | None:
        """Get the path if valid, None otherwise."""
        path_str = self.value.strip()
        if not path_str:
            return None
        try:
            path = Path(path_str).expanduser().resolve()
            if path.is_dir():
                return path
        except Exception:
            pass
        return None
