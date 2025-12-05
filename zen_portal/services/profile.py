"""User profile management for Zen Portal.

Stores user preferences in ~/.zen_portal/.profile
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UserProfile:
    """User preferences stored in ~/.zen_portal/.profile."""

    theme: str | None = None
    last_working_dir: Path | None = None

    def to_dict(self) -> dict:
        result: dict = {}
        if self.theme is not None:
            result["theme"] = self.theme
        if self.last_working_dir is not None:
            result["last_working_dir"] = str(self.last_working_dir)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        last_working_dir = Path(data["last_working_dir"]) if data.get("last_working_dir") else None
        return cls(
            theme=data.get("theme"),
            last_working_dir=last_working_dir,
        )


class ProfileManager:
    """Manages user profile stored in ~/.zen_portal/.profile."""

    def __init__(self, profile_dir: Path | None = None):
        if profile_dir is None:
            profile_dir = Path.home() / ".zen_portal"
        self._profile_dir = profile_dir
        self._profile_file = profile_dir / ".profile"
        self._profile: UserProfile | None = None

    @property
    def profile(self) -> UserProfile:
        """Get the user profile, loading from disk if needed."""
        if self._profile is None:
            self._profile = self._load_profile()
        return self._profile

    def _load_profile(self) -> UserProfile:
        """Load profile from disk."""
        if self._profile_file.exists():
            try:
                data = json.loads(self._profile_file.read_text())
                return UserProfile.from_dict(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return UserProfile()

    def save_profile(self, profile: UserProfile) -> None:
        """Save profile to disk."""
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile_file.write_text(json.dumps(profile.to_dict(), indent=2))
        self._profile = profile

    def update_theme(self, theme: str) -> None:
        """Update the theme setting."""
        profile = self.profile
        profile.theme = theme
        self.save_profile(profile)

    def update_last_working_dir(self, path: Path) -> None:
        """Update the last used working directory."""
        profile = self.profile
        profile.last_working_dir = path
        self.save_profile(profile)
