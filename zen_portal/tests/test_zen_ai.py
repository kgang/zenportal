"""Tests for Zen AI components.

Tests context parsing, loading indicator, and prompt modal.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from zen_portal.services.context_parser import (
    parse_context_refs,
    gather_context,
    strip_refs_from_prompt,
    SessionContext,
)
from zen_portal.models.session import Session, SessionType, SessionState


class TestParseContextRefs:
    """Test @ref parsing."""

    def test_parse_single_ref(self):
        """Parse single @output reference."""
        refs = parse_context_refs("explain @output")
        assert refs == {"output"}

    def test_parse_multiple_refs(self):
        """Parse multiple references."""
        refs = parse_context_refs("check @output and @error")
        assert refs == {"output", "error"}

    def test_parse_session_ref(self):
        """Parse @session reference."""
        refs = parse_context_refs("what is @session doing?")
        assert refs == {"session"}

    def test_parse_git_ref(self):
        """Parse @git reference."""
        refs = parse_context_refs("show me @git status")
        assert refs == {"git"}

    def test_parse_all_ref(self):
        """Parse @all reference."""
        refs = parse_context_refs("give me @all context")
        assert refs == {"all"}

    def test_parse_case_insensitive(self):
        """References are case insensitive."""
        refs = parse_context_refs("check @OUTPUT and @Error")
        assert refs == {"output", "error"}

    def test_parse_no_refs(self):
        """No references returns empty set."""
        refs = parse_context_refs("just a normal question")
        assert refs == set()

    def test_parse_all_ref_types(self):
        """Parse all ref types in one prompt."""
        refs = parse_context_refs("@output @error @git @session @all")
        assert refs == {"output", "error", "git", "session", "all"}

    def test_parse_ref_in_sentence(self):
        """Parse ref embedded in sentence."""
        refs = parse_context_refs("why is @error happening in @session?")
        assert refs == {"error", "session"}

    def test_parse_invalid_ref_ignored(self):
        """Invalid refs like @foo are ignored."""
        refs = parse_context_refs("check @foo and @output")
        assert refs == {"output"}


class TestStripRefsFromPrompt:
    """Test removing @refs from prompts."""

    def test_strip_single_ref(self):
        """Strip single reference."""
        result = strip_refs_from_prompt("explain @output please")
        assert result == "explain please"

    def test_strip_multiple_refs(self):
        """Strip multiple references."""
        result = strip_refs_from_prompt("check @output and @error now")
        assert result == "check and now"

    def test_strip_preserves_question(self):
        """Strip preserves the question."""
        result = strip_refs_from_prompt("why is @error happening?")
        assert result == "why is happening?"

    def test_strip_collapses_whitespace(self):
        """Extra whitespace is collapsed."""
        result = strip_refs_from_prompt("what   @output   is this")
        assert result == "what is this"


class TestSessionContext:
    """Test SessionContext data class."""

    def test_to_system_prompt_with_session_ref(self):
        """Session ref includes basic session info."""
        context = SessionContext(
            session_name="zen-abc123",
            session_type="claude",
            session_state="running",
            session_age="5m",
            model="sonnet",
            working_dir="/home/user/project",
        )
        prompt = context.to_system_prompt({"session"})

        assert "zen-abc123" in prompt
        assert "claude" in prompt
        assert "running" in prompt
        assert "5m" in prompt
        assert "sonnet" in prompt
        assert "/home/user/project" in prompt

    def test_to_system_prompt_with_output_ref(self):
        """Output ref includes session output."""
        context = SessionContext(
            session_name="test",
            session_type="claude",
            session_state="running",
            session_age="1m",
            output_tail="some terminal output here",
        )
        prompt = context.to_system_prompt({"output"})

        assert "Session Output" in prompt
        assert "some terminal output here" in prompt

    def test_to_system_prompt_with_error_ref(self):
        """Error ref includes error message."""
        context = SessionContext(
            session_name="test",
            session_type="claude",
            session_state="failed",
            session_age="1m",
            error_message="Connection refused",
        )
        prompt = context.to_system_prompt({"error"})

        assert "Error" in prompt
        assert "Connection refused" in prompt

    def test_to_system_prompt_with_git_ref(self):
        """Git ref includes git info."""
        context = SessionContext(
            session_name="test",
            session_type="claude",
            session_state="running",
            session_age="1m",
            git_branch="main",
            git_status="M file.txt",
            git_recent_commits="abc123 fix bug",
        )
        prompt = context.to_system_prompt({"git"})

        assert "Git" in prompt
        assert "main" in prompt
        assert "M file.txt" in prompt
        assert "abc123 fix bug" in prompt

    def test_to_system_prompt_empty_refs(self):
        """Empty refs returns minimal prompt."""
        context = SessionContext(
            session_name="test",
            session_type="claude",
            session_state="running",
            session_age="1m",
        )
        prompt = context.to_system_prompt(set())
        assert prompt == ""

    def test_to_system_prompt_all_ref(self):
        """@all includes everything."""
        context = SessionContext(
            session_name="zen-test",
            session_type="claude",
            session_state="running",
            session_age="2m",
            output_tail="output here",
            error_message="error here",
            git_branch="main",
        )
        prompt = context.to_system_prompt({"all"})

        assert "zen-test" in prompt
        assert "Session Output" in prompt
        assert "output here" in prompt
        assert "Error" in prompt
        assert "error here" in prompt
        assert "Git" in prompt
        assert "main" in prompt


class TestGatherContext:
    """Test gathering context from session."""

    def test_gather_basic_context(self):
        """Gather basic session context."""
        session = MagicMock(spec=Session)
        session.display_name = "zen-test"
        session.session_type = SessionType.AI
        session.provider = "claude"
        session.state = SessionState.RUNNING
        session.age_display = "5m"
        session.resolved_model = MagicMock(value="sonnet")
        session.resolved_working_dir = Path("/tmp/test")
        session.error_message = None

        manager = MagicMock()

        context = gather_context({"session"}, session, manager)

        assert context.session_name == "zen-test"
        assert context.session_type == "claude"
        assert context.session_state == "running"
        assert context.session_age == "5m"
        assert context.model == "sonnet"

    def test_gather_output_context(self):
        """Gather output context calls manager."""
        session = MagicMock(spec=Session)
        session.display_name = "test"
        session.session_type = SessionType.AI
        session.provider = "claude"
        session.state = SessionState.RUNNING
        session.age_display = "1m"
        session.resolved_model = None
        session.resolved_working_dir = None
        session.id = "test-id"

        manager = MagicMock()
        manager.get_output.return_value = "terminal output"

        context = gather_context({"output"}, session, manager)

        manager.get_output.assert_called_once_with("test-id", lines=100)
        assert context.output_tail == "terminal output"

    def test_gather_error_context(self):
        """Gather error context from session."""
        session = MagicMock(spec=Session)
        session.display_name = "test"
        session.session_type = SessionType.AI
        session.provider = "claude"
        session.state = SessionState.FAILED
        session.age_display = "1m"
        session.resolved_model = None
        session.resolved_working_dir = None
        session.error_message = "binary not found"

        manager = MagicMock()

        context = gather_context({"error"}, session, manager)

        assert context.error_message == "binary not found"


