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

**Status**: 361 tests (⚠ 1 failing) | Branch: `main` | Lines: ~22k (17.7k code + 4.3k tests) | Version: ⚠ inconsistent (see void)
**Last hydrated**: 2026-06-21 (deep re-exploration) | Last commit: 2026-05-20
################################################################################

## hydrate.project.manifest

**Zenportal** - Contemplative TUI for managing AI assistant sessions in parallel.

```
zen                                          # run
uv run --extra dev pytest zen_portal/tests/  # test (pytest is a dev extra)
```

**Session types**: AI (claude/codex/gemini/openrouter), Shell
**States**: RUNNING (●), COMPLETED (○), PAUSED (◐), FAILED (·), KILLED (·)

---

## hydrate.self.manifest

```
zen_portal/
├── app.py                    # Entry point + Services container (DI, 8 services), 271 lines
├── __main__.py               # CLI entry
├── __init__.py               # ⚠ __version__ = "0.1.0" (out of sync, see void)
├── models/                   # Data models and enums
│   ├── session.py            # Session, SessionType, SessionState, SessionFeatures, SessionTokenMetrics (211)
│   ├── template.py           # SessionTemplate for reusable configs
│   ├── new_session.py        # AIProvider, ResultType (NewSessionType aliased to SessionType)
│   ├── events.py             # UI-level Textual messages (SessionSelected)
│   └── exceptions.py         # ZenError hierarchy
├── services/                 # Business logic (no UI)
│   ├── session_manager.py    # Lifecycle management (720 lines)
│   ├── events.py             # EventBus pub/sub (234 lines)
│   ├── session_state.py      # Thread-safe persistence (RLock, JSONL) (304)
│   ├── state.py              # SessionRecord/PortalState persistence dataclasses (125)
│   ├── session_commands.py   # Shell command builder (375 lines)
│   ├── validation.py         # SessionValidator, ValidationResult (241)
│   ├── conflict.py           # Pre-creation session conflict detection (81) [NEW]
│   ├── command_registry.py   # Command metadata registry — data layer for palette (320) [NEW]
│   ├── fuzzy.py              # Fuzzy match + scoring for command palette (110) [NEW]
│   ├── token_parser.py       # Parse Claude JSONL → TokenUsage + cost estimate (281) [NEW]
│   ├── context_parser.py     # @output/@error/@git context refs for Zen AI (185) [NEW]
│   ├── tmux.py               # Low-level tmux operations (324)
│   ├── tmux_async.py         # Async tmux wrapper (asyncio.to_thread)
│   ├── worktree.py           # Git worktree management (434)
│   ├── config.py             # 3-tier config resolution (549)
│   ├── discovery.py          # Claude session discovery (473)
│   ├── profile.py            # User preferences
│   ├── notification.py       # Toast notifications
│   ├── banner.py             # ASCII art banners
│   ├── template_manager.py   # Template CRUD
│   ├── pipeline.py           # Step/StepResult protocol (composable steps)
│   ├── zen_ai.py             # Lightweight AI backend — PRESERVED but DORMANT (323, see void)
│   ├── billing_tracker.py    # ⚠ DEPRECATED shim → openrouter.billing
│   ├── openrouter_models.py  # ⚠ DEPRECATED shim → openrouter.models
│   ├── proxy_monitor.py      # ⚠ DEPRECATED shim → openrouter.monitor
│   ├── proxy_validation.py   # ⚠ DEPRECATED shim → openrouter.validation
│   ├── core/                 # Extracted core services
│   │   ├── detection.py      # Session state detection
│   │   ├── state_refresher.py # [LEGACY] Sync polling (replaced by reactive)
│   │   └── token_manager.py  # Token tracking + sparklines
│   ├── reactive/             # Reactive architecture (replaces polling)
│   │   ├── signal.py         # Signal[T], Computed[T], Effect primitives (275)
│   │   └── session_watcher.py # Async state monitoring (10s heartbeat) (196)
│   ├── git/                  # Git integration
│   │   └── git_service.py    # Centralized git ops (247)
│   ├── openrouter/           # OpenRouter proxy support (canonical location)
│   │   ├── billing.py        # Cost tracking (456)
│   │   ├── models.py         # Model fetching (24h cache) (269)
│   │   ├── validation.py     # Proxy config validation (358)
│   │   └── monitor.py        # Health monitoring (412)
│   └── pipelines/            # Composable multi-step operations
│       └── create.py         # 8-step session creation pipeline (265)
├── screens/                  # Textual UI screens and modals
│   ├── base.py               # ZenScreen / ZenModalScreen base (notification rack) (97) [NEW]
│   ├── main.py               # MainScreen (848 lines, uses 4 mixins)
│   ├── main_actions.py       # MainScreenActionsMixin + MainScreenExitMixin
│   ├── main_templates.py     # MainScreenPaletteMixin + MainScreenTemplateMixin
│   ├── new_session_modal.py  # Session creation (871 lines, 3 tabs)
│   ├── new_session/          # NewSession modal components
│   │   ├── billing_widget.py # Claude vs OpenRouter billing select (243) [NEW]
│   │   └── css.py            # NEW_SESSION_CSS constant (187) [NEW]
│   ├── new_session_lists.py  # ListBuilder[T] base + list components
│   ├── config_screen.py      # Configuration editor (386)
│   ├── command_palette.py    # Palette UI (consumes command_registry + fuzzy) (212)
│   ├── worktrees.py          # Worktree management modal (W key) (213) [NEW]
│   ├── zen_prompt.py         # ZenPromptModal — DEFINED but DISABLED (209, see void) [NEW]
│   ├── template_picker.py    # Template picker (218)
│   ├── template_editor.py    # Template editor (240)
│   ├── insert_modal.py       # Send keystrokes to tmux (215)
│   ├── exit_modal.py         # Exit confirmation (188)
│   ├── rename_modal.py       # Session rename
│   ├── attach_session.py     # Adopt external tmux (186)
│   └── help.py               # Keybindings reference
├── widgets/                  # Reusable Textual widgets
│   ├── session_list.py       # Session list with smart diffing (443 lines)
│   ├── output_view.py        # Tmux output display (407 lines)
│   ├── session_info.py       # Session details panel (197 lines)
│   ├── directory_browser.py  # Filesystem picker (339 lines)
│   ├── path_input.py         # Path Input w/ live validation (69) [NEW]
│   ├── model_selector.py     # Claude/OpenRouter model dropdown (335)
│   ├── session_type_dropdown.py # Session-type filter dropdown (config) [NEW]
│   ├── proxy_status.py       # OpenRouter health/billing display (327)
│   ├── zen_dropdown.py       # Custom dropdown with search (222)
│   ├── zen_ai_dropdown.py    # Zen AI config dropdown — WIRED into config (116) [NEW]
│   ├── zen_mirror.py         # AI-context sidebar — DEFINED but UNUSED stub (149, see void) [NEW]
│   ├── status.py             # StatusBar (duration + AAU budget) — exported, not mounted (46) [NEW]
│   ├── splitter.py           # Draggable vertical splitter for resizable panes (106)
│   └── notification.py       # Toast widget
├── styles/                   # Python-defined CSS (not .tcss files)
│   └── base.py               # BASE_CSS = 7 concatenated CSS constants (250)
└── tests/                    # 17 test modules, 361 tests (⚠ 1 failing)
    ├── conftest.py           # Pytest fixtures
    └── test_*.py             # Test modules
```

**File limit**: ~500 lines. Largest: new_session_modal.py (871), main.py (848), session_manager.py (720).
**[NEW]** = added since previous hydration. **⚠ DEPRECATED shim** = re-export for back-compat (removal candidate).

---

## hydrate.concept.manifest

**Zen Principles**: 簡素 Kanso (Simplicity) • 明快 Meikai (Clarity) • 分離 Bunri (Separation) • 空 Kū (Emptiness) • 検証 Kenshō (Verification)

### Architecture Patterns

**Services Container** (`app.py`, 8 services):
```python
@dataclass
class Services:
    tmux: TmuxService
    config: ConfigManager
    profile: ProfileManager
    notification: NotificationService
    sessions: SessionManager
    state: SessionStateService
    worktree: WorktreeService | None  # None if not a git repo
    discovery: DiscoveryService

    @classmethod
    def create(cls, working_dir: Path | None = None) -> "Services":
        # Wires all dependencies; created once in main() and reused
        # across attach/detach cycles (persists the reactive watcher state)
```

**Command Palette architecture** (`:` / `ctrl+p`) — clean data/UI split:
```python
# DATA: services/command_registry.py — single source of truth for commands
registry = create_default_registry()        # ~26 Command entries w/ metadata
registry.get_contextual(has_selection)      # context-aware filtering
# RANK: services/fuzzy.py — exact > prefix > word-boundary > contains > subseq
rank_commands(query, items)
# UI:   screens/command_palette.py — Textual modal, consumes the registry
# Registry built once in MainScreen.__init__ → self._command_registry
```

**Token tracking** (`services/token_parser.py` + `core/token_manager.py`):
```python
# Parse Claude Code JSONL session logs → token usage + OpenRouter cost estimate
TokenParser.get_session_stats(claude_session_id, working_dir) -> SessionTokenStats
TokenParser.get_token_history(...) -> list[int]   # feeds sparklines
# Surfaced on Session.token_metrics (SessionTokenMetrics dataclass)
```

**EventBus** (`services/events.py`):
```python
bus = EventBus.get()  # Singleton
bus.emit(SessionCreatedEvent(session_id="x", session_name="y"))
bus.subscribe(SessionCreatedEvent, self._on_session_created)
# Events: SessionCreated, SessionPaused, SessionKilled, SessionCleaned,
#         SessionOutput, SessionTokenUpdate, ProxyStatusChanged, ConfigChanged
```

**Reactive Architecture** (`services/reactive/`, `services/tmux_async.py`):

The critical breakthrough: **async tmux calls via `asyncio.to_thread()` eliminate UI freezing**.

```python
# OLD: Blocking polling caused 5s UI freezes
self.set_interval(1.0, self._poll_sessions)  # Every 1s
def _poll_sessions(self):
    self._manager.refresh_states()  # → subprocess.run() BLOCKS

# NEW: Async watcher with non-blocking tmux calls
self._watcher = SessionStateWatcher(AsyncTmuxService(tmux), manager)
await self._watcher.start()  # 10s heartbeat, event-triggered refreshes

# AsyncTmuxService wraps blocking calls
async def session_exists(self, name: str) -> bool:
    return await asyncio.to_thread(self._tmux.session_exists, name)
```

**Reactive Primitives** (ported from kgents):
```python
# Signal[T] - observable state with subscribers
count = Signal.of(0)
unsub = count.subscribe(lambda v: print(f"Count: {v}"))
count.set(1)  # → prints "Count: 1"

# Computed[T] - lazy derived state
full_name = Computed.of(
    compute=lambda: f"{first.value} {last.value}",
    sources=[first, last]
)

# Effect - side effects with cleanup
effect = Effect.of(fn=log_count, sources=[count])
effect.run_if_dirty()
```

**Why this works**:
| Aspect | Before (Polling) | After (Reactive) |
|--------|------------------|------------------|
| Interval | 1s blocking | 10s async heartbeat |
| Rapid refresh | 333ms × 9 ticks | 500ms × 6 async |
| tmux calls | subprocess.run() blocks | asyncio.to_thread() |
| UI freeze | 5s timeout risk | Never blocks |
| CPU usage | Constant polling | Zero when idle |

**Pipeline Pattern** (`services/pipelines/create.py`):
```python
# 8-step session creation
Steps: ResolveConfig → CreateSessionModel → SetupWorktree → BuildCommand
     → ValidateCommand → ValidateProxy → CreateTmuxSession → DiscoverClaudeSession
# Each returns StepResult[T] for error handling
```

**3-Tier Configuration** (`services/config.py`):
```
Resolution: session > portal > config > defaults
Files: ~/.config/zen-portal/config.json (user defaults)
       ~/.config/zen-portal/portal.json (project state)
       ~/.zen_portal/state.json (session persistence)
```

**Graceful Degradation** (tuple return for error handling):
```python
def expand_file_reference(text: str) -> tuple[str, str | None]:
    """Return (result, error). Caller decides how to handle."""
    if error:
        return original_text, "descriptive error"
    return expanded_text, None
```

### Widget Rules

**Widget ID Rules** (prevent DuplicateIds):
```python
# ✓ classes for dynamic widgets
container.mount(Static("empty", classes="empty-list"))
# ✗ static IDs cause duplicates on remount
container.mount(Static("empty", id="empty-list"))
```

**Async remove/mount** (also DuplicateIds source — even with unique IDs):
```python
# ✗ remove_children() returns AwaitRemove; mount runs before removal lands
container.remove_children()
container.mount(Static(..., id=f"row-{i}"))  # collides with stale row-{i}

# ✓ await both — propagate async up the call chain (handlers can be async)
await container.remove_children()
await container.mount(Static(..., id=f"row-{i}"))
```
This bit `NewSessionModal` attach/resume tabs on re-activation (f7ddb37).

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

**Focus & Binding Control**:
```python
# 1. Hidden widgets steal focus - control can_focus with visibility
search_input.can_focus = False
search_input.add_class("hidden")

# 2. Dynamic bindings for mode-specific behavior
def enable_mode(self):
    self.can_focus = True
    self._bindings.bind("j", "nav_down", "Down", show=False)

# 3. Return focus to screen after hiding modal widgets
self.focus()
```

**Smart Diffing** (visual calm in SessionList):
```python
# In-place updates for content-only changes (age, glyph)
# Full recompose only on structural changes (add/remove sessions)
```

**Elastic Width** (SessionListItem):
```python
# SessionListItem.render() adapts to available width
# - Wide (>=25): glyph + name + age
# - Narrow (<25): glyph + name only (hide age)
# SessionList.on_resize() refreshes all items when splitter moves
```

---

## hydrate.concept.refine

**Keybindings**:
```
j/k navigate    n new          l move mode    p pause
a   attach tmux o attach exist x kill         v revive
d   clean       e rename       c config       i insert
I   info        s streaming    S out-search   / sess-search
w   worktree    W worktrees    : palette      ctrl+p palette
T   template    r refresh      R restart      ? help    q quit
1-0 focus 1-10  (quick jump to session by position)
```
Source of truth: `screens/main.py` BINDINGS (lines 42-84). Many actions also
registered in `services/command_registry.py` for the `:` / ctrl+p palette.

**External Tools Required**:
- `tmux` - Session management (required)
- `git` - Worktree support (optional)
- `claude` - Claude Code CLI (for Claude sessions)
- `codex` - OpenAI Codex CLI (optional)
- `gemini` - Google Gemini CLI (optional)
- `orchat` - OpenRouter CLI (optional)

**Session Matching** (for Claude revival):
```
Match strategy (find_session_for_zenportal):
1. Use created_at (st_birthtime on macOS) - find session created closest after zen-portal creation
2. Fallback to modified_at - find session modified closest after zen-portal creation

KILLED sessions: start fresh (no --resume or --continue)
PAUSED: capture claude_session_id at pause time if not already set
COMPLETED: use existing claude_session_id for --resume
```

**@filepath Expansion**:
```
Pattern: @/path, @~/home, @./relative
Max size: 1MB
Used in: prompt input of NewSessionModal

Note: Large system prompts (>12KB) use launcher script approach
to bypass tmux's ~16KB command length limit.
```

**Security**:
- Command injection detection (backticks, $(), &&, ||, ;)
- API key pattern validation: ^[a-zA-Z0-9_-]+$
- URL scheme whitelist: http, https only
- Config files: 0600 permissions (atomic writes)
- Input limits: prompt (2000 chars), name (64 chars, no character restrictions)

---

## hydrate.void.witness

**⚠ ACTIVE ISSUES (found 2026-06-21 re-exploration)**:

1. **Version is inconsistent across 3 sources** — pick one and unify:
   - `zen_portal/__init__.py` → `__version__ = "0.1.0"`
   - `pyproject.toml` → `version = "0.3.0"`
   - this doc (previously) → `0.3.1`

2. **1 failing test**: `tests/test_config.py::TestFeatureSettings::test_to_dict_with_values`
   - Expects `model == "opus"` but Opus 4.6 change (fe15ddf) now serializes
     `"claude-opus-4-6"`. Test was never updated. Fix: update the assertion.
   - `uv run --extra dev pytest` → 360 passed, 1 failed.

3. **Dormant "Zen AI" feature** (built, then disconnected — preserved for future
   non-blocking chat UX; do not assume it runs):
   - `services/zen_ai.py` — backend, stable API, NOT wired to any action.
   - `screens/zen_prompt.py` (`ZenPromptModal`) — DEFINED but no caller
     (`action_zen_prompt`/`action_analyze` removed, see main_actions.py ~278).
   - `widgets/zen_mirror.py` (`ZenMirror`) — DEFINED but never imported (stub).
   - `widgets/zen_ai_dropdown.py` — the ONLY live piece (config_screen settings UI).

4. **4 deprecated re-export shims** in `services/` top level (removal candidates
   once no external imports depend on the old paths):
   `billing_tracker.py`, `openrouter_models.py`, `proxy_monitor.py`,
   `proxy_validation.py` → all re-export from `services/openrouter/`.

5. **`widgets/status.py`** (`StatusBar`) — exported but not mounted anywhere
   (AAU-budget UI; pending or abandoned).

**Tech debt** (acknowledged, by size):
- `screens/new_session_modal.py`: 871 lines — 3 tabs, @filepath, widget caching
  (still flagged for split into a subdirectory; `new_session/` started this)
- `services/session_manager.py`: 720 lines
- `screens/main.py`: 848 lines (acceptable with 4 mixins)
- `services/config.py`: 549 lines

### tmux Memory Considerations

**Known issue**: tmux memory grows with `history-limit` and high-output sessions due to glibc allocator behavior (not a true leak - freed memory not returned to OS).

**Current setting**: `DEFAULT_HISTORY_LIMIT = 10000` (zen_portal/services/tmux.py:21)

**Mitigations**:
1. `clear_history()` called automatically when sessions transition to COMPLETED/FAILED (session_watcher.py:174)
2. `clear_history()` called before killing sessions (tmux.py:245)
3. Sessions with dead panes cleaned via `cleanup_dead_zen_sessions()`

**If "server stopped unexpectedly" still occurs**:
- Kill old tmux sessions manually: `tmux kill-server` (nuclear option)
- Reduce parallel sessions or restart zen periodically

**Refactoring Progress**:
- ✓ Phase 1-4: Services container, EventBus, ZenError, SessionValidator, widget caching
- ✓ Phase 5: @filepath expansion, session revival fixes
- ✓ Phase 6: Search mode j/k hotkey fix
- ✓ Phase 7: **Reactive Architecture** - eliminated polling, async tmux calls
- ✓ Phase 8: Session name restrictions removed (any characters allowed)
- ✓ Phase 9: **Session revival fix** - accurate claude_session_id matching using created_at
- ✓ Phase 10: **Command palette** - registry/fuzzy/UI split (`:` / ctrl+p)
- ✓ Phase 11: **Token tracking** - JSONL parsing → usage + cost (token_parser)
- ✓ Phase 12: **Worktrees screen** (`W`) + `o` attach-existing + base ZenScreen/ZenModalScreen
- ✓ Phase 13: **OpenRouter package** - moved to `services/openrouter/` (old paths now deprecated shims)
- ◐ Phase 14: **Zen AI** - backend built, UI disconnected (dormant, see void)

**Completed Simplifications** (2024-12):
| Done | Issue | Location | Result |
|------|-------|----------|--------|
| ✓ | Visibility toggle duplication | new_session_modal.py | Extracted `_update_ui_visibility()` (-25 lines) |
| ✓ | NewSessionType/SessionType enum duplication | models/ | Unified to single SessionType enum |
| ✓ | ListBuilder code duplication | new_session_lists.py | Extracted base `ListBuilder[T]` class |
| ✓ | Session dataclass token concerns | models/session.py | Extracted `SessionTokenMetrics` dataclass |
| | new_session_modal.py oversized (871 lines) | screens/ | Future: split into subdirectory |

See `docs/ENHANCEMENT_PLAN.md` for detailed roadmap.

---

## hydrate.time.witness

**Recent commits** (git log --oneline -10):
```
b36101b docs: update HYDRATE.md with async remove/mount gotcha
f7ddb37 fix: prevent DuplicateIds crash when activating attach/resume tabs
054aee9 change from zen-portal to zenportal
fe15ddf feat: update default Opus model to Claude Opus 4.6   ← broke test_config
a964fc8 fix prompt injection into fresh session
f81493b docs: update HYDRATE.md with latest commits
613b3de docs: update HYDRATE.md with hotkey and revival improvements
7f18c4c feat: add numeric hotkeys 1-0 for quick session focus
48d2ff2 fix: improve session revival with accurate claude_session_id matching
5b92278 docs: update HYDRATE.md with refactor commit
```
(working tree clean at hydration time; HEAD = b36101b, dated 2026-05-20)

---

## hydrate.api.surface

**Key Entry Points**:
```python
# Create session
SessionManager.create_session(
    name: str,
    session_type: NewSessionType,
    provider: AIProvider | None,
    model: ClaudeModel | None,
    prompt: str | None,
    features: SessionFeatures | None
) -> Session

# Session state
session.state: SessionState  # RUNNING, COMPLETED, FAILED, PAUSED, KILLED
session.is_active: bool      # Property: state == RUNNING
session.status_glyph: str    # ●/○/◐/·

# Configuration
ConfigManager.get_resolved_features(
    session_features: SessionFeatures | None
) -> FeatureSettings  # Merged: session > portal > config > defaults
```

**EventBus Events**:
```python
SessionCreatedEvent(session_id, session_name)
SessionStateChangedEvent(session_id, old_state, new_state)
SessionPausedEvent(session_id, worktree_preserved)
SessionKilledEvent(session_id, worktree_deleted)
SessionCleanedEvent(session_id)
SessionOutputEvent(session_id, output)
SessionTokenUpdateEvent(session_id, input_tokens, output_tokens)
ProxyStatusChangedEvent(enabled, healthy)
ConfigChangedEvent(config_type, key, value)
```

################################################################################
*To read is to invoke. To edit is to disturb. There is no view from nowhere.*
