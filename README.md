# Zen Portal

A contemplative multi-session Claude Code manager built with Textual.

## Features

- **Multi-session management** - Run multiple Claude Code sessions simultaneously
- **Progressive disclosure** - See session list, focus on one, or attach directly to tmux
- **Vim-style navigation** - j/k navigation, familiar keyboard-first interface
- **Security-first** - Input validation, session limits, resource protection
- **Garden metaphor** - Sessions are plants that sprout, grow, bloom, or wilt
- **3-tier feature system** - Config, portal, and session-level settings override cascade

## Quick Start

```bash
cd thoughts/prototypes/zen-portal
uv run python -m zen_portal.app
```

## Key Bindings

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `Enter` | Focus on session (full output) |
| `n` | New session |
| `p` | Prune (kill) session |
| `a` | Attach to tmux (leaves TUI) |
| `r` | Refresh |
| `?` | Help |
| `q` | Quit |

## Session States

| Glyph | State | Meaning |
|-------|-------|---------|
| `.` | SPROUTING | Starting |
| `*` | GROWING | Running |
| `+` | BLOOMED | Completed successfully |
| `-` | WILTED | Error or killed |
| `~` | DORMANT | Paused |

## Architecture

```
zen_portal/
├── app.py                  # Main Textual App
├── models/
│   ├── session.py          # Session dataclass + states
│   └── events.py           # Custom Textual messages
├── services/
│   ├── tmux.py             # Low-level tmux operations
│   ├── session_manager.py  # Business logic + limits
│   └── validation.py       # Input security validation
├── widgets/
│   ├── session_list.py     # Session list with selection
│   └── output_view.py      # Output streaming display
├── screens/
│   ├── main.py             # Main split view
│   ├── focus.py            # Full-screen output
│   └── new_session.py      # New session modal
└── tests/                  # 68 unit tests
```

## Security

- **Session limits**: Max 10 total, 5 active
- **Input validation**: Rejects command injection patterns
- **Subprocess safety**: Uses list args, not shell=True
- **History clearing**: Clears tmux history on prune

See `research/SECURITY_ANALYSIS.md` for threat model.

## 3-Tier Feature System

Settings cascade through three levels, with each level overriding the previous:

### Level 1: Config (`~/.config/zen-portal/config.json`)
Global defaults that rarely change.
```json
{
  "exit_behavior": "ask",
  "features": {
    "working_dir": "/Users/me/projects",
    "model": "sonnet",
    "session_prefix": "zen"
  }
}
```

### Level 2: Portal State (`~/.config/zen-portal/portal.json`)
Current project context. Survives restarts, cleared when switching projects.
```json
{
  "features": {
    "working_dir": "/Users/me/projects/zen-portal",
    "model": "opus"
  },
  "description": "Working on zen-portal"
}
```

### Level 3: Session Override (per-session)
Specified when creating a new session via the "n" key modal.
- Override working directory for this specific session
- Override model for this session

### Resolution Order

```
session > portal > config > system defaults
```

If a session specifies `model: haiku`, it wins. If not, portal is checked.
If portal doesn't specify, config is checked. If nothing specifies,
system defaults apply (cwd for working_dir, "zen" for session_prefix).

## Testing

```bash
# Run all tests
uv run python -m pytest zen_portal/tests/ -v

# With coverage
uv run python -m pytest zen_portal/tests/ --cov=zen_portal
```

## Documentation

See `research/` for detailed research and design docs:
- `TUI_PATTERNS.md` - TUI best practices from k9s, lazygit, etc.
- `DESIGN_EXPLORATION.md` - Design alternatives explored
- `SECURITY_ANALYSIS.md` - Threat model and mitigations
- `ARCHITECTURE_PROPOSAL.md` - Full architecture spec
