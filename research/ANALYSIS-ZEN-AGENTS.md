# Analysis: zen-agents vs zenportal

> Deep reconciliation for zenportal's future direction. December 2025.

---

## Metrics Comparison

| Metric | zenportal | zen-agents |
|--------|-----------|------------|
| Core Python LOC | 17,249 | 6,854 |
| Python files | 88 | 38 |
| Avg LOC/file | 196 | 180 |
| Test coverage | Good | 41 tests |
| Architecture | Service-oriented | Agent-morphism |

zen-agents achieves ~60% code reduction while implementing equivalent functionality.

---

## What zen-agents Does Better

### 1. **Explicit Composition Over Implicit Flow**

**zenportal** (implicit):
```python
def create_session(self, name, prompt, features, session_type):
    # 130 lines mixing validation, worktree, tmux, persistence
    if len(self._sessions) >= MAX: raise ...
    resolved = self._config.resolve_features(...)
    working_dir = resolved.working_dir or ...
    session = Session(...)
    working_dir = self._worktree_mgr.setup_for_session(...)
    binary_error = self._commands.validate_binary(...)
    # ... more inline logic
```

**zen-agents** (explicit pipeline):
```python
NewSessionPipeline = (
    Judge(config)      # validate against principles
    >> Create(config)  # make Session object
    >> Spawn(session)  # create tmux session
    >> Detect(session) # Fix-based polling until stable
)
result = await pipeline.invoke(config)
```

**Learning**: zenportal's `create_session()` is a 130-line monolith. zen-agents decomposes into 4 composable agents, each testable in isolation.

### 2. **Polling as Fixed-Point (Mathematical Abstraction)**

**zenportal** (imperative polling):
```python
def _refresh_single(self, session):
    if session.state != RUNNING: return False
    if not self._tmux.session_exists(tmux_name):
        session.state = COMPLETED; return True
    if self._tmux.is_pane_dead(tmux_name):
        # inline state detection logic
```

**zen-agents** (Fix abstraction):
```python
result = await fix(
    transform=poll_and_detect,
    initial=DetectionState(RUNNING, confidence=0.0),
    equality_check=lambda a, b: a.state == b.state and b.confidence >= 0.8
)
```

**Learning**: Polling IS fixed-point search. Making this explicit:
- Surfaces termination conditions
- Composes with other Fix operations
- Separates "what" from "how"

### 3. **Conflict as Data, Not Exception**

**zenportal**: No formal conflict handling. Name collisions silently work (tmux allows duplicates).

**zen-agents**:
```python
@dataclass
class SessionConflict:
    conflict_type: str  # NAME_COLLISION, PORT_CONFLICT, etc.
    session_a: SessionConfig
    session_b: Session
    suggested_resolution: str

# Detected, presented to user, resolved or held
```

**Learning**: Tensions should be first-class citizens. zenportal could benefit from:
- Name collision detection
- Worktree conflict warnings
- Resource limit soft warnings before hard failure

### 4. **Ground State as Single Source of Truth**

**zenportal**: State scattered across:
- `SessionManager._sessions`
- `ConfigManager` (3-tier cascade)
- `StateService` (disk persistence)
- `TmuxService` (tmux reality)

**zen-agents**:
```python
ZenGround() → ZenGroundState:
    - config_cascade: resolved config
    - sessions: known sessions
    - tmux_facts: actual tmux state
    - preferences: user settings
```

**Learning**: A unified "world model" simplifies reasoning. zenportal's state is coherent but distributed.

### 5. **Principles Embedded in Validation**

**zenportal**: Validation is structural (max sessions, binary exists, path valid).

**zen-agents**:
```python
SESSION_PRINCIPLES = {
    "Tasteful": "Does this session serve a clear purpose?",
    "Curated": "Is another session doing the same thing?",
    "Composable": "Can this session work with others?",
    # ... 6 principles total
}
```

**Learning**: zen-agents validates against values, not just structure. This is philosophically interesting but may be over-engineering for a session manager.

---

## What zenportal Does Better

### 1. **Production Maturity**

- **Battle-tested**: zenportal has real usage, edge case handling
- **Multiple session types**: Claude, Codex, Gemini, OpenRouter, Shell
- **Token tracking**: Sophisticated JSONL parsing, cost estimation
- **Proxy integration**: OpenRouter proxy with y-router/CLIProxyAPI support

zen-agents is a proof-of-concept; zenportal is production software.

### 2. **Rich Token Analytics**

```
tokens  12.5k  (8.2k↓ 4.3k↑)
activity  12 turns · ~1.0k/turn · 15m
cache  2.1k read / 0.5k write (45% hit)
cost  ~$0.32  api
```

zen-agents has no equivalent. This is a zenportal differentiator.

### 3. **Zen AI Quick Queries**

```
/why is @error happening?
```

Context-aware AI assistance with `@output`, `@error`, `@git`, `@session` references. zen-agents doesn't have this.

### 4. **Flexible UI System**

- Grab mode for reordering
- Multiple modal types (new session, config, help, insert)
- Theme system with saved preferences
- Notification system with severity levels

zen-agents has basic UI; zenportal has a polished experience.

### 5. **Git Worktree Integration**

- Automatic isolation per session
- `.env` symlink preservation
- Worktree navigation (`w` to jump)
- Cleanup on session kill

zen-agents mentions worktrees but doesn't implement them.

---

## Architectural Insights from zen-agents

### Insight 1: Services → Agents Mapping

| zenportal Service | zen-agents Agent | Pattern |
|-------------------|------------------|---------|
| `SessionManager.create_session()` | `NewSessionPipeline` | Compose |
| `ConfigManager.resolve_features()` | `ZenGround` | Ground |
| `StateRefresher.refresh()` | `SessionDetect` | Fix |
| `TmuxService.*` | `zen_agents/tmux/*` | Id (pass-through) |
| `SessionPersistence` | `StateSave/StateLoad` | Persistence agents |
| *none* | `SessionContradict/Sublate` | Conflict resolution |

### Insight 2: The Bootstrap Kernel

zen-agents proves that 7 primitives suffice:
1. **Id** - identity/pass-through
2. **Compose** - pipeline construction
3. **Judge** - validation
4. **Ground** - world model
5. **Contradict** - detect conflicts
6. **Sublate** - resolve conflicts
7. **Fix** - stable state search

zenportal uses these implicitly:
- `SessionManager` is implicit Compose
- `ConfigManager` is implicit Ground
- `StateRefresher` is implicit Fix
- No formal Contradict/Sublate

### Insight 3: Heterarchy via Dependency Injection

zen-agents:
```python
def __init__(self, ground=None, capture=None):
    self._ground = ground or zen_ground  # injectable or default
```

zenportal already does this well:
```python
def __init__(self, tmux, config_manager, worktree_service=None, ...):
```

Both support testing via DI. zenportal is already heterarchical.

---

## Recommendations for zenportal

### Keep (zenportal Strengths)

1. **Token tracking system** - unique value proposition
2. **Zen AI queries** - powerful feature
3. **Multi-session-type support** - practical necessity
4. **Current UI/UX polish** - production-ready
5. **Worktree integration** - git isolation is valuable

### Adopt from zen-agents

#### R1: Extract Pipelines from SessionManager (High Value)

**Current**: `create_session()` is 130 lines inline.

**Proposed**: Extract to composable steps:
```python
# services/pipelines/create_session.py
class CreateSessionPipeline:
    def __init__(self, validator, worktree_mgr, tmux, commands):
        self.steps = [
            ValidateConfig(validator),
            SetupWorktree(worktree_mgr),
            BuildCommand(commands),
            SpawnTmux(tmux),
            DetectState(),
        ]

    async def invoke(self, config: SessionConfig) -> SessionResult:
        ctx = config
        for step in self.steps:
            ctx = await step.invoke(ctx)
            if ctx.failed: return ctx
        return ctx
```

**Benefit**: Testable steps, clear flow, easier debugging.

#### R2: Formalize State Detection as Fix (Medium Value)

**Current**: `StateRefresher._refresh_single()` mixes polling with state updates.

**Proposed**: Explicit fixed-point abstraction:
```python
def detect_stable_state(session: Session) -> SessionState:
    """Iterate until state stabilizes."""
    return fix(
        transform=poll_once,
        initial=session.state,
        until_stable=lambda old, new: old == new
    )
```

**Benefit**: Mathematical clarity, testable termination.

#### R3: Add Conflict Detection (Medium Value)

**New**: `services/conflict.py`
```python
@dataclass
class SessionConflict:
    type: str  # "name_collision", "worktree_overlap", "near_limit"
    severity: str  # "warning", "error"
    message: str
    suggestion: str | None

def detect_conflicts(config: SessionConfig, existing: list[Session]) -> list[SessionConflict]:
    conflicts = []
    if any(s.name == config.name for s in existing):
        conflicts.append(SessionConflict("name_collision", "warning", ...))
    if len(existing) >= MAX_SESSIONS - 1:
        conflicts.append(SessionConflict("near_limit", "warning", ...))
    return conflicts
```

**Benefit**: Proactive warnings, better UX.

#### R4: Document Ground State Explicitly (Low Effort, High Clarity)

Add to HYDRATE.md or new `ARCHITECTURE.md`:
```
## Ground State (World Model)

zenportal's ground state is:
- ConfigManager: resolved config (session > portal > config > defaults)
- SessionManager._sessions: known sessions
- TmuxService: tmux reality (actual running sessions)
- StateService: persisted state on disk

All operations should read from ground state, not cache local copies.
```

**Benefit**: Clarity for future development.

### Do NOT Adopt

1. **Full agent-morphism architecture** - Over-engineering for zenportal's scope
2. **Principle-based validation** - Philosophical; adds complexity without clear benefit
3. **Explicit Contradict/Sublate** - Simple conflict detection suffices
4. **kgents-bootstrap dependency** - Adds framework dependency

---

## Vision: zenportal 2.0

**Identity**: Contemplative TUI for managing AI assistant sessions in parallel.

**Architecture**:
```
zen_portal/
├── app.py                    # entry point (unchanged)
├── models/                   # data types (unchanged)
├── services/
│   ├── session_manager.py    # orchestrates pipelines (slimmed)
│   ├── pipelines/            # NEW: composable workflows
│   │   ├── create.py         # create session pipeline
│   │   ├── revive.py         # revive session pipeline
│   │   └── tick.py           # state refresh pipeline
│   ├── conflict.py           # NEW: conflict detection
│   ├── core/                 # extracted managers (existing)
│   └── ...                   # existing services
├── widgets/                  # (unchanged)
├── screens/                  # (unchanged)
└── tests/
    └── pipelines/            # NEW: pipeline tests
```

**Key Changes**:
1. `SessionManager` becomes orchestrator, not implementor
2. Pipelines are explicit, testable, composable
3. Conflict detection warns before failure
4. Ground state documented but not refactored (keep what works)

**Migration Path**:
1. Extract `create_session()` into pipeline (breaking up the monolith)
2. Add conflict detection with soft warnings
3. Refactor `StateRefresher` to use Fix abstraction (optional)
4. Keep all existing features intact

---

## Summary

| Category | zenportal | zen-agents | Recommendation |
|----------|-----------|------------|----------------|
| Code size | 17k LOC | 6.8k LOC | Extract pipelines |
| Architecture | Service | Agent-morphism | Partial adoption |
| State model | Distributed | Unified Ground | Document, don't refactor |
| Conflict handling | None | First-class | Add detection |
| Token tracking | Excellent | None | Keep |
| UI polish | Production | Basic | Keep |
| Session types | 5 | 5 | Keep |
| Worktree integration | Full | Stub | Keep |

**Bottom line**: zenportal is the better product. zen-agents is the cleaner architecture.

Adopt zen-agents' **pipeline composition** and **conflict detection** patterns while keeping zenportal's **feature richness** and **production maturity**. The result: a more maintainable zenportal with no feature regression.
