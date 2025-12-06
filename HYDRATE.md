# HYDRATE.md - Claude Code Context Document

> Quick context for future Claude Code sessions working on this codebase.

## What is Zenportal?

A **contemplative TUI for managing multiple AI assistant and shell sessions**. It allows developers to run Claude Code, OpenAI Codex, Google Gemini CLI, and plain shell sessions in parallel with git worktree isolation.

**Key value prop**: Organized, keyboard-first (Vim-style) session management with persistent state across restarts.

## Quick Start

```bash
# Install
uv tool install zen-portal

# Run
zen                           # Short form
zen-portal                    # Long form
uv run python -m zen_portal.app  # From source

# Test
uv run pytest zen_portal/tests/ -v
```

## Project Structure

```
zen_portal/
├── app.py                 # Main Textual app entry point
├── models/
│   ├── session.py         # Session dataclass + enums (SessionType, SessionState)
│   └── events.py          # Custom Textual messages
├── services/              # Business logic (no UI)
│   ├── session_manager.py # Core lifecycle (create, revive, pause, kill)
│   ├── tmux.py            # Low-level tmux commands
│   ├── worktree.py        # Git worktree isolation
│   ├── config.py          # 3-tier config system
│   ├── state.py           # Persistent state (~/.zen_portal/)
│   ├── discovery.py       # Find Claude/tmux sessions
│   ├── profile.py         # User preferences
│   ├── banner.py          # Session visual markers
│   ├── validation.py      # Input validation
│   └── token_parser.py    # Parse Claude JSONL for token usage
├── widgets/               # Reusable UI components
│   ├── session_list.py    # Session list with selection
│   ├── output_view.py     # Session output display
│   ├── session_info.py    # Metadata panel
│   ├── directory_browser.py
│   └── status.py
├── screens/               # Modal dialogs and full screens
│   ├── main.py            # Primary interface
│   ├── new_session.py     # Create/attach/resume modal
│   ├── insert_modal.py    # Send keystrokes
│   ├── config_screen.py   # Configuration UI
│   └── help.py            # Keybindings display
└── tests/                 # pytest + pytest-asyncio
```

## Core Concepts

### Session Types
- `CLAUDE` - Claude Code AI assistant
- `CODEX` - OpenAI Codex CLI
- `GEMINI` - Google Gemini CLI
- `SHELL` - Plain zsh shell

### Session States
- `RUNNING` - Active tmux session
- `COMPLETED` - Process exited normally
- `PAUSED` - Manually paused, worktree preserved
- `KILLED` - Manually killed, worktree removed
- `FAILED` - Failed to start

### State Glyphs
| Glyph | State |
|-------|-------|
| ● | RUNNING |
| ○ | COMPLETED |
| ◐ | PAUSED |
| · | FAILED/KILLED |

## Key Technologies

- **textual >= 0.89.0** - TUI framework
- **rich >= 13.0.0** - Terminal formatting
- **tmux** - Session multiplexing (system dep)
- **git** - Worktree isolation (system dep)
- **Python 3.11+**

## Configuration System (3-Tier)

Resolution order: `session > portal > config > defaults`

1. **Level 1: Config** (`~/.config/zen-portal/config.json`) - Global defaults
2. **Level 2: Portal** (`~/.config/zen-portal/portal.json`) - Current context
3. **Level 3: Session** - Per-session overrides (not persisted)

Key settings: `exit_behavior`, `working_dir`, `model`, `worktree.*`

## Key Patterns

### Session Lifecycle
1. Creation → tmux spawned → `SessionCreated` event
2. Running → polling detects state
3. Completion → auto-detected → `SessionStateChanged`
4. Paused/Killed → user action → cleanup

### State Persistence
- State: `~/.zen_portal/state.json`
- History: `~/.zen_portal/history/YYYY-MM-DD.jsonl`
- Sessions survive restarts if tmux/worktree exists

### Polling & Detection
- Interval: 1 second (`MainScreen._poll_sessions`)
- Grace period: 5 seconds after revival

### Event System (Textual Messages)
```python
SessionCreated(session)
SessionStateChanged(session, old_state)
SessionOutput(session_id, output)
SessionPaused(session_id)
SessionKilled(session_id)
SessionCleaned(session_id)
SessionSelected(session)
```

## Key Keybindings (MainScreen)

| Key | Action |
|-----|--------|
| j/k | Navigate sessions |
| n | New session |
| p | Pause (preserve worktree) |
| x | Kill (remove worktree) |
| d | Clean (remove from list) |
| a | Attach to tmux |
| v | Revive completed session |
| i | Insert mode (send keys) |
| c | Config screen |
| ? | Help |
| q | Quit |

## Important Files to Know

| File | Purpose |
|------|---------|
| `services/session_manager.py` | Core session lifecycle logic |
| `services/tmux.py` | All tmux command wrappers |
| `services/config.py` | 3-tier config resolution |
| `services/token_parser.py` | Parse Claude JSONL for token stats |
| `screens/main.py` | Primary UI with keybindings |
| `screens/new_session.py` | Session creation modal |
| `models/session.py` | Session dataclass + enums |

## Constraints & Limits

- MAX_SESSIONS = 10
- Session names: `{prefix}-{session_id[:8]}` (e.g., "zen-a1b2c3d4")
- Worktrees symlink env files (.env, .env.local)

## Testing

```bash
uv run pytest zen_portal/tests/ -v
uv run pytest zen_portal/tests/ --cov=zen_portal
```

Tests use mocked tmux operations. Key test files:
- `test_session_manager.py`
- `test_config.py`
- `test_tmux.py`
- `test_worktree.py`

## Common Tasks

### Adding a New Session Type
1. Add to `SessionType` enum in `models/session.py`
2. Update `SessionManager.create_session()` command building
3. Add detection logic in `services/discovery.py`

### Adding a New Keybinding
1. Add to `BINDINGS` list in `screens/main.py`
2. Implement action method `action_<name>()`
3. Update help screen if visible binding

### Adding Configuration Option
1. Add to dataclasses in `services/config.py`
2. Update `ConfigManager` merge logic
3. Add UI in `screens/config_screen.py`

## Naming Conventions

- Methods: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Events: `PascalCase` messages

## Architecture Notes

- **Services** have no UI dependencies - can be tested in isolation
- **Widgets** are reusable Textual components
- **Screens** are full views or modals
- **Models** are pure data structures
- State is managed reactively via Textual's reactive properties

## Token Tracking

Token usage is parsed from Claude's JSONL session files at `~/.claude/projects/`.

**Key components:**
- `services/token_parser.py` - `TokenParser` class parses JSONL files
- `models/session.py` - `Session.token_stats: TokenUsage | None`
- `services/state.py` - `SessionRecord.{input_tokens, output_tokens, cache_tokens}`
- `widgets/session_info.py` - Displays tokens in info panel

**Data flow:**
1. `refresh_states()` calls `update_session_tokens()` for Claude sessions
2. `TokenParser.get_session_stats()` reads Claude's JSONL files
3. Token counts stored in `session.token_stats`
4. Persisted to history via `SessionRecord` fields

## Error Handling

Failed sessions now capture and display error reasons:

- `Session.error_message: str` - Human-readable failure reason
- `tmux.py` validates working directory exists before creating session
- `session_manager.py` validates binary exists (claude, codex, gemini, zsh)
- Error displayed in red in dead session info panel

## New Session Modal Features

- **"set as default dir" checkbox** - In advanced section, saves working directory to portal-level config when checked
- Located in `screens/new_session.py`, calls `config.update_portal_features()`

## Design System (Zen/Minimalist)

Recent design pass established consistent visual patterns:

**Color hierarchy:**
- `$text` - Primary content
- `$text-muted` - Secondary labels, titles
- `$text-disabled` - Hints, placeholders
- Semantic colors only for states (green=running, etc.)

**Borders:**
- `border: round $surface-lighten-1` for modals/containers
- `border: none` or subtle dividers for main screen panels
- No heavy/thick borders

**Layout:**
- Main screen: 2:3 ratio (session list : output), subtle vertical divider
- Modals: 45-65 char width, centered
- Consistent padding: 1-2 units

**Session list prefixes:**
- Claude: no prefix
- Shell: `sh:`
- Codex: `cx:`
- Gemini: `gm:`

**Info view:** Compact single-line format for git/tokens/model
