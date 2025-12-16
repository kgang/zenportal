"""Tests for @filepath expansion in prompts."""

import pytest
from pathlib import Path

from zen_portal.screens.new_session_modal import expand_file_reference, _MAX_PROMPT_FILE_SIZE


class TestExpandFileReference:
    """Tests for expand_file_reference function."""

    def test_plain_text_unchanged(self):
        """Plain text without @ prefix passes through unchanged."""
        text, err = expand_file_reference("hello world")
        assert text == "hello world"
        assert err is None

    def test_empty_string_unchanged(self):
        """Empty string passes through unchanged."""
        text, err = expand_file_reference("")
        assert text == ""
        assert err is None

        text, err = expand_file_reference("   ")
        assert text == ""
        assert err is None

    def test_absolute_path_expansion(self, tmp_path):
        """@/absolute/path expands to file contents."""
        test_file = tmp_path / "prompt.md"
        test_file.write_text("This is my prompt content")

        text, err = expand_file_reference(f"@{test_file}")
        assert text == "This is my prompt content"
        assert err is None

    def test_home_path_nonexistent_returns_error(self):
        """@~/nonexistent returns error message."""
        text, err = expand_file_reference("@~/nonexistent_file_12345.md")
        assert text == "@~/nonexistent_file_12345.md"
        assert err is not None
        assert "not found" in err

    def test_relative_path_with_working_dir(self, tmp_path):
        """Relative paths resolve against working_dir."""
        test_file = tmp_path / "prompts" / "system.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("System prompt from file")

        text, err = expand_file_reference("@prompts/system.md", working_dir=tmp_path)
        assert text == "System prompt from file"
        assert err is None

    def test_dot_relative_path(self, tmp_path):
        """@./path resolves relative to working_dir."""
        test_file = tmp_path / "local.md"
        test_file.write_text("Local file content")

        text, err = expand_file_reference("@./local.md", working_dir=tmp_path)
        assert text == "Local file content"
        assert err is None

    def test_nonexistent_file_returns_error(self):
        """Non-existent file returns error message."""
        text, err = expand_file_reference("@/nonexistent/path.md")
        assert text == "@/nonexistent/path.md"
        assert err is not None
        assert "not found" in err

    def test_directory_path_returns_error(self, tmp_path):
        """Directory path (not file) returns error."""
        text, err = expand_file_reference(f"@{tmp_path}")
        assert text == f"@{tmp_path}"
        assert err is not None
        assert "not found" in err

    def test_file_content_stripped(self, tmp_path):
        """File content is stripped of leading/trailing whitespace."""
        test_file = tmp_path / "padded.md"
        test_file.write_text("\n\n  Content with padding  \n\n")

        text, err = expand_file_reference(f"@{test_file}")
        assert text == "Content with padding"
        assert err is None

    def test_multiline_content(self, tmp_path):
        """Multi-line file content is preserved."""
        test_file = tmp_path / "multi.md"
        test_file.write_text("Line 1\nLine 2\nLine 3")

        text, err = expand_file_reference(f"@{test_file}")
        assert text == "Line 1\nLine 2\nLine 3"
        assert err is None

    def test_at_in_middle_of_text_unchanged(self):
        """@ in middle of text is not treated as file reference."""
        text, err = expand_file_reference("email@example.com")
        assert text == "email@example.com"
        assert err is None

        text, err = expand_file_reference("Send to @user")
        assert text == "Send to @user"
        assert err is None

    def test_without_working_dir_uses_cwd(self, tmp_path, monkeypatch):
        """Without working_dir, relative paths use cwd."""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "cwd_file.md"
        test_file.write_text("CWD content")

        text, err = expand_file_reference("@cwd_file.md")
        assert text == "CWD content"
        assert err is None

    # Robustness tests

    def test_file_too_large_returns_error(self, tmp_path):
        """Files exceeding size limit return error."""
        large_file = tmp_path / "large.md"
        # Create file just over the limit
        large_file.write_bytes(b"x" * (_MAX_PROMPT_FILE_SIZE + 1))

        text, err = expand_file_reference(f"@{large_file}")
        assert text == f"@{large_file}"
        assert err is not None
        assert "too large" in err

    def test_file_at_size_limit_succeeds(self, tmp_path):
        """Files at exactly the size limit succeed."""
        max_file = tmp_path / "max.md"
        max_file.write_bytes(b"x" * _MAX_PROMPT_FILE_SIZE)

        text, err = expand_file_reference(f"@{max_file}")
        assert text == "x" * _MAX_PROMPT_FILE_SIZE
        assert err is None

    def test_non_utf8_file_returns_error(self, tmp_path):
        """Non-UTF-8 files return error."""
        binary_file = tmp_path / "binary.md"
        # Write invalid UTF-8 bytes
        binary_file.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")

        text, err = expand_file_reference(f"@{binary_file}")
        assert text == f"@{binary_file}"
        assert err is not None
        assert "UTF-8" in err

    def test_utf8_with_bom_succeeds(self, tmp_path):
        """UTF-8 files with BOM succeed."""
        bom_file = tmp_path / "bom.md"
        # UTF-8 BOM + content
        bom_file.write_bytes(b"\xef\xbb\xbfContent with BOM")

        text, err = expand_file_reference(f"@{bom_file}")
        # BOM is preserved by read_text but stripped by our .strip()
        assert "Content with BOM" in text
        assert err is None

    def test_unicode_content(self, tmp_path):
        """Unicode content is handled correctly."""
        unicode_file = tmp_path / "unicode.md"
        unicode_file.write_text("Hello 世界 🌍 émojis", encoding="utf-8")

        text, err = expand_file_reference(f"@{unicode_file}")
        assert text == "Hello 世界 🌍 émojis"
        assert err is None

    def test_symlink_followed(self, tmp_path):
        """Symlinks are followed to target file."""
        target = tmp_path / "target.md"
        target.write_text("Target content")
        link = tmp_path / "link.md"
        link.symlink_to(target)

        text, err = expand_file_reference(f"@{link}")
        assert text == "Target content"
        assert err is None
