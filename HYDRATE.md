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

**Status**: 361 tests | Branch: `main` | Lines: ~20,857 | Version: 0.3.0
################################################################################

## hydrate.project.manifest

**Zenportal** - Contemplative TUI for managing AI assistant sessions in parallel.

```
zen                              # run
uv run pytest zen_portal/tests/  # test
```

**Session types**: AI (claude/codex/gemini/openrouter), Shell
**States**: RUNNING (●), COMPLETED (○), PAUSED (◐), FAILED (·), KILLED (·)

---

## hydrate.self.manifest

```
zen_portal/
├── app.py                    # Entry point + Services container (DI)
├── __main__.py               # CLI entry
├── models/                   # Data models and enums
│   ├── session.py            # Session, SessionType, SessionState, SessionFeatures
│   ├── template.py           # SessionTemplate for reusable configs
│   ├── new_session.py        # NewSessionType, AIProvider, ResultType
│   ├── events.py             # UI-level Textual messages (SessionSelected)
│   └── exceptions.py         # ZenError hierarchy
├── services/                 # Business logic (no UI)
│   ├── session_manager.py    # Lifecycle management (686 lines)
│   ├── events.py             # EventBus pub/sub (235 lines)
│   ├── session_state.py      # Thread-safe persistence (RLock, JSONL)
│   ├── session_commands.py   # Shell command builder (330 lines)
│   ├── validation.py         # SessionValidator, ValidationResult
│   ├── tmux.py               # Low-level tmux operations
│   ├── worktree.py           # Git worktree management
│   ├── config.py             # 3-tier config resolution
│   ├── discovery.py          # Claude session discovery
│   ├── profile.py            # User preferences
│   ├── notification.py       # Toast notifications
│   ├── banner.py             # ASCII art banners
│   ├── template_manager.py   # Template CRUD
│   ├── zen_ai.py             # Lightweight AI queries (unused)
│   ├── core/                 # Extracted core services
│   │   ├── detection.py      # Session state detection
│   │   ├── state_refresher.py # Background polling
│   │   └── token_manager.py  # Token tracking + sparklines
│   ├── git/                  # Git integration
│   │   └── git_service.py    # Centralized git ops
│   ├── openrouter/           # OpenRouter proxy support
│   │   ├── billing.py        # Cost tracking
│   │   ├── models.py         # Model fetching (24h cache)
│   │   ├── validation.py     # Proxy config validation
│   │   └── monitor.py        # Health monitoring
│   └── pipelines/            # Composable multi-step operations
│       └── create.py         # 8-step session creation pipeline
├── screens/                  # Textual UI screens and modals
│   ├── main.py               # MainScreen (900+ lines, uses mixins)
│   ├── main_*.py             # MainScreen mixins (actions, exit, template, palette)
│   ├── new_session_modal.py  # Session creation (35KB, 3 tabs)
│   ├── new_session/          # NewSession modal components
│   ├── config_screen.py      # Configuration editor
│   ├── command_palette.py    # Command registry + fuzzy search
│   ├── template_*.py         # Template picker/editor
│   ├── insert_modal.py       # Send keystrokes to tmux
│   ├── exit_modal.py         # Exit confirmation
│   ├── rename_modal.py       # Session rename
│   ├── attach_session.py     # Adopt external tmux
│   └── help.py               # Keybindings reference
├── widgets/                  # Reusable Textual widgets
│   ├── session_list.py       # Session list with smart diffing (394 lines)
│   ├── output_view.py        # Tmux output display (405 lines)
│   ├── session_info.py       # Session details panel (197 lines)
│   ├── directory_browser.py  # Filesystem picker (339 lines)
│   ├── model_selector.py     # Claude/OpenRouter model dropdown
│   ├── proxy_status.py       # OpenRouter health/billing display
│   ├── zen_dropdown.py       # Custom dropdown with search
│   └── notification.py       # Toast widget
├── styles/                   # CSS styling
└── tests/                    # 356 unit tests
    ├── conftest.py           # Pytest fixtures
    └── test_*.py             # Test modules
```

**File limit**: ~500 lines. Large modules split into `core/` or supporting files.

---

## hydrate.concept.manifest

**Zen Principles**: 簡素 Kanso (Simplicity) • 明快 Meikai (Clarity) • 分離 Bunri (Separation) • 空 Kū (Emptiness) • 検証 Kenshō (Verification)

### Architecture Patterns

**Services Container** (`app.py`):
```python
@dataclass
class Services:
    tmux: TmuxService
    config: ConfigManager
    sessions: SessionManager
    state: SessionStateService
    worktree: WorktreeService | None  # None if not git repo
    # ... other services

    @classmethod
    def create(cls, working_dir: Path | None = None) -> "Services":
        # Wires all dependencies
```

**EventBus** (`services/events.py`):
```python
bus = EventBus.get()  # Singleton
bus.emit(SessionCreatedEvent(session_id="x", session_name="y"))
bus.subscribe(SessionCreatedEvent, self._on_session_created)
# Events: SessionCreated, SessionPaused, SessionKilled, SessionCleaned,
#         SessionOutput, SessionTokenUpdate, ProxyStatusChanged, ConfigChanged
```

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

---

## hydrate.concept.refine

**Keybindings**:
```
j/k navigate    n new      l move mode    p pause
a   attach      x kill     v revive       d clean
e   rename      c config   i insert       / search
I   info        S output   :  palette     T template
?   help        q quit     s streaming    R restart
```

**External Tools Required**:
- `tmux` - Session management (required)
- `git` - Worktree support (optional)
- `claude` - Claude Code CLI (for Claude sessions)
- `codex` - OpenAI Codex CLI (optional)
- `gemini` - Google Gemini CLI (optional)
- `orchat` - OpenRouter CLI (optional)

**Session Matching** (for Claude revival):
```
Match claude sessions by: modified_at >= session.created_at
Prevents attaching wrong session after restart
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
- Input limits: prompt (2000 chars), name (64 chars)

---

## hydrate.void.witness

**Tech debt** (acknowledged):
- `new_session_modal.py`: 35KB (896 lines) - widget caching, @filepath, 3 tabs
- `session_manager.py`: 686 lines
- `main.py`: ~900 lines (acceptable with mixins)

**Refactoring Progress**:
- ✓ Phase 1-4: Services container, EventBus, ZenError, SessionValidator, widget caching
- ✓ Phase 5: @filepath expansion, session revival fixes
- ✓ Phase 6: Search mode j/k hotkey fix
- Next: Zen AI UX redesign (lightweight chat interface)

**Stale Docs**:
- `docs/ARCHITECTURE.md`: References old AAU Budget system (removed)
- `docs/ENHANCEMENT_PLAN.md`: Test count says 328, actual is 356

See `docs/ENHANCEMENT_PLAN.md` for detailed roadmap.

---

## hydrate.time.witness

**Recent commits** (git log --oneline -10):
```
012bc86 docs: update HYDRATE.md with test count and tmux limit note
c02634e fix: handle large system prompts by using launcher scripts for tmux
4527f5d feat: add system prompt support to session creation pipeline
564664e chore: add .envrc to gitignore
6676ea3 feat: add @filepath expansion for prompts in new session modal
133ac92 fix: session revival matches correct claude session, dangerous mode default on
df5ef63 fix: resolve search mode breaking j/k navigation hotkeys
6704ed3 docs: update HYDRATE.md for Phase 5 completion
dfd9729 feat: add EventBus for decoupled service-to-UI communication
14b6ce7 docs: update HYDRATE.md for Phase 3 completion
```

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
