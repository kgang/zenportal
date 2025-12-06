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
│   ├── events.py          # Custom Textual messages
│   └── new_session.py     # Data models for new session modal
├── services/              # Business logic (no UI)
│   ├── session_manager.py # Core lifecycle (create, revive, pause, kill)
│   ├── session_persistence.py # State loading/saving
│   ├── session_commands.py # Command building for session types
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
│   ├── session_type_dropdown.py # Collapsible session type selector
│   ├── path_input.py      # Validated path input
│   └── status.py
├── screens/               # Modal dialogs and full screens
│   ├── main.py            # Primary interface
│   ├── main_actions.py    # MainScreen action handlers (mixin)
│   ├── new_session.py     # Create/attach/resume modal
│   ├── new_session_lists.py # Attach/resume list builders
│   ├── attach_session.py  # Attach to external tmux session
│   ├── rename_modal.py    # Rename session modal
│   ├── worktrees.py       # Git worktree management
│   ├── insert_modal.py    # Send keystrokes
│   ├── config_screen.py   # Configuration UI
│   ├── exit_modal.py      # Quit confirmation modal
│   └── help.py            # Keybindings display
└── tests/                 # pytest + pytest-asyncio
```

## Module Organization

Files are kept under ~500 lines for progressive disclosure in AI-assisted development:

| Core Module | Supporting Modules |
|-------------|-------------------|
| `session_manager.py` | `session_persistence.py`, `session_commands.py` |
| `main.py` | `main_actions.py` |
| `new_session.py` | `new_session_lists.py`, `models/new_session.py` |
| `config_screen.py` | `widgets/session_type_dropdown.py`, `widgets/path_input.py` |

## Core Concepts

### Session Types
- `CLAUDE` - Claude Code AI assistant
- `CODEX` - OpenAI Codex CLI
- `GEMINI` - Google Gemini CLI
- `SHELL` - Plain zsh shell
- `OPENROUTER` - OpenRouter via orchat (400+ AI models)

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

Key settings: `exit_behavior`, `working_dir`, `model`, `worktree.*`, `enabled_session_types`

## Key Patterns

### Session Lifecycle
1. Creation → tmux spawned → `SessionCreated` event
2. Running → polling detects state
3. Completion → auto-detected → `SessionStateChanged`
4. Paused/Killed → user action → cleanup
5. Revive FAILED → starts fresh (no --resume); Revive COMPLETED → resumes session

### State Persistence
- State: `~/.zen_portal/state.json`
- History: `~/.zen_portal/history/YYYY-MM-DD.jsonl`
- Sessions survive restarts if tmux/worktree exists

### Polling & Detection
- Interval: 1 second (`MainScreen._poll_sessions`)
- Grace period: 5 seconds after revival
- Exit code detection: Non-zero exit → `FAILED` with error message; zero exit → `COMPLETED`

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
| j/k | Navigate up/down |
| h/l | Focus left/right panel |
| f | Toggle focus between panels |
| n | New session |
| p | Pause (preserve worktree) |
| x | Kill (remove worktree) |
| d | Clean (remove from list) |
| a | Attach to tmux |
| v | Revive completed session |
| e | Rename session |
| i | Insert mode (send keys) |
| c | Config screen |
| ? | Help |
| q | Quit |

## Keybinding Invariants

These patterns MUST be followed consistently across all screens:

| Key | Semantic | Context |
|-----|----------|---------|
| j/k | Vertical navigation (down/up) | Lists, items within containers |
| h/l | Horizontal navigation (left/right) | Panels, sections, tabs |
| f | Focus/expand toggle | Dropdowns, collapsibles, panel focus |
| Enter/Space | Select/toggle | Buttons, checkboxes, options |
| Esc | Cancel/close/collapse | Modals, dropdowns, cancel actions |
| Tab | Next section | Form navigation (fallback for h/l) |

**Dropdown/Collapsible behavior:**
- `f`, `Enter`, or `Space` on header → expand/collapse
- `h` or `Esc` inside expanded → collapse and return focus to header
- `j/k` inside expanded → navigate items
- Checkbox toggle via `Enter` or `Space`

**Panel navigation:**
- `h` → focus left panel
- `l` → focus right panel
- `f` → toggle between panels (if no expandable focused)

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
2. Add to `NewSessionType` enum in `models/new_session.py`
3. Add binary to `BINARY_MAP` in `services/session_commands.py`
4. Add create/revive command cases in `session_commands.py`
5. Add to `ALL_SESSION_TYPES` in `services/config.py`
6. Add type mapping in `screens/main.py` (`action_new_session`)
7. Add prefix in `widgets/session_list.py`
8. Update AI type checks in `screens/new_session.py`

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

**Info panel display format:**
```
tokens  12.5k  (8.2k↓ 4.3k↑)
cache   2.1k read / 0.5k write
```
- ↓ = input tokens, ↑ = output tokens
- Cache line only shown when cache tokens > 0

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
- OpenRouter: `or:`

**Info view:** Compact single-line format for git/tokens/model/repo (repo shown for worktree sessions)

## Session Type Filtering

Users can enable/disable session types via settings (`c` key):

- **Config key:** `features.enabled_session_types` (list of strings or null)
- **Values:** `["claude", "codex", "gemini", "shell", "openrouter"]`
- **Default:** `null` (all types enabled)
- **Effect:** Disabled types hidden from new session modal type selector
- **UI:** `SessionTypeDropdown` widget in config_screen.py - collapsible with checkboxes

## y-router Proxy

Route Claude Code through OpenRouter via [y-router](https://github.com/luohy15/y-router) for alternative models:

- **Config location:** `features.openrouter_proxy` in `~/.config/zen-portal/config.json`
- **Settings:**
  - `enabled: bool` - Enable/disable proxy routing
  - `base_url: str` - Proxy URL (default: `http://localhost:8787`)
  - `api_key: str` - OpenRouter API key (or set `OPENROUTER_API_KEY` env var)
  - `default_model: str` - Model override (e.g., `anthropic/claude-sonnet-4`)
- **UI:** Collapsible section in settings (`c` key)
- **Effect:** Sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_MODEL` for Claude sessions
- **Setup:** Run y-router locally: `git clone https://github.com/luohy15/y-router && cd y-router && docker-compose up -d`

## Exit Modal

Safe defaults for quit behavior:
- Default selection is "Keep running" (not "Kill all")
- Options: Keep running → Kill all → Cancel
- "Remember choice" checkbox persists to config

## New Session Modal

Three-tab modal for session management (new/attach/resume):

**Keybindings:**
- `h`/`l` - Navigate between tabs (works everywhere)
- `^t` - Cycle tabs (works even in input fields)
- `j`/`k` - Navigate lists in attach/resume tabs; cycle type selector when focused
- `f` - Focus/expand: type dropdown, directory browser toggle, advanced collapsible
- `Space` - Select item in attach/resume tabs
- `Enter` - Confirm selection
- `Esc` - Cancel

**Shell session features:**
- Shell sessions can use worktrees (separate `#shell-options` checkbox)
- Worktree checkbox visible when session type is `shell`

**Resume tab features:**
- Shows all recent Claude sessions from `~/.claude/projects/`
- Zen format: `● project-name                    2h` (project first, compact time)
- Sessions known to zen-portal tagged with `●` (cyan), unknown with `○` (dim)
- Validates session file exists before resume; shows error if missing
- Time format: `now`, `5m`, `2h`, `3d`, `2w`

**Reactivity pattern:**
- Lists built once on load (`_build_*_list`)
- Selection uses CSS class toggling (`_update_*_selection`) - O(1) vs O(n) rebuild
- Each row has unique ID (`attach-row-{i}`, `resume-row-{i}`)
