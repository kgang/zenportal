# HYDRATE.md - zenportal

> *"To read is to invoke. There is no view from nowhere."*

This document is an AGENTESE coordination surface. Edits disturb the field.

## hydrate.protocol

```
hydrate.project.manifest   → View status (observer-dependent)
hydrate.project.afford     → What can I do? (synergies)
hydrate.project.block      → What blocks me?
hydrate.concept.manifest   → Shared abstractions (patterns, gotchas)
hydrate.void.sip           → Tech debt, tangents
hydrate.time.witness       → git log, recent changes
```

| Action | AGENTESE Analog | Protocol |
|--------|-----------------|----------|
| Update status | `hydrate.project.manifest` | Touch only your section |
| Note dependency | `hydrate.project.block` | Announce blockers |
| Note enablement | `hydrate.project.afford` | Announce what you enable |
| Update shared | `hydrate.concept.refine` | Prefix `[STALE?]` if uncertain |

**Status**: 338 tests | Branch: `main` | Files: 20k lines
################################################################################

## hydrate.project.manifest

**Zenportal** - Contemplative TUI for managing AI assistant sessions in parallel.

```
zen                              # run
uv run pytest zen_portal/tests/  # test
```

**Session types**: AI (claude/codex/gemini/openrouter), Shell
**States**: RUNNING (▪), not running (▫)

---

## hydrate.self.manifest

```
zen_portal/
├── app.py                    # entry + Services container (DI)
├── models/                   # Session, Template, events, enums, exceptions
│   └── exceptions.py         # ZenError hierarchy
├── services/                 # business logic (no UI)
│   ├── session_manager.py    # lifecycle (686 lines)
│   ├── events.py             # EventBus pub/sub (235 lines)
│   ├── session_state.py      # thread-safe persistence
│   ├── validation.py         # SessionValidator, ValidationResult
│   ├── worktree.py           # git worktree
│   ├── config.py             # configuration (dataclass schema)
│   ├── core/                 # detection, state_refresher, token_manager
│   ├── pipelines/            # composable multi-step operations
│   └── openrouter/           # validation, billing, models, monitor
├── widgets/                  # reusable UI components
├── screens/                  # modals and full screens
│   ├── main.py               # MainScreen (uses mixins)
│   └── new_session_modal.py  # session creation (uses SessionValidator)
└── tests/                    # 338 tests
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## hydrate.concept.manifest

**Zen Principles**: 簡素 Kanso (Simplicity) • 明快 Meikai (Clarity) • 分離 Bunri (Separation) • 空 Kū (Emptiness) • 検証 Kenshō (Verification)

**Architecture Patterns**:
- **Services Container** (`app.py`): DI via dataclass, `Services.create()` wires deps
- **EventBus** (`services/events.py`): Typed pub/sub, SessionManager emits domain events
- **UI Subscriptions**: MainScreen subscribes to `SessionCreatedEvent`, `SessionPausedEvent`, `SessionKilledEvent`, `SessionCleanedEvent` for reactive updates
- **Exception Hierarchy** (`models/exceptions.py`): `ZenError` base, specific subclasses
- **Validation** (`services/validation.py`): `SessionValidator`, `ValidationResult`
- **State Persistence** (`session_state.py`): RLock, atomic writes, cursor position, JSONL history
- **Pipelines** (`pipelines/`): Composable steps, `T → StepResult[U]`
- **Mixins** (`screens/main_*.py`): MainScreen organization
- **Widget Caching**: Lazy properties for frequently-accessed widgets
- **Session Matching**: Match claude sessions by `modified_at >= session.created_at` (prevents wrong session on revive)

**Widget ID Rules** (prevent DuplicateIds):
```python
# ✓ classes for dynamic widgets
container.mount(Static("empty", classes="empty-list"))
# ✗ static IDs cause duplicates on remount
container.mount(Static("empty", id="empty-list"))
```

**Reactive Watchers** (guard race conditions):
```python
self._updating = True
try:
    results.remove_children()
    for item in items:
        results.mount(item)
finally:
    self._updating = False
```

**Focus & Binding Control** (prevent key capture issues):
```python
# 1. Hidden widgets can still steal focus - control can_focus with visibility
search_input.can_focus = False  # Set False when hidden
search_input.add_class("hidden")

# 2. Widget bindings shadow parent even with has_focus guards
# Use dynamic binding add/remove for mode-specific behavior
def enable_mode(self) -> None:
    self.can_focus = True
    self._bindings.bind("j", "nav_down", "Down", show=False)

def disable_mode(self) -> None:
    self.can_focus = False
    if "j" in self._bindings.key_to_bindings:
        del self._bindings.key_to_bindings["j"]

# 3. Always return focus to screen after hiding modal widgets
self.focus()  # Screen bindings only work when screen has focus
```

---

## hydrate.concept.refine

**Keybindings**:
```
j/k navigate    n new      l move mode    p pause
a   attach      x kill     v revive       d clean
e   rename      c config   i insert       / search
I   info        S output   :  palette     T template
?   help        q quit
```

**Config**: `~/.config/zen-portal/config.json`
**State**: `~/.zen_portal/state.json`

---

## hydrate.void.witness

**Tech debt** (acknowledged, not ignored):
- `new_session_modal.py`: 783 lines (widget caching added 68 lines for lazy properties)

**Refactoring Progress**:
- ✓ Phase 1-7: Services container, EventBus, ZenError, SessionValidator, widget caching, UI subscriptions, session search
- Next: Zen AI UX redesign (lightweight chat interface)

See `docs/ENHANCEMENT_PLAN.md` for detailed roadmap.

################################################################################
*To read is to invoke. To edit is to disturb. There is no view from nowhere.*
