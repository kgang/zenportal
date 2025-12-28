"""Input validation for Zenportal.

Provides ValidationResult dataclass and validators for session creation.
Business logic is separated from UI for testability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models.session import Session

# Patterns that suggest command injection attempts
SUSPICIOUS_PATTERNS = [
    r"`[^`]+`",  # Backticks
    r"\$\([^)]+\)",  # Command substitution
    r"&&\s*\w+",  # Command chaining with &&
    r"\|\|\s*\w+",  # Command chaining with ||
    r";\s*\w+",  # Semicolon command separation
    r">\s*/[a-z]",  # Redirect to absolute path
    r"rm\s+-[rf]+",  # Dangerous rm variations
    r"chmod\s+[0-7]+",  # Permission changes
    r"curl\s+.+\|\s*sh",  # Pipe curl to shell
    r"wget\s+.+\|\s*sh",  # Pipe wget to shell
]

MAX_PROMPT_LENGTH = 2000
MIN_PROMPT_LENGTH = 1
MAX_SESSION_NAME_LENGTH = 64


# Re-export ValidationError from exceptions for backwards compatibility
from ..models.exceptions import ValidationError  # noqa: E402, F401


@dataclass
class ValidationResult:
    """Result of a validation check.

    Supports errors (blocking) and warnings (advisory).
    """

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if there are any errors or warnings."""
        return bool(self.errors or self.warnings)

    @property
    def first_error(self) -> str | None:
        """Get the first error message, if any."""
        return self.errors[0] if self.errors else None

    @property
    def first_warning(self) -> str | None:
        """Get the first warning message, if any."""
        return self.warnings[0] if self.warnings else None

    @property
    def first_issue(self) -> str | None:
        """Get the first issue (error or warning)."""
        return self.first_error or self.first_warning

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another result into this one."""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class SessionValidator:
    """Validates session creation inputs.

    Extracted from NewSessionModal for testability.
    """

    def validate_name(
        self,
        name: str,
        existing_names: set[str] | None = None,
    ) -> ValidationResult:
        """Validate session name.

        Args:
            name: Proposed session name
            existing_names: Set of existing session names for duplicate check

        Returns:
            ValidationResult with errors/warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        name = name.strip() if name else ""

        if not name:
            errors.append("session name cannot be empty")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        if len(name) > MAX_SESSION_NAME_LENGTH:
            errors.append(f"name too long (max {MAX_SESSION_NAME_LENGTH} chars)")

        # Check for duplicates (warning, not error - tmux allows duplicates)
        if existing_names and name in existing_names:
            warnings.append(f"'{name}' already exists")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_directory(self, path_str: str) -> ValidationResult:
        """Validate working directory.

        Args:
            path_str: Directory path string

        Returns:
            ValidationResult with errors/warnings
        """
        errors: list[str] = []

        if not path_str or not path_str.strip():
            errors.append("directory cannot be empty")
            return ValidationResult(is_valid=False, errors=errors)

        path_str = path_str.strip()

        # Expand ~ to home directory
        if path_str.startswith("~"):
            path_str = str(Path.home()) + path_str[1:]

        try:
            path = Path(path_str).expanduser().resolve()
            if not path.exists():
                errors.append(f"directory does not exist: {path_str}")
            elif not path.is_dir():
                errors.append(f"path is not a directory: {path_str}")
        except Exception as e:
            errors.append(f"invalid path: {e}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def validate_prompt(self, prompt: str, required: bool = False) -> ValidationResult:
        """Validate session prompt.

        Args:
            prompt: Initial prompt for the session
            required: Whether prompt is required

        Returns:
            ValidationResult with errors/warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        prompt = prompt.strip() if prompt else ""

        if required and not prompt:
            errors.append("prompt cannot be empty")
            return ValidationResult(is_valid=False, errors=errors)

        if prompt:
            if len(prompt) < MIN_PROMPT_LENGTH:
                errors.append(f"prompt too short (min {MIN_PROMPT_LENGTH} chars)")

            if len(prompt) > MAX_PROMPT_LENGTH:
                errors.append(f"prompt too long (max {MAX_PROMPT_LENGTH} chars)")

            # Check for suspicious patterns
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, prompt, re.IGNORECASE):
                    warnings.append("prompt contains potentially unsafe patterns")
                    break

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_for_creation(
        self,
        name: str,
        directory: str,
        existing_sessions: list[Session] | None = None,
        prompt: str = "",
        prompt_required: bool = False,
    ) -> ValidationResult:
        """Validate all inputs for session creation.

        Args:
            name: Session name
            directory: Working directory
            existing_sessions: Existing sessions for duplicate check
            prompt: Optional initial prompt
            prompt_required: Whether prompt is required

        Returns:
            Merged ValidationResult from all checks
        """
        existing_names = {s.name for s in existing_sessions} if existing_sessions else set()

        result = self.validate_name(name, existing_names)
        result = result.merge(self.validate_directory(directory))

        if prompt or prompt_required:
            result = result.merge(self.validate_prompt(prompt, prompt_required))

        return result


# Legacy functions for backwards compatibility
def validate_prompt(prompt: str) -> tuple[bool, str | None]:
    """Validate user prompt for security issues.

    Returns (is_valid, error_message).

    Note: Use SessionValidator.validate_prompt() for new code.
    """
    result = SessionValidator().validate_prompt(prompt, required=True)
    return result.is_valid, result.first_issue


def validate_session_name(name: str) -> tuple[bool, str | None]:
    """Validate a session name.

    Returns (is_valid, error_message).

    Note: Use SessionValidator.validate_name() for new code.
    """
    result = SessionValidator().validate_name(name)
    return result.is_valid, result.first_issue
