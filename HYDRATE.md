# HYDRATE.md - Claude Code Context Document

> Quick context for future Claude Code sessions working on this codebase.
> Last updated: 2025-12-07 (v0.4.8) - Fix R restart to use os.execv for fresh code.

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
├── styles/
│   └── base.py            # Shared CSS tokens and modal base styles
├── models/
│   ├── session.py         # Session dataclass + enums (SessionType, SessionState)
│   ├── events.py          # Custom Textual messages
│   └── new_session.py     # Data models for new session modal
├── services/              # Business logic (no UI)
│   ├── session_manager.py # Core lifecycle (create, revive, pause, kill) - 624 lines
│   ├── core/              # Extracted managers from SessionManager
│   │   ├── worktree_manager.py  # Git worktree setup/cleanup
│   │   ├── token_manager.py     # Claude token statistics
│   │   └── state_refresher.py   # Session state polling
│   ├── git/               # Unified git operations
│   │   └── git_service.py       # GitService: branch, status, log, repo info
│   ├── openrouter/        # OpenRouter integration package
│   │   ├── validation.py        # Proxy connectivity/credential checks
│   │   ├── monitor.py           # Real-time proxy monitoring
│   │   ├── billing.py           # Usage and cost tracking
│   │   └── models.py            # Fetch/cache model list
│   ├── session_persistence.py # State loading/saving
│   ├── session_commands.py # Command building for session types
│   ├── notification.py    # Centralized notification service
│   ├── zen_ai.py          # Lightweight AI invocation (claude -p / OpenRouter)
│   ├── context_parser.py  # @ref syntax parsing for AI context (uses GitService)
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
│   ├── zen_dropdown.py    # Base class for collapsible dropdowns (j/k/h/l/f nav)
│   ├── session_list.py    # Session list with selection
│   ├── output_view.py     # Session output display
│   ├── session_info.py    # Metadata panel (uses GitService)
│   ├── proxy_status.py    # Real-time proxy monitoring widget
│   ├── notification.py    # Zen-styled notification widget
│   ├── model_selector.py  # Autocomplete model selector for OpenRouter
│   ├── directory_browser.py
│   ├── session_type_dropdown.py # Extends ZenDropdown
│   ├── zen_ai_dropdown.py # Extends ZenDropdown
│   ├── path_input.py      # Validated path input
│   ├── zen_mirror.py      # Context-aware AI companion panel
│   └── status.py
├── screens/               # Modal dialogs and full screens
│   ├── base.py            # ZenScreen + ZenModalScreen base classes
│   ├── main.py            # Primary interface
│   ├── main_actions.py    # MainScreen action handlers (mixin)
│   ├── new_session/       # New session modal package (555 lines total)
│   │   ├── __init__.py          # Re-exports NewSessionModal
│   │   ├── css.py               # Extracted modal CSS
│   │   └── billing_widget.py    # Billing mode selector widget
│   ├── new_session_modal.py     # Create/attach/resume modal (main class)
│   ├── new_session_lists.py     # Attach/resume list builders
│   ├── attach_session.py  # Attach to external tmux session
│   ├── rename_modal.py    # Rename session modal (extends ZenModalScreen)
│   ├── worktrees.py       # Git worktree management
│   ├── insert_modal.py    # Send keystrokes
│   ├── config_screen.py   # Configuration UI
│   ├── exit_modal.py      # Quit confirmation modal
│   ├── zen_prompt.py      # Zen AI quick query modal
│   └── help.py            # Keybindings display
└── tests/                 # pytest + pytest-asyncio
```

## Recent Enhancements (v0.3.x - v0.4.x)

| Feature | Files | Key |
|---------|-------|-----|
| **Zen AI** | `zen_ai.py`, `context_parser.py`, `zen_prompt.py`, `zen_ai_dropdown.py` | `/` |
| Textual 6.x Upgrade | `pyproject.toml`, all modals | - |
| Modal Focus Trapping | all `screens/*.py` modals | `trap_focus=True` |
| Flat Cancel Buttons | `exit_modal.py`, `config_screen.py` | `.flat` CSS class |
| Output Search | `output_view.py` | `Ctrl+F` |
| Token Sparklines | `session_info.py`, `token_parser.py` | `Ctrl+I` (info mode) |
| Proxy Monitoring | `proxy_monitor.py`, `billing_tracker.py` | `P` (dashboard) |

See feature-specific sections below for details.

## Module Organization

Files are kept under ~500 lines for progressive disclosure in AI-assisted development:

| Core Module | Supporting Modules | Lines |
|-------------|-------------------|-------|
| `session_manager.py` | `core/{worktree,token,state}_manager.py` | 624 |
| `main.py` | `main_actions.py` | 529 |
| `new_session_modal.py` | `new_session/{css,billing_widget}.py` | 555 |
| `config_screen.py` | `widgets/{session_type,zen_ai}_dropdown.py` | 547 |

**Base classes for code reuse:**
- `ZenDropdown` - Collapsible dropdown with j/k/h/l/f navigation
- `ZenModalScreen` - Modal with focus trapping, escape handling, notifications
- `GitService` - Unified git operations (branch, status, log, repo info)

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

- **textual >= 6.7.0** - TUI framework
- **rich >= 14.0.0** - Terminal formatting
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

### tmux Scrollback
- History limit: 50,000 lines (set via global `history-limit` BEFORE session creation)
- **Critical**: history-limit is fixed at pane creation time, cannot be changed after
- Standard tmux scrolling works: `Ctrl+B [` enters copy mode, then j/k/PgUp/PgDn
- The 100-line `capture_pane` is only for zen-portal's output view widget, not the actual scrollback
- Scrollback preserved when attaching via `a` key or external `tmux attach`
- Sessions use `bash -l -c` (login shell) for proper terminal environment with TUI apps
- Adopted sessions get `remain-on-exit` configured but inherit existing scrollback limit

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

All interactions happen through the session list - no panel focus switching needed.

| Key | Action |
|-----|--------|
| j/k | Navigate up/down (reorder in grab mode) |
| l/space | Toggle grab mode |
| esc | Exit grab mode |
| n | New session |
| p | Pause (preserve worktree) |
| x | Kill (remove worktree) |
| d | Clean (remove from list) |
| a | Attach to tmux |
| v | Revive completed session |
| e | Rename session |
| i | Insert mode (send keys) |
| c | Config screen |
| P | Proxy dashboard |
| Ctrl+F | Search output |
| Ctrl+I | Toggle info mode |
| / | Zen AI prompt |
| ? | Help |
| q | Quit |
| R | Restart (clears cache) |

## Grab Mode (Session Reordering)

Allows reordering sessions in the list. Order is persisted.

**Entering grab mode:**
- Press `space` or `l`

**Visual indicators:**
- Title changes to "≡ reorder" (cyan)
- Selected session shows border outline

**In grab mode:**
- `j/k` moves the session up/down in the list
- `space`, `l`, or `esc` exits grab mode and saves order

**Persistence:**
- Order stored in `~/.zen_portal/state.json` as `session_order` array
- New sessions appear at top (not in saved order yet)
- Polling is paused during grab mode to prevent overwriting user's reordering

## Output Search

Filter-based search within session output (`Ctrl+F`).

**Usage:**
- `Ctrl+F` toggles search input
- Type to filter lines containing query (case-insensitive)
- `Escape` closes search and restores full output

**Implementation:** `widgets/output_view.py` - filter-based (shows matching lines).

## Token Sparkline

Minimal sparkline visualization of token usage over time.

**Components:**
- `Session.token_history` - cumulative token totals at each API call
- `services/token_parser.py` - `get_token_history()` method
- `widgets/session_info.py` - Sparkline widget (Textual built-in)

**Display:**
- 2-line height, muted colors
- Only shows for Claude sessions with >1 history points
- Appears below token stats in info mode (`Ctrl+I`)

## Keybinding Invariants

These patterns MUST be followed consistently across all screens:

| Key | Semantic | Context |
|-----|----------|---------|
| j/k | Vertical navigation (down/up) | Lists, items within containers |
| h/l | Horizontal navigation (left/right) | Tabs, sections in modals |
| f | Expand toggle | Dropdowns, collapsibles |
| Enter/Space | Select/toggle | Buttons, checkboxes, options |
| Esc | Cancel/close/collapse | Modals, dropdowns, cancel actions |
| Tab | Next section | Form navigation (fallback for h/l) |

**Dropdown/Collapsible behavior:**
- `f`, `Enter`, or `Space` on header → expand/collapse
- `h` or `Esc` inside expanded → collapse and return focus to header
- `j/k` inside expanded → navigate items
- Checkbox toggle via `Enter` or `Space`

**Main screen focus model:**
- All widgets are non-focusable (`can_focus=False`)
- All keybindings are handled by MainScreen and delegate to widgets
- This simplifies UX - no focus switching between panels needed

**Focus architecture rules (CRITICAL):**
- Hidden widgets can still steal focus - CSS `display:none` alone is NOT enough
- Any child widget with `can_focus=True` inside a `can_focus=False` parent is a focus leak
- Rule: **visibility AND focusability must be controlled together**
- Pattern for conditional focusable elements (e.g., search input):
  1. Create with `can_focus=False` initially
  2. Set `can_focus=True` only when showing/activating
  3. Set `can_focus=False` before hiding/deactivating
  4. Always call `blur()` before disabling focus
- Modals use `trap_focus=True` to prevent focus escaping to background

## Important Files to Know

| File | Purpose |
|------|---------|
| `services/session_manager.py` | Core session lifecycle logic |
| `services/core/` | Extracted managers (worktree, token, state_refresher) |
| `services/git/git_service.py` | Unified git operations |
| `services/openrouter/` | Proxy validation, monitoring, billing, models |
| `services/tmux.py` | All tmux command wrappers |
| `services/config.py` | 3-tier config resolution |
| `services/token_parser.py` | Parse Claude JSONL for token stats |
| `screens/main.py` | Primary UI with keybindings + proxy monitoring |
| `screens/new_session_modal.py` | Session creation modal + billing settings |
| `screens/base.py` | ZenScreen + ZenModalScreen base classes |
| `screens/config_screen.py` | Settings UI (theme, exit behavior, session types) |
| `widgets/zen_dropdown.py` | Base class for collapsible dropdowns |
| `widgets/session_info.py` | Session metadata with enhanced proxy status + token sparklines |
| `widgets/output_view.py` | Session output display with search functionality |
| `widgets/model_selector.py` | Autocomplete model selector for OpenRouter |
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

Tests use mocked tmux operations. Test files:
- `test_app.py` - App import/instantiation smoke tests
- `test_session_manager.py` - Session lifecycle
- `test_session_commands.py` - Command building, proxy env vars
- `test_proxy_validation.py` - Proxy connectivity/credential checks
- `test_openrouter_models.py` - Model fetching, caching, search
- `test_config.py` - 3-tier config resolution
- `test_tmux.py` - Tmux command wrappers
- `test_worktree.py` - Git worktree operations
- `test_state.py` - State persistence
- `test_validation.py` - Input validation
- `test_banner.py` - Session banners
- `test_profile.py` - User profiles
- `test_insert_modal.py` - Insert mode UI

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
- **Screens** inherit from `ZenScreen` (regular) or `ZenModalScreen` (modals) for notification support
- **Models** are pure data structures
- State is managed reactively via Textual's reactive properties
- **NEVER use `_notifications` as attribute name** - Textual's App uses it internally for toast rack
- **Screen compose pattern**: Call `yield from super().compose()` at end to include notification rack

## Token Tracking

Token usage is parsed from Claude's JSONL session files at `~/.claude/projects/`.

**Key components:**
- `services/token_parser.py` - `TokenParser` parses JSONL, `TokenUsage.estimate_cost()` for pricing
- `models/session.py` - `Session.token_stats`, `Session.uses_proxy`
- `services/state.py` - `SessionRecord.{input_tokens, output_tokens, cache_tokens, uses_proxy}`
- `widgets/session_info.py` - `_render_token_section()` displays tokens

**Info panel display format:**
```
tokens  12.5k  (8.2k↓ 4.3k↑)
cache   2.1k read / 0.5k write
cost    ~$0.32  openrouter        # Only for proxy billing
[sparkline visualization]           # Token history for Claude sessions
```
- ↓ = input tokens, ↑ = output tokens
- Cache line: shown when >1k tokens
- Cost line: shown when `uses_proxy=True`
- Sparkline: Visual token usage history for Claude sessions with 2+ data points

**Token History Visualization:**
- Sparkline widget displays token usage trends over time
- Only shown for Claude sessions with `session.token_history` data
- 2-line height with max/min color highlighting
- Automatically rendered below token information in session info view

**Token formatting:** `1234` (raw) → `12.5k` (thousands) → `1.2M` (millions)

**Cost estimation:**
- `OPENROUTER_PRICING` dict has per-token prices (Dec 2024)
- Supports opus-4, sonnet-4, haiku-4, 3.5-sonnet; defaults to Sonnet

**Data flow:**
1. `refresh_states()` → `update_session_tokens()` for Claude sessions
2. `TokenParser.get_session_stats()` reads Claude's JSONL
3. Stored in `session.token_stats`, persisted via `SessionRecord`
4. Cost displayed when `uses_proxy=True`

## Error Handling

Failed sessions now capture and display error reasons:

- `Session.error_message: str` - Human-readable failure reason
- `tmux.py` validates working directory exists before creating session
- `session_manager.py` validates binary exists (claude, codex, gemini, zsh)
- Error displayed in red in dead session info panel

## Notification System

Custom zen-styled notifications with centralized service via `ZenScreen` base class.

**Components:**
- `services/notification.py` - `NotificationService` + `NotificationRequest` message
- `widgets/notification.py` - `ZenNotification` + `ZenNotificationRack`
- `screens/base.py` - `ZenScreen` base class with notification rack
- CSS in `styles/base.py` - `NOTIFICATION_CSS`

**Architecture:**
- `ZenScreen` base class provides `#notifications` rack via `compose()`
- Screens inherit from `ZenScreen` and call `yield from super().compose()` at end
- Uses `layer: notification` to float above screen content
- `ZenScreen.on_notification_request()` handles events for the screen
- Screens use `zen_notify()` helper which posts `NotificationRequest` message

**Severity levels:**
| Severity | Timeout | Border Color | Text Color |
|----------|---------|--------------|------------|
| SUCCESS | 3s | `$surface-lighten-1` | `$text-muted` |
| WARNING | 4s | `$warning-darken-2` | `$warning` |
| ERROR | 5s | `$error-darken-2` | `$error` |

**Usage in screens:**
```python
# MainScreen has zen_notify() helper
self.zen_notify("session created")
self.zen_notify("no session selected", "warning")
self.zen_notify("could not revive", "error")

# Modals use post_message
self.post_message(self.app.notification_service.warning("enter a name"))
```

**Message format:**
- Lowercase first letter
- Past tense for success: "created", "renamed", "deleted"
- Declarative for warnings: "no session selected"

## New Session Modal Features

- **"set as default dir" checkbox** - In advanced section, saves working directory to portal-level config when checked
- Located in `screens/new_session.py`, calls `config.update_portal_features()`

## Design System (Zen/Minimalist)

### Shared CSS (`zen_portal/styles/base.py`)

Central design tokens imported via `app.py`. All modals use shared classes.

**Modal size tiers (viewport-relative):**
| Class | Width | Min | Max | Use |
|-------|-------|-----|-----|-----|
| `.modal-sm` | 50vw | 40 | 50 | RenameModal, ExitModal |
| `.modal-md` | 60vw | 50 | 65 | InsertModal, HelpScreen |
| `.modal-lg` | 70vw | 60 | 80 | NewSessionModal, ConfigScreen, AttachSessionModal |
| `.modal-xl` | 80vw | 70 | 90 | WorktreesScreen |

**List height tiers:**
| Class | Max Height | Use |
|-------|------------|-----|
| `.list-sm` | 20vh | DirectoryBrowser |
| `.list-md` | 30vh | Modal lists |
| `.list-lg` | 50vh | Large lists |

**Common classes:**
- `.modal-base` - Center alignment for modals
- `.dialog-title` - Centered, muted title
- `.dialog-hint` - Bottom hint text
- `.field-label` - Field labels with margin-top: 1
- `.list-row` - Standard list row with hover/selected states
- `.elastic` - `height: auto; min-height: 0` for content-based sizing
- `.hidden` - `display: none` for toggled visibility
- `.no-scrollbar` - Hide scrollbars (Textual 6.x `scrollbar-visibility`)

**Modal focus trapping (Textual 6.5+):**
- All modals set `self.trap_focus = True` in `on_mount()`
- Prevents focus from escaping to background elements

**Usage pattern:**
```python
def compose(self) -> ComposeResult:
    self.add_class("modal-base", "modal-lg")
    with Vertical(id="dialog"):
        yield Static("title", classes="dialog-title")
        # ... content
        yield Static("hints", classes="dialog-hint")
```

### Visual Patterns

**Color hierarchy:**
- `$text` - Primary content
- `$text-muted` - Secondary labels, titles
- `$text-disabled` - Hints, placeholders
- `$surface-lighten-1` - Selection highlight (standardized)

**Borders:**
- `border: round $surface-lighten-1` for modals/containers
- `border: none` or subtle dividers for main screen panels

**Button variants:** `default`, `error`, `primary`, `success`, `warning` (no `outline`)
- `.flat` class: transparent background, no border (zen aesthetic for secondary actions)

**Elastic modals:**
- Dialog: `height: auto; max-height: 90%; overflow-y: auto`
- Inner containers: `height: auto; min-height: 0` (critical for shrinking)
- Never use fixed max-height values on dialogs
- Collapsible contents inherit elastic sizing from `CONTAINER_CSS`

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

## Session Billing (y-router)

Choose billing mode for Claude sessions in the new session modal:

- **UI:** New session modal → advanced → billing selector
- **Config location:** `features.openrouter_proxy` in `~/.config/zen-portal/config.json`

**Billing modes:**
- `claude account` - Use your Claude subscription (default)
- `openrouter` - Pay-per-token via y-router proxy

**OpenRouter setup:**
```bash
git clone https://github.com/luohy15/y-router && cd y-router && docker-compose up -d
```

**When OpenRouter selected:**
- Status shows "● ready" if API key configured (from input or `OPENROUTER_API_KEY` env)
- API key + model selector with autocomplete inline in advanced section
- Settings persisted to config on session creation

**Model Selector:**
- `widgets/model_selector.py` - Autocomplete input for 400+ OpenRouter models
- `services/openrouter_models.py` - Fetches and caches model list from OpenRouter API
- Cache: `~/.cache/zen-portal/openrouter_models.json` (24h TTL)
- Search: Exact match > prefix > contains > fuzzy (chars in order)
- Display: `provider/model  $prompt/$completion  context-length`
- Keybindings: `j/k` navigate dropdown, `Enter` select, `Esc` close

**Security:**
- All env var values validated before shell injection
- URLs: Only http/https schemes; normalized to prevent obfuscation
- API keys: Alphanumeric + dash/underscore only; shell metacharacters rejected
- Config files saved with 0600 permissions (owner read/write only)
- Prefer env vars (`OPENROUTER_API_KEY`) over storing credentials in config

## Proxy Monitoring System (v0.3.2)

Real-time proxy health monitoring with billing integration:

**Architecture:**
- **`ProxyMonitor`** - Async monitoring service with health checks and billing
- **`BillingTracker`** - OpenRouter API integration for usage and cost tracking
- **`ProxyStatusWidget`** - Reactive UI component with real-time updates

**Health Status Levels:**
- `EXCELLENT` (●) - Fast response, < 200ms
- `GOOD` (●) - Normal operation, < 500ms
- `DEGRADED` (◐) - Slow but working, < 2000ms
- `WARNING` (⚠) - Issues detected but functional
- `ERROR` (⚠) - Not working, connection failed
- `UNKNOWN` (○) - Not tested yet

**Monitoring Features:**
- Continuous health checks (30s interval, 10s when issues detected)
- Response time tracking and performance metrics
- Success rate calculation over 24h window
- OpenRouter account balance and rate limit monitoring
- Session-level proxy status display

**Integration:**
- Main screen initializes monitoring on mount
- Session info view shows enhanced per-session proxy status
- Event-driven status updates via callback system
- Cached billing data (5min TTL) and model pricing (24h TTL)

**Display Formats:**
```
# Session info view
proxy  ● openrouter (claude-sonnet-4.5)    # Active session
proxy  ⚠ openrouter (timeout)              # Connection issue
proxy  claude account                      # Direct billing

# Detailed status (in proxy widget)
● openrouter (12ms) $4.23 remaining        # Full metrics
⚠ openrouter (slow)                        # Performance issue
```

## Zen AI (v0.4.0)

Native AI integration for quick queries without leaving context.

**Invocation:**
- `/` key opens quick prompt modal
- Command palette: "ask ai"

**Context References:**
| Reference | Expands To |
|-----------|------------|
| `@output` | Last 100 lines of session output |
| `@error` | Most recent error message |
| `@git` | Current branch, status, recent commits |
| `@session` | Session metadata (type, state, age, model) |
| `@all` | Full context bundle |

**Example prompts:**
- `why is @error happening?`
- `explain @output`
- `what should I commit based on @git?`

**Architecture:**
- `services/zen_ai.py` - Core AI invocation (claude -p / OpenRouter API)
- `services/context_parser.py` - @ref parsing and context gathering
- `screens/zen_prompt.py` - Quick query modal using Textual workers
- `widgets/zen_ai_dropdown.py` - Config screen settings widget
- `widgets/zen_mirror.py` - Optional context sidebar (future)

**Loading Animation:**
- Zen breathing animation: dots expand/contract (`· · ·` → `· · · ·` → `· · ·` → `· ·`)
- 0.66s interval for contemplative pace
- Uses `set_interval()` timer, stopped on completion/error
- `run_worker()` for non-blocking queries
- `on_worker_state_changed()` handles completion/error

**Backends:**
- **Claude Provider**: Uses `claude -p` subprocess (pipe mode)
- **OpenRouter Provider**: Direct HTTP to OpenRouter API
- Hybrid mode: Claude for Claude models, API for others

**Configuration:**
```json
{
  "features": {
    "zen_ai": {
      "enabled": true,
      "model": "haiku",
      "provider": "claude"
    }
  }
}
```

**Models:** `haiku` (fast, cheap), `sonnet` (balanced), `opus` (deep)

**Config Screen (`c` key):**
- `ZenAIDropdown` widget in settings modal
- Header shows: `▶ zen ai: on · haiku · claude`
- `f` to expand, configure enabled/model/provider
- Settings saved to `~/.config/zen-portal/config.json`

**Graceful Degradation:**
- No API key? Feature hidden
- API error? Notification: "could not reach ai"
- Claude not installed? Falls back gracefully

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

## Future Enhancements (Backlog)

Potential features that build on the grab mode infrastructure:

| Feature | Key | Description | Complexity |
|---------|-----|-------------|------------|
| Duplicate session | `D` | Clone session config to new session | Medium |
| Bulk pause | `P` | Pause all running sessions | Low |
| Bulk clean | `X` | Clean all dead sessions | Low |
| Pin to top | `t` | Pin session to always show at top | Medium |
| Session groups | `g` | Group sessions by project/worktree | High |
| Session tags | `#` | Tag sessions for filtering | High |
| Quick switch | `1-9` | Jump to session by number | Low |

**Design principles for new actions:**
- Single-letter keys for frequent actions
- Uppercase for "heavier" operations (bulk, destructive)
- Modal confirmations for destructive bulk operations
- Consistent with vim idioms (d=delete, p=put/pause, y=yank/duplicate)
