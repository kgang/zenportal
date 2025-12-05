"""Tests for ProfileManager service."""

from pathlib import Path

import pytest

from zen_portal.services.profile import ProfileManager, UserProfile


class TestUserProfile:
    """Tests for UserProfile dataclass."""

    def test_to_dict_empty(self):
        """Empty profile returns empty dict."""
        profile = UserProfile()
        assert profile.to_dict() == {}

    def test_to_dict_with_theme(self):
        """Profile with theme includes it in dict."""
        profile = UserProfile(theme="nord")
        assert profile.to_dict() == {"theme": "nord"}

    def test_to_dict_with_all_values(self):
        """Profile with all values includes everything."""
        profile = UserProfile(
            theme="dracula",
            last_working_dir=Path("/home/user/projects"),
        )
        result = profile.to_dict()
        assert result["theme"] == "dracula"
        assert result["last_working_dir"] == "/home/user/projects"

    def test_from_dict_empty(self):
        """Empty dict creates default profile."""
        profile = UserProfile.from_dict({})
        assert profile.theme is None
        assert profile.last_working_dir is None

    def test_from_dict_with_theme(self):
        """Dict with theme sets it."""
        profile = UserProfile.from_dict({"theme": "gruvbox"})
        assert profile.theme == "gruvbox"

    def test_from_dict_with_all_values(self):
        """Dict with all values sets everything."""
        profile = UserProfile.from_dict({
            "theme": "monokai",
            "last_working_dir": "/tmp/test",
        })
        assert profile.theme == "monokai"
        assert profile.last_working_dir == Path("/tmp/test")


class TestProfileManager:
    """Tests for ProfileManager."""

    def test_profile_defaults(self, tmp_path):
        """Default profile has expected values."""
        manager = ProfileManager(profile_dir=tmp_path)
        assert manager.profile.theme is None
        assert manager.profile.last_working_dir is None

    def test_save_and_load_profile(self, tmp_path):
        """Profile can be saved and loaded."""
        manager = ProfileManager(profile_dir=tmp_path)
        profile = UserProfile(theme="nord")
        manager.save_profile(profile)

        # Create new manager to load from disk
        manager2 = ProfileManager(profile_dir=tmp_path)
        assert manager2.profile.theme == "nord"

    def test_update_theme(self, tmp_path):
        """Theme can be updated."""
        manager = ProfileManager(profile_dir=tmp_path)
        manager.update_theme("catppuccin-mocha")

        # Verify persisted
        manager2 = ProfileManager(profile_dir=tmp_path)
        assert manager2.profile.theme == "catppuccin-mocha"

    def test_update_last_working_dir(self, tmp_path):
        """Last working dir can be updated."""
        manager = ProfileManager(profile_dir=tmp_path)
        manager.update_last_working_dir(Path("/home/user/projects"))

        # Verify persisted
        manager2 = ProfileManager(profile_dir=tmp_path)
        assert manager2.profile.last_working_dir == Path("/home/user/projects")

    def test_profile_file_location(self, tmp_path):
        """Profile is saved to .profile file in profile dir."""
        manager = ProfileManager(profile_dir=tmp_path)
        manager.update_theme("tokyo-night")

        # Verify file exists at expected location
        profile_file = tmp_path / ".profile"
        assert profile_file.exists()

    def test_creates_profile_dir(self, tmp_path):
        """Profile directory is created if it doesn't exist."""
        profile_dir = tmp_path / "nested" / "zen_portal"
        manager = ProfileManager(profile_dir=profile_dir)
        manager.update_theme("dracula")

        assert profile_dir.exists()
        assert (profile_dir / ".profile").exists()

    def test_handles_corrupt_profile(self, tmp_path):
        """Corrupt profile file is handled gracefully."""
        profile_file = tmp_path / ".profile"
        profile_file.write_text("not valid json {")

        manager = ProfileManager(profile_dir=tmp_path)
        # Should return default profile instead of crashing
        assert manager.profile.theme is None
