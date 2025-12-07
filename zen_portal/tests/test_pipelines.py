"""Tests for pipeline module and create session pipeline."""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from zen_portal.services.pipeline import StepResult, run_pipeline
from zen_portal.services.pipelines.create import (
    CreateContext,
    ValidateLimit,
    ValidateBinary,
    ResolveConfig,
    CreateSessionModel,
)
from zen_portal.services.conflict import (
    detect_conflicts,
    has_blocking_conflict,
    get_conflict_summary,
    ConflictSeverity,
)
from zen_portal.models.session import Session, SessionState, SessionType


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_success_creates_ok_result(self):
        result = StepResult.success("value")
        assert result.ok is True
        assert result.value == "value"
        assert result.error is None

    def test_fail_creates_error_result(self):
        result = StepResult.fail("error message")
        assert result.ok is False
        assert result.value is None
        assert result.error == "error message"


class TestRunPipeline:
    """Tests for run_pipeline function."""

    def test_runs_all_steps_on_success(self):
        step1 = Mock(invoke=Mock(return_value=StepResult.success(2)))
        step2 = Mock(invoke=Mock(return_value=StepResult.success(4)))

        result = run_pipeline([step1, step2], 1)

        assert result.ok is True
        assert result.value == 4
        step1.invoke.assert_called_once_with(1)
        step2.invoke.assert_called_once_with(2)

    def test_stops_on_first_failure(self):
        step1 = Mock(invoke=Mock(return_value=StepResult.fail("step1 failed")))
        step2 = Mock(invoke=Mock(return_value=StepResult.success("never called")))

        result = run_pipeline([step1, step2], "input")

        assert result.ok is False
        assert result.error == "step1 failed"
        step2.invoke.assert_not_called()


class TestValidateLimit:
    """Tests for ValidateLimit step."""

    def test_allows_when_under_limit(self):
        step = ValidateLimit(max_sessions=10, current_count=5)
        ctx = CreateContext(name="test")

        result = step.invoke(ctx)

        assert result.ok is True
        assert result.value is ctx

    def test_rejects_when_at_limit(self):
        step = ValidateLimit(max_sessions=10, current_count=10)
        ctx = CreateContext(name="test")

        result = step.invoke(ctx)

        assert result.ok is False
        assert "Maximum sessions" in result.error

    def test_rejects_when_over_limit(self):
        step = ValidateLimit(max_sessions=5, current_count=6)
        ctx = CreateContext(name="test")

        result = step.invoke(ctx)

        assert result.ok is False


class TestValidateBinary:
    """Tests for ValidateBinary step."""

    def test_passes_when_binary_exists(self):
        commands = Mock(validate_binary=Mock(return_value=None))
        step = ValidateBinary(commands)
        ctx = CreateContext(name="test", session_type=SessionType.CLAUDE)

        result = step.invoke(ctx)

        assert result.ok is True
        commands.validate_binary.assert_called_once_with(SessionType.CLAUDE)

    def test_fails_when_binary_missing(self):
        commands = Mock(validate_binary=Mock(return_value="claude not found"))
        step = ValidateBinary(commands)
        ctx = CreateContext(name="test", session_type=SessionType.CLAUDE)

        result = step.invoke(ctx)

        assert result.ok is False
        assert "claude not found" in result.error


class TestConflictDetection:
    """Tests for conflict detection module."""

    def test_detects_name_collision(self):
        existing = [Session(name="my-session")]

        conflicts = detect_conflicts(
            name="my-session",
            session_type=SessionType.CLAUDE,
            existing=existing,
            max_sessions=10,
        )

        assert len(conflicts) == 1
        assert conflicts[0].type == "name_collision"
        assert conflicts[0].severity == ConflictSeverity.WARNING

    def test_detects_near_limit(self):
        existing = [Session(name=f"session-{i}") for i in range(8)]

        conflicts = detect_conflicts(
            name="new-session",
            session_type=SessionType.CLAUDE,
            existing=existing,
            max_sessions=10,
        )

        assert any(c.type == "near_limit" for c in conflicts)

    def test_detects_at_limit(self):
        existing = [Session(name=f"session-{i}") for i in range(10)]

        conflicts = detect_conflicts(
            name="new-session",
            session_type=SessionType.CLAUDE,
            existing=existing,
            max_sessions=10,
        )

        assert any(c.type == "at_limit" for c in conflicts)
        assert any(c.severity == ConflictSeverity.ERROR for c in conflicts)

    def test_no_conflicts_with_unique_name_under_limit(self):
        existing = [Session(name="existing")]

        conflicts = detect_conflicts(
            name="new-unique-session",
            session_type=SessionType.CLAUDE,
            existing=existing,
            max_sessions=10,
        )

        assert len(conflicts) == 0

    def test_has_blocking_conflict_with_error(self):
        existing = [Session(name=f"s{i}") for i in range(10)]
        conflicts = detect_conflicts("new", SessionType.CLAUDE, existing, 10)

        assert has_blocking_conflict(conflicts) is True

    def test_has_blocking_conflict_without_error(self):
        existing = [Session(name="existing")]
        conflicts = detect_conflicts("existing", SessionType.CLAUDE, existing, 10)

        assert has_blocking_conflict(conflicts) is False  # warning only

    def test_get_conflict_summary_returns_highest_priority(self):
        existing = [Session(name=f"s{i}") for i in range(10)]
        # This creates both a name collision (warning) and at_limit (error)
        conflicts = detect_conflicts("s0", SessionType.CLAUDE, existing, 10)

        summary = get_conflict_summary(conflicts)

        # Should return error message, not warning
        assert "maximum sessions" in summary

    def test_get_conflict_summary_returns_none_for_empty(self):
        conflicts = []
        assert get_conflict_summary(conflicts) is None
