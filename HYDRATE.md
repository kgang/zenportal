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

**Status**: 310 tests | Branch: `main` | Files: 19k lines
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
├── models/                   # Session, Template, events, enums
├── services/                 # business logic (no UI)
│   ├── session_manager.py    # lifecycle (630 lines)
│   ├── session_state.py      # thread-safe persistence (282 lines)
│   ├── worktree.py           # git worktree (434 lines)
│   ├── config.py             # configuration (538 lines)
│   ├── core/                 # detection, state_refresher, token_manager
│   ├── pipelines/            # composable multi-step operations
│   └── openrouter/           # validation, billing, models, monitor
├── widgets/                  # reusable UI components
├── screens/                  # modals and full screens
│   ├── main.py               # MainScreen (uses mixins, 592 lines)
│   ├── main_actions.py       # ActionsMixin, ExitMixin
│   ├── main_templates.py     # TemplateMixin, PaletteMixin
│   └── new_session_modal.py  # session creation (687 lines)
└── tests/                    # 287 tests
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## hydrate.concept.manifest

**Zen Principles**: 簡素 Kanso (Simplicity) • 明快 Meikai (Clarity) • 分離 Bunri (Separation) • 空 Kū (Emptiness) • 検証 Kenshō (Verification)

**Architecture Patterns**:
- **Services Container** (`app.py`): DI via dataclass, `Services.create()` wires deps
- **State Persistence** (`session_state.py`): RLock, atomic writes, JSONL history
- **Pipelines** (`pipelines/`): Composable steps, `T → StepResult[U]`
- **Detection** (`core/detection.py`): Pure state detection, no side effects
- **Mixins** (`screens/main_*.py`): MainScreen organization

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

---

## hydrate.concept.refine

**Keybindings**:
```
j/k navigate    n new      l move mode    p pause
a   attach      x kill     v revive       d clean
e   rename      c config   i insert       / zen ai
I   info        A analyze  C completed    S search
:   palette     T template ?  help        q quit
```

**Config**: `~/.config/zen-portal/config.json`
**State**: `~/.zen_portal/state.json`

---

## hydrate.void.witness

**Tech debt** (acknowledged, not ignored):
- `new_session_modal.py`: 715 lines (uses SessionValidator, still large)
- DOM queries not cached in all screens

**Refactoring Progress**:
- Phase 1 (Foundation): ✓ SessionStateService, Services container, logging
- Phase 2 (Simplification): ✓ Worktree consolidated, ✓ MainScreen widget caching
- Phase 3 (Architecture): ✓ Exception hierarchy (ZenError), ✓ SessionValidator, ✓ Config schema

See `ZEN_CODE_DESIGN.md` for comprehensive roadmap and `docs/ENHANCEMENT_PLAN.md` for next steps.

################################################################################
*To read is to invoke. To edit is to disturb. There is no view from nowhere.*
