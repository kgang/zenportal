# Zenportal Enhancement Plan

> Assessment Date: 2025-12-11 (Updated)

## hydrate.project.manifest

**Current State**: Solid foundation with good test coverage (356 tests). Phase 1-6 complete. EventBus added for decoupled service-UI communication. Widget caching in main screens. @filepath expansion for prompts.

**Key Metrics**:
| Metric | Current | Target |
|--------|---------|--------|
| Tests | 356 | 400+ |
| Files > 500 lines | 3 | 0 |
| Total lines | 20,857 | ~18,000 |

---

## hydrate.project.afford

What zenportal enables:

1. **Parallel AI Sessions**: Run multiple Claude/Codex/Gemini sessions simultaneously
2. **Session Persistence**: Sessions survive app restart (tmux backing)
3. **Worktree Isolation**: Git worktrees for session-specific branches
4. **Token Tracking**: Real-time token usage visualization
5. **OpenRouter Integration**: Proxy support with billing monitoring

---

## hydrate.project.block

Current blockers and tech debt:

### 1. Large Files (Violate 500-line Limit)

| File | Lines | Issue |
|------|-------|-------|
| `new_session_modal.py` | 715 | Uses SessionValidator, further extraction possible |
| `session_manager.py` | 630 | Still above target |
| `main.py` | 592 | Acceptable with mixins |

### 2. Architectural Gaps (All Addressed)

- ✓ **Exception Hierarchy**: `ZenError` base with specific subclasses
- ✓ **SessionValidator**: Extracted to `services/validation.py`
- ✓ **Config Schema**: Dataclasses with `from_dict`/`to_dict`
- ✓ **EventBus**: `services/events.py` - typed pub/sub, decouples services from UI

### 3. Missing Features

- Session search/filter
- Batch operations UI
- Session groups/tags
- Export session output

---

## hydrate.concept.refine (Recommendations)

### Phase 3: Architecture (COMPLETE)

**3.1 Extract Validators from Screens** ✓

Implemented in `services/validation.py`:
```python
class SessionValidator:
    def validate_name(self, name: str, existing_names: set[str]) -> ValidationResult
    def validate_directory(self, path_str: str) -> ValidationResult
    def validate_prompt(self, prompt: str, required: bool) -> ValidationResult
    def validate_for_creation(...) -> ValidationResult  # Full validation
```

`new_session_modal.py` now uses `SessionValidator` for all validation.
23 new tests added for `ValidationResult` and `SessionValidator`.

**3.2 Create Exception Hierarchy** ✓

Implemented in `models/exceptions.py`:
```python
class ZenError(Exception):
    """Base for all zenportal errors."""

class SessionError(ZenError): ...
class SessionNotFoundError(SessionError): ...
class ConfigError(ZenError): ...
class WorktreeError(ZenError): ...
class ValidationError(ZenError): ...
class TmuxError(ZenError): ...
```

**3.3 Config Schema Dataclass** ✓

Already in place in `services/config.py`:
- `ProxySettings`, `ZenAIConfig`, `WorktreeSettings`, `FeatureSettings`, `Config`
- All with `from_dict()` and `to_dict()` serialization
- Type-safe, IDE autocomplete works

### Phase 4: Architecture (COMPLETE)

**4.1 EventBus** ✓

Implemented in `services/events.py`:
```python
from zen_portal.services.events import EventBus, SessionCreatedEvent

# Services emit
bus = EventBus.get()
bus.emit(SessionCreatedEvent(session_id="x", session_name="y"))

# UI subscribes
bus.subscribe(SessionCreatedEvent, self._on_session_created)
```

- Typed events: `SessionCreatedEvent`, `SessionPausedEvent`, `ProxyStatusChangedEvent`, etc.
- Singleton pattern with `EventBus.get()`
- Error isolation: one handler's error doesn't affect others
- 18 tests added

**4.2 Widget Caching** ✓

Added lazy property pattern to `new_session_modal.py`:
```python
@property
def name_input(self) -> Input:
    if self._name_input is None:
        self._name_input = self.query_one("#name-input", Input)
    return self._name_input
```

Removes ~50 DOM queries per modal lifecycle.

### Phase 5: Features

**5.1 Session Search**

- Fuzzy search across session names/output
- Filter by type, state, directory
- Keybinding: `/` (when no session selected)

**5.2 Session Groups**

- Tag sessions with labels
- Group by project/directory
- Collapse/expand groups in list

**5.3 Output Export**

- Export session output to file
- Format options: plain text, markdown, JSON
- Keybinding: `E`

### Phase 6: Polish

**6.1 Performance**

- ✓ Cache widget references in main screens
- Lazy load OpenRouter models
- Debounce rapid state updates

**6.2 Testing**

- Integration tests for session lifecycle
- UI tests with Textual's pilot
- Target: 80% coverage

**6.3 Documentation**

- User guide (README enhancement)
- Configuration reference
- Keybinding cheatsheet

---

## hydrate.time.witness (Timeline)

### Completed

- ✓ Phase 1: SessionStateService, Services container, logging
- ✓ Phase 2: Worktree consolidation, MainScreen widget caching
- ✓ Session limit removed (unlimited sessions)
- ✓ Phase 3.1: SessionValidator extracted to `services/validation.py`
- ✓ Phase 3.2: Exception hierarchy in `models/exceptions.py`
- ✓ Phase 3.3: Config schema already in place
- ✓ Phase 4.1: EventBus in `services/events.py` (18 tests)
- ✓ Phase 4.2: Widget caching in `new_session_modal.py`

### Upcoming

| Phase | Focus | Files Affected |
|-------|-------|----------------|
| 5.1 | Session search | main.py, session_list.py |
| 5.2 | Session groups | models/session.py, main.py |
| 5.3 | Integrate EventBus into SessionManager | session_manager.py |

---

## hydrate.void.sip (Exploration Ideas)

Low-priority but interesting:

1. **AI Session Templates**: Pre-configured prompts for common tasks
2. **Session Snapshots**: Save/restore session state
3. **Remote Sessions**: SSH tunnel to remote tmux
4. **Collaborative Mode**: Share session view (read-only)
5. **Plugin System**: Custom providers, output processors

---

## Success Criteria

The enhancement plan succeeds when:

- [ ] All files under 500 lines
- [x] Exception hierarchy implemented
- [x] Config uses schema dataclass
- [x] Validators extracted from screens
- [x] 300+ tests (328 currently)
- [x] EventBus for service-UI decoupling
- [ ] Session search functional
- [ ] User documentation complete

---

*Generated by claude-opus-4.5 on 2025-12-11*
