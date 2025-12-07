# HYDRATE.md

> Quick context for Claude Code sessions. Last updated: 2025-12-07 (v0.4.12)

## Essence

**Zenportal** is a contemplative TUI for managing AI assistant sessions in parallel.

```
zen                              # run
uv run pytest zen_portal/tests/  # test
```

Supports Claude Code, OpenAI Codex, Google Gemini CLI, OpenRouter, and shell sessions with git worktree isolation.

---

## Structure

```
zen_portal/
├── app.py                    # entry point
├── models/                   # data: Session, events, enums
├── services/                 # business logic (no UI)
│   ├── session_manager.py    # core lifecycle
│   ├── core/                 # worktree, token, state managers
│   ├── git/                  # GitService
│   ├── openrouter/           # proxy validation, billing, models
│   └── ...                   # tmux, config, state, persistence
├── widgets/                  # reusable UI components
├── screens/                  # modals and full screens
└── tests/
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## Core Concepts

**Session types**: `CLAUDE`, `CODEX`, `GEMINI`, `SHELL`, `OPENROUTER`

**Session states**: `RUNNING` (●), `COMPLETED` (○), `PAUSED` (◐), `FAILED`/`KILLED` (·)

**Config tiers**: session > portal > config > defaults
- Config: `~/.config/zen-portal/config.json`
- Portal: `~/.config/zen-portal/portal.json`
- State: `~/.zen_portal/state.json`

---

## Keybindings

```
j/k     navigate          n    new session
l/space grab mode         p    pause
a       attach tmux       x    kill
v       revive            d    clean
e       rename            c    config
i       insert            /    zen ai
?       help              q    quit
```

**Grab mode**: `l` or `space` to enter, `j/k` reorders, `esc` exits

**Navigation invariants**: `j/k` vertical, `h/l` horizontal, `f` expand, `esc` cancel

---

## Key Patterns

**Lifecycle**: create → running → completed/paused/killed → revive or clean

**Polling**: 1s interval, 5s grace after revival, exit code determines final state

**Events**: `SessionCreated`, `SessionStateChanged`, `SessionPaused`, `SessionKilled`

**Focus model**: MainScreen handles all keys, widgets are `can_focus=False`

**Modals**: inherit `ZenModalScreen`, use `trap_focus=True`, call `yield from super().compose()`

---

## Token Tracking

Parsed from Claude's JSONL at `~/.claude/projects/`.

Display format:
```
tokens  12.5k  (8.2k↓ 4.3k↑)
activity  12 turns · ~1.0k/turn · 15m
cache  2.1k read / 0.5k write (45% hit)
cost  ~$0.32  api
```

Formatting: `1234` → `12.5k` → `1.2M`

---

## Zen AI

Press `/` for quick AI queries with context references:

| ref | expands to |
|-----|------------|
| `@output` | last 100 lines |
| `@error` | recent error |
| `@git` | branch, status, commits |
| `@session` | metadata |
| `@all` | full context |

Example: `why is @error happening?`

---

## Design System

**Modal sizes**: `.modal-sm` (50vw), `.modal-md` (60vw), `.modal-lg` (70vw), `.modal-xl` (80vw)

**Modal anchors**: `.modal-base` (center), `.modal-left` (left-anchored for quick actions)

**Colors**: `$text` primary, `$text-muted` secondary, `$text-disabled` hints

**Session prefixes**: Claude (none), Shell `sh:`, Codex `cx:`, Gemini `gm:`, OpenRouter `or:`

**Elastic modals**: `height: auto; max-height: 90%` on dialog, `min-height: 0` on contents

---

## Eye Strain Reduction (v0.4.12)

Output view echoes selection to minimize horizontal eye movement:

```
● session-name  ·  active  ·  2h     ← title with glyph/state/age
claude  ·  main ✓  ·  .../project    ← context bar
[output content...]
```

**Key changes**:
- `OutputView.update_session()` - accepts full session context
- Notifications: bottom-left (near session list, was bottom-right)
- Quick modals: `.modal-left` class (rename, insert, zen AI)

---

## Common Tasks

### Add session type
1. `models/session.py` - add to `SessionType` enum
2. `models/new_session.py` - add to `NewSessionType`
3. `services/session_commands.py` - add binary and commands
4. `services/config.py` - add to `ALL_SESSION_TYPES`
5. `screens/main.py` - add type mapping
6. `widgets/session_list.py` - add prefix

### Add keybinding
1. `screens/main.py` - add to `BINDINGS`, implement `action_<name>()`
2. `screens/help.py` - update if visible

### Add config option
1. `services/config.py` - add to dataclass
2. `screens/config_screen.py` - add UI

---

## Constraints

- `MAX_SESSIONS = 10`
- tmux names: `zen-{session_id[:8]}`
- tmux scrollback: 50,000 lines (set at creation)
- Worktrees symlink `.env` files

---

## Notifications

```python
self.zen_notify("session created")           # success
self.zen_notify("no session", "warning")     # warning
self.zen_notify("failed", "error")           # error
```

Style: lowercase, past tense for success, declarative for warnings.

---

## Testing

```bash
uv run pytest zen_portal/tests/ -v
uv run pytest zen_portal/tests/ --cov=zen_portal
```

Tests mock tmux operations. Key test files mirror service/widget structure.
