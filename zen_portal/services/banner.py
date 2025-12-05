"""Banner generation for session identification."""

import hashlib


# Box drawing characters for borders
GLYPHS = {
    "top_left": "╭",
    "top_right": "╮",
    "bottom_left": "╰",
    "bottom_right": "╯",
    "horizontal": "─",
    "vertical": "│",
}

# Zen-themed decorative patterns
PATTERNS = [
    "· · ·",
    "~ ~ ~",
    "* * *",
    "○ ○ ○",
    "◦ ◦ ◦",
    "· ~ ·",
    "* · *",
    "~ · ~",
]

# Subtle accent colors (ANSI 256-color codes, muted tones)
COLORS = [
    "\033[38;5;109m",  # muted cyan
    "\033[38;5;139m",  # muted purple
    "\033[38;5;144m",  # muted olive
    "\033[38;5;138m",  # muted rose
    "\033[38;5;108m",  # muted green
    "\033[38;5;146m",  # muted blue
    "\033[38;5;181m",  # muted pink
    "\033[38;5;187m",  # muted cream
]

RESET = "\033[0m"
DIM = "\033[2m"


def _hash_to_index(seed: str, options: list) -> int:
    """Convert a string seed to a deterministic index."""
    h = hashlib.md5(seed.encode()).hexdigest()
    return int(h[:8], 16) % len(options)


def generate_banner(session_name: str, session_id: str) -> str:
    """Generate a procedural banner for a session.

    The banner is deterministic based on the session ID, so the same
    session always gets the same visual identity.

    Args:
        session_name: Display name for the session
        session_id: Unique session ID for procedural generation

    Returns:
        A multi-line string containing the banner
    """
    # Use session_id for deterministic selection
    pattern = PATTERNS[_hash_to_index(session_id + "pattern", PATTERNS)]
    color = COLORS[_hash_to_index(session_id + "color", COLORS)]

    # Build the banner
    width = max(40, len(session_name) + 8)
    inner_width = width - 2

    # Top pattern line
    pattern_line = f"{pattern:^{inner_width}}"

    # Session name centered
    name_line = f"{session_name:^{inner_width}}"

    # Short ID for reference
    short_id = session_id[:8]
    id_line = f"{short_id:^{inner_width}}"

    # Build the box
    top = GLYPHS["top_left"] + GLYPHS["horizontal"] * inner_width + GLYPHS["top_right"]
    bottom = GLYPHS["bottom_left"] + GLYPHS["horizontal"] * inner_width + GLYPHS["bottom_right"]

    lines = [
        "",
        f"{color}{DIM}{top}{RESET}",
        f"{color}{DIM}{GLYPHS['vertical']}{RESET}{pattern_line}{color}{DIM}{GLYPHS['vertical']}{RESET}",
        f"{color}{DIM}{GLYPHS['vertical']}{RESET}{color}{name_line}{RESET}{color}{DIM}{GLYPHS['vertical']}{RESET}",
        f"{color}{DIM}{GLYPHS['vertical']}{id_line}{GLYPHS['vertical']}{RESET}",
        f"{color}{DIM}{bottom}{RESET}",
        "",
    ]

    return "\n".join(lines)


def generate_banner_command(session_name: str, session_id: str) -> str:
    """Generate a shell command that prints the banner.

    This is safe to pass to bash -c or include in a script.

    Args:
        session_name: Display name for the session
        session_id: Unique session ID for procedural generation

    Returns:
        A shell command string that prints the banner
    """
    banner = generate_banner(session_name, session_id)
    # Escape for shell (single quotes, escape existing single quotes)
    escaped = banner.replace("'", "'\"'\"'")
    return f"printf '%s\\n' '{escaped}'"
