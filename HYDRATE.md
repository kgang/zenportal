# HYDRATE.md

> Quick context for Claude Code sessions. Last updated: 2025-12-07 (v0.5.3 - token metrics fix)

## Essence

**Zenportal** is a contemplative TUI for managing AI assistant sessions in parallel.

```
zen                              # run
uv run pytest zen_portal/tests/  # test
```

Two session types: **AI** (with provider: claude, codex, gemini, openrouter) and **Shell**.

---

## Structure

```
zen_portal/
├── app.py                    # entry point
├── models/                   # data: Session, events, enums
├── services/                 # business logic (no UI)
│   ├── session_manager.py    # core lifecycle
│   ├── pipelines/            # composable multi-step operations
│   ├── conflict.py           # pre-creation conflict detection
│   ├── core/                 # worktree, token, state, detection
│   ├── git/                  # GitService
│   ├── openrouter/           # proxy validation, billing, models
│   └── state.py              # persistence dataclasses only
├── widgets/                  # reusable UI components
├── screens/                  # modals and full screens
└── tests/
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## Core Concepts

**Session types**: `AI` (with provider field), `SHELL`

**Session states**: `RUNNING` (▪), not running (▫) - binary indicators

**Config**: `~/.config/zen-portal/config.json`, State: `~/.zen_portal/state.json`

---

## Keybindings

```
j/k     navigate          n    new session
l       move mode         p    pause
a       attach tmux       x    kill
v       revive            d    clean
e       rename            c    config
i       insert            /    zen ai
I       info panel        S    search output
C       show completed    ?    help
q       quit
```

**Move mode**: `l` to enter, `j/k` reorders, `esc` exits

**Completed sessions**: hidden by default, `C` to toggle visibility

**Navigation invariants**: `j/k` vertical, `h/l` horizontal, `f` expand, `esc` cancel

---

## Key Patterns

**Lifecycle**: create → running → completed/paused/killed → revive or clean

**Polling**: 1s interval, exit code determines final state

**Events**: `SessionCreated`, `SessionStateChanged`, `SessionPaused`, `SessionKilled`

**Focus model**: MainScreen handles all keys, widgets are `can_focus=False`

**Modals**: inherit `ZenModalScreen`, use `trap_focus=True`, call `yield from super().compose()`

---

## Architecture Patterns

**Pipelines** (`services/pipelines/`): Multi-step operations as composable steps.
- Each step: `T → StepResult[U]`
- `CreateSessionPipeline` orchestrates session creation
- Steps: ValidateLimit, ResolveConfig, SetupWorktree, ValidateBinary, SpawnTmux

**Detection** (`services/core/detection.py`): Pure state detection function.
- `detect_session_state(tmux, name) → DetectionResult`
- No side effects, just facts about current state
- `StateRefresher` handles polling, calls detection

**Conflicts** (`services/conflict.py`): Pre-creation warnings.
- `detect_conflicts(name, type, existing, max) → list[SessionConflict]`
- Severities: INFO, WARNING, ERROR
- New session modal shows warnings before creation

---

## Token Tracking

Parsed from Claude's JSONL at `~/.claude/projects/`. Claude AI sessions only.

Key files:
- `services/token_parser.py` - JSONL parsing, `TokenUsage` dataclass
- `services/core/token_manager.py` - session updates, auto-discovery
- `widgets/session_info.py` - display with sparkline visualization

---

## Zen AI

Press `/` for quick AI queries. Context is automatically included (session output, errors, git status). Just ask naturally - no @ references needed.

---

## Design System

**Modal sizes**: `.modal-sm` (50vw), `.modal-md` (60vw), `.modal-lg` (70vw), `.modal-xl` (80vw)

**Modal anchors**: `.modal-base` (center), `.modal-left` (left-anchored for quick actions)

**Colors**: `$text` primary, `$text-muted` secondary, `$text-disabled` hints

**Session display**: No prefixes - clean names only. Type indicated by context.

**Elastic modals**: `height: auto; max-height: 90%` on dialog, `min-height: 0` on contents

---

## Eye Strain Reduction

Output view echoes selection: `▪ session-name  active  2h` in header.
Notifications bottom-left. Quick modals use `.modal-left` class.
Completed sessions hidden by default (less visual clutter).

---

## Info Panel (I key)

Shows detailed session metadata:
- **identifiers**: tmux name (`zen-xxxxx`), zen id, claude session id
- **type**: provider (claude/codex/gemini/openrouter), model
- **directory**: working dir, worktree branch
- **tokens**: input/output/total counts, cache efficiency, turns, sparkline
- **cost**: estimated cost for proxy sessions (~$0.xxx)
- **created**: timestamp

---

## Common Tasks

### Add AI provider
1. `models/session.py` - add provider string option
2. `services/session_commands.py` - add binary and commands for new provider
3. `screens/new_session_modal.py` - add to provider dropdown

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
