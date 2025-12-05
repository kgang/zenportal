"""Tests for banner generation."""

from zen_portal.services.banner import generate_banner, generate_banner_command


class TestBannerGeneration:
    """Tests for banner generator."""

    def test_generate_banner_returns_string(self):
        """generate_banner returns a non-empty string."""
        banner = generate_banner("test-session", "abc12345")
        assert isinstance(banner, str)
        assert len(banner) > 0

    def test_generate_banner_contains_session_name(self):
        """Banner contains the session name."""
        banner = generate_banner("my-cool-session", "abc12345")
        assert "my-cool-session" in banner

    def test_generate_banner_contains_short_id(self):
        """Banner contains the short session ID."""
        banner = generate_banner("test", "abc12345-full-uuid")
        assert "abc12345" in banner

    def test_generate_banner_deterministic(self):
        """Same inputs produce same output."""
        banner1 = generate_banner("test", "abc12345")
        banner2 = generate_banner("test", "abc12345")
        assert banner1 == banner2

    def test_generate_banner_different_ids_different_output(self):
        """Different session IDs produce different banners."""
        banner1 = generate_banner("test", "abc12345")
        banner2 = generate_banner("test", "xyz98765")
        # They should differ in at least the ID shown and possibly color/pattern
        assert banner1 != banner2

    def test_generate_banner_command_returns_shell_command(self):
        """generate_banner_command returns a shell command string."""
        cmd = generate_banner_command("test-session", "abc12345")
        assert isinstance(cmd, str)
        assert "printf" in cmd

    def test_generate_banner_command_deterministic(self):
        """Same inputs produce same command."""
        cmd1 = generate_banner_command("test", "abc12345")
        cmd2 = generate_banner_command("test", "abc12345")
        assert cmd1 == cmd2

    def test_banner_has_box_characters(self):
        """Banner contains box drawing characters."""
        banner = generate_banner("test", "abc12345")
        assert "╭" in banner or "─" in banner
