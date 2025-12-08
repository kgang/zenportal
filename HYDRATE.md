# HYDRATE.md

> Quick context for Claude Code sessions. Last updated: 2025-12-07 (v0.3.1 - Phase 1 refactoring)

**Status**: Phase 1 foundation refactoring complete. SessionStateService extracted (thread-safe), Services container for DI, logging infrastructure added. SessionManager reduced 832→636 lines. See ZEN_CODE_DESIGN.md for architecture roadmap.

---

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
├── app.py                    # entry point + Services container (DI)
├── models/                   # data: Session, Template, events, enums
├── services/                 # business logic (no UI)
│   ├── session_manager.py    # core lifecycle (636 lines, refactored)
│   ├── session_state.py      # thread-safe state persistence (NEW)
│   ├── template_manager.py   # template CRUD
│   ├── command_registry.py   # palette commands
│   ├── fuzzy.py              # fuzzy matching
│   ├── core/                 # detection, state_refresher, token_manager, worktree_manager
│   ├── pipelines/            # create.py - composable multi-step operations
│   ├── git/                  # git_service.py
│   ├── openrouter/           # validation, billing, models, monitor
│   ├── conflict.py           # pre-creation conflict detection
│   └── state.py              # persistence dataclasses only
├── widgets/                  # reusable UI components
├── screens/                  # modals and full screens
│   ├── main.py               # MainScreen (uses mixins)
│   ├── main_actions.py       # ActionsMixin, ExitMixin
│   └── main_templates.py     # TemplateMixin, PaletteMixin
└── tests/                    # 294 tests, all passing
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## Core Concepts

**Session types**: `AI` (with provider field), `SHELL`

**AI providers**: `CLAUDE`, `CODEX`, `GEMINI`, `OPENROUTER`

**Session states**: `RUNNING` (▪), not running (▫) - binary indicators

**Config**: `~/.config/zen-portal/config.json`, State: `~/.zen_portal/state.json`
- `enabled_session_types`: `["ai", "shell"]` (types, not providers)

---

## Keybindings

```
j/k     navigate          n    new session
l       move mode         p    pause
a       attach tmux       x    kill
v       revive            d    clean
e       rename            c    config
i       insert            /    zen ai
I       info panel        A    analyze session
C       show completed    S    search output
:       command palette   T    templates
?       help              q    quit
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

**Services Container** (`app.py`): Dependency injection via dataclass.
- `Services.create()` wires up all dependencies
- Clear dependency graph: tmux → state → sessions
- Enables testing with mock injection
- Single source of truth for service lifetime

**State Persistence** (`services/session_state.py`): Thread-safe operations.
- RLock for concurrent access safety
- Atomic file writes (temp + rename)
- Separate from lifecycle (SessionManager)
- JSONL history appends

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

**Mixins** (`screens/main_*.py`): MainScreen uses mixins for organization.
- `MainScreenActionsMixin` - session operations (pause, kill, revive, etc.)
- `MainScreenExitMixin` - exit/cleanup logic
- `MainScreenTemplateMixin` - template management
- `MainScreenPaletteMixin` - command palette
- Pattern keeps main.py focused on UI composition and orchestration

**Logging**: All services use Python logging.
- `logger = logging.getLogger(__name__)`
- No silent failures - all errors logged
- Levels: debug (verbose), warning (recoverable), error (critical)

**Reactive watchers**: Guard against race conditions during DOM updates.
```python
# Pattern: use flag to prevent watcher firing during rebuild
self._updating = True
try:
    results.remove_children()
    for item in items:
        results.mount(item)
finally:
    self._updating = False

def watch_selected_index(self, new_index: int) -> None:
    if self._updating:
        return  # Skip during rebuild
    # Update visual selection
```

**Widget IDs**: NEVER use `id=` for widgets mounted in methods called multiple times.
```python
# ✓ CORRECT - use classes for reusable widgets
container.mount(Static("empty", classes="empty-list"))

# ✗ WRONG - static IDs cause DuplicateIds errors
container.mount(Static("empty", id="empty-list"))
```

---

## Token Tracking

Parsed from Claude's JSONL at `~/.claude/projects/`. Claude AI sessions only.

Key files:
- `services/token_parser.py` - JSONL parsing, `TokenUsage` dataclass
- `services/core/token_manager.py` - session updates, auto-discovery
- `widgets/session_info.py` - display with sparkline visualization

---

## Zen AI

Press `/` for quick AI queries, `A` for instant session analysis. Context is automatically included (session output, errors, git status). Just ask naturally - no @ references needed.

---

## Command Palette

Press `:` or `Ctrl+P` to open. Fuzzy search across all commands with keybinding hints.

Key files:
- `services/command_registry.py` - command definitions
- `services/fuzzy.py` - fuzzy matching
- `screens/command_palette.py` - modal UI

---

## Session Templates

Press `T` to open template picker. Templates save session configurations for quick reuse.

Supports directory placeholders: `$CWD`, `$GIT_ROOT`

Key files:
- `models/template.py` - SessionTemplate dataclass
- `services/template_manager.py` - CRUD + persistence (~/.config/zen-portal/templates.json)
- `screens/template_picker.py` - selection modal
- `screens/template_editor.py` - create/edit form

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
2. `services/command_registry.py` - register command for palette
3. `screens/help.py` - update if visible

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

---

## Refactoring Roadmap

See **ZEN_CODE_DESIGN.md** for comprehensive architecture guide.

**Phase 1 (Foundation) - COMPLETE ✓**
- SessionStateService extracted (thread-safe, 271 lines)
- Services container for DI (app.py)
- Logging infrastructure (no silent failures)
- SessionManager: 832 → 636 lines (-24%)

**Phase 2 (Simplification) - NEXT**
- Consolidate WorktreeService + WorktreeManager (425 → 300 lines)
- Cache widget references (152 DOM queries → ~15)
- Config schema with dataclasses (type-safe)

**Phase 3 (Architecture)**
- Extract validators from screens (business logic → services)
- Exception hierarchy (ZenError base class)
- Event bus for pub/sub (decouple services from UI)

All 294 tests passing. Zen code principles: simplicity, clarity, separation, testability.
