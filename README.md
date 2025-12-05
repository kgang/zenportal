# Zen Portal

A contemplative multi-session AI assistant manager built with Textual.

Manage Claude Code, Codex, Gemini CLI, and shell sessions simultaneously in a clean terminal UI.

## Features

- **Multi-shell support** - Claude Code, OpenAI Codex, Google Gemini CLI, plain shell
- **Multi-session management** - Run multiple sessions simultaneously
- **Git worktree integration** - Isolated worktrees per session for parallel development
- **Vim-style navigation** - j/k navigation, familiar keyboard-first interface
- **Session persistence** - Sessions survive restarts if tmux/worktree exists
- **Insert mode** - Send keystrokes directly to sessions (Ctrl+C, arrows, etc.)
- **3-tier feature system** - Config, portal, and session-level settings

## Installation

```bash
# With uv (recommended)
uv tool install zen-portal

# Or with pip
pip install zen-portal
```

## Quick Start

```bash
# Run zen portal
zen

# Or the long form
zen-portal
```

## Key Bindings

| Key | Action |
|-----|--------|
| `j` / `k` | Move up/down |
| `n` | New session |
| `a` | Attach to tmux |
| `i` | Insert mode (send keys) |
| `R` | Rename session |
| `v` | Revive session |
| `p` | Pause session |
| `x` | Kill session |
| `d` | Clean session |
| `r` | Refresh output |
| `Ctrl+i` | Toggle info panel |
| `?` | Help |
| `q` | Quit |

## Session States

| Glyph | State | Meaning |
|-------|-------|---------|
| `●` | RUNNING | Active tmux session |
| `○` | COMPLETED | Process finished |
| `·` | FAILED | Failed to start |
| `◐` | PAUSED | Paused (worktree preserved) |
| `·` | KILLED | Killed (worktree removed) |

## Session Types

- **Claude** - Claude Code AI assistant
- **Codex** - OpenAI Codex CLI
- **Gemini** - Google Gemini CLI
- **Shell** - Plain shell session

## Configuration

Settings cascade through three levels:

### Level 1: Config (`~/.config/zen-portal/config.json`)
```json
{
  "features": {
    "working_dir": "/path/to/default",
    "model": "sonnet",
    "session_prefix": "zen"
  }
}
```

### Level 2: Portal State (`~/.config/zen-portal/portal.json`)
```json
{
  "features": {
    "working_dir": "/path/to/current/project"
  }
}
```

### Level 3: Session Override
Specified when creating a session via the `n` key modal.

Resolution order: `session > portal > config > defaults`

## Git Worktree Integration

Enable isolated worktrees per session:

```json
{
  "worktree": {
    "enabled": true,
    "default_from_branch": "main",
    "env_files": [".env", ".env.local"]
  }
}
```

Sessions with worktrees get their own branch and symlinked env files.

## Development

```bash
# Clone and install
git clone https://github.com/yourusername/zen-portal
cd zen-portal
uv sync

# Run from source
uv run python -m zen_portal.app

# Run tests
uv run pytest zen_portal/tests/ -v

# With coverage
uv run pytest zen_portal/tests/ --cov=zen_portal
```

## Architecture

```
zen_portal/
├── app.py                  # Main Textual App
├── models/
│   ├── session.py          # Session dataclass + states
│   └── events.py           # Custom Textual messages
├── services/
│   ├── session_manager.py  # Core business logic
│   ├── tmux.py             # Low-level tmux operations
│   ├── worktree.py         # Git worktree management
│   ├── config.py           # 3-tier config resolution
│   ├── state.py            # Session persistence
│   └── discovery.py        # Claude session discovery
├── widgets/                # Textual widgets
├── screens/                # Textual screens
└── tests/                  # Unit tests
```

## License

MIT
