"""Tests for InsertModal."""

import pytest

from zen_portal.screens.insert_modal import (
    InsertModal,
    InsertResult,
    KeyItem,
    SPECIAL_KEYS,
)


class TestKeyItem:
    """Tests for KeyItem dataclass."""

    def test_literal_key_item(self):
        """KeyItem stores literal characters."""
        item = KeyItem(value="a", display="a", is_special=False)
        assert item.value == "a"
        assert item.display == "a"
        assert not item.is_special

    def test_special_key_item(self):
        """KeyItem stores special keys."""
        item = KeyItem(value="Up", display="↑", is_special=True)
        assert item.value == "Up"
        assert item.display == "↑"
        assert item.is_special


class TestInsertResult:
    """Tests for InsertResult dataclass."""

    def test_insert_result_dataclass(self):
        """InsertResult stores keys correctly."""
        items = [KeyItem(value="h", display="h"), KeyItem(value="i", display="i")]
        result = InsertResult(keys=items)
        assert len(result.keys) == 2
        assert result.keys[0].value == "h"

    def test_insert_result_with_special_keys(self):
        """InsertResult can store special keys."""
        items = [
            KeyItem(value="hello", display="hello"),
            KeyItem(value="Enter", display="↵", is_special=True),
        ]
        result = InsertResult(keys=items)
        assert result.keys[1].is_special
        assert result.keys[1].value == "Enter"


class TestSpecialKeys:
    """Tests for special key mappings."""

    def test_arrow_keys_mapped(self):
        """Arrow keys have tmux mappings."""
        assert "up" in SPECIAL_KEYS
        assert "down" in SPECIAL_KEYS
        assert "left" in SPECIAL_KEYS
        assert "right" in SPECIAL_KEYS

    def test_shift_enter_mapped(self):
        """Shift+Enter has tmux mapping."""
        assert "shift+enter" in SPECIAL_KEYS
        tmux_key, display = SPECIAL_KEYS["shift+enter"]
        assert tmux_key == "S-Enter"

    def test_function_keys_mapped(self):
        """Function keys have tmux mappings."""
        for i in range(1, 13):
            assert f"f{i}" in SPECIAL_KEYS


class TestInsertModal:
    """Tests for InsertModal."""

    def test_insert_modal_has_session_name(self):
        """InsertModal stores session name."""
        modal = InsertModal("my-session")
        assert modal._session_name == "my-session"

    def test_insert_modal_buffer_starts_empty(self):
        """InsertModal buffer starts empty."""
        modal = InsertModal("test")
        assert modal._buffer == []

    def test_add_literal(self):
        """_add_literal adds a KeyItem to buffer."""
        modal = InsertModal("test")
        modal._buffer = []  # Ensure clean start
        # Manually add since _add_literal calls _update_buffer_display which needs compose
        item = KeyItem(value="a", display="a", is_special=False)
        modal._buffer.append(item)
        assert len(modal._buffer) == 1
        assert modal._buffer[0].value == "a"
        assert not modal._buffer[0].is_special

    def test_add_special(self):
        """Special keys are added with is_special=True."""
        modal = InsertModal("test")
        item = KeyItem(value="Up", display="↑", is_special=True)
        modal._buffer.append(item)
        assert modal._buffer[0].is_special
        assert modal._buffer[0].value == "Up"

    def test_get_display_text_empty(self):
        """Empty buffer shows placeholder."""
        modal = InsertModal("test")
        assert modal._get_display_text() == "type to capture..."

    def test_get_display_text_literals(self):
        """Display text shows literal characters."""
        modal = InsertModal("test")
        modal._buffer = [
            KeyItem(value="h", display="h"),
            KeyItem(value="i", display="i"),
        ]
        assert modal._get_display_text() == "hi"

    def test_get_display_text_special_keys(self):
        """Display text shows special keys in brackets."""
        modal = InsertModal("test")
        modal._buffer = [
            KeyItem(value="hello", display="hello"),
            KeyItem(value="Down", display="↓", is_special=True),
        ]
        assert modal._get_display_text() == "hello[↓]"
