"""Input validation for security."""

import re

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


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_prompt(prompt: str) -> tuple[bool, str | None]:
    """
    Validate user prompt for security issues.

    Returns (is_valid, error_message).
    """
    if not prompt or not prompt.strip():
        return False, "Prompt cannot be empty"

    prompt = prompt.strip()

    if len(prompt) < MIN_PROMPT_LENGTH:
        return False, f"Prompt too short (min {MIN_PROMPT_LENGTH} chars)"

    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, f"Prompt too long (max {MAX_PROMPT_LENGTH} chars)"

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return False, "Prompt contains suspicious patterns"

    return True, None


def validate_session_name(name: str) -> tuple[bool, str | None]:
    """
    Validate a session name.

    Session names should be alphanumeric with hyphens only.
    """
    if not name:
        return False, "Session name cannot be empty"

    if len(name) > 64:
        return False, "Session name too long (max 64 chars)"

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False, "Session name must be alphanumeric with hyphens/underscores"

    return True, None
