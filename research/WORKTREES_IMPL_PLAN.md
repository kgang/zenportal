# Git Worktrees Implementation Plan - Phase 1 MVP

## Overview

Implement core git worktree support for zen-portal, enabling isolated workspaces per Claude session.

**Reference:** See `GIT_WORKTREES_ASSESSMENT.md` for full rationale and alternatives analysis.

---

## Phase 1 Tasks

### 1. Create WorktreeService (`zen_portal/services/worktree.py`)

**New file** following TmuxService pattern.

```python
@dataclass
class WorktreeResult:
    success: bool
    path: Path | None = None
    branch: str = ""
    error: str = ""

@dataclass
class WorktreeInfo:
    path: Path
    branch: str
    commit: str
    is_bare: bool = False

class WorktreeService:
    def __init__(self, source_repo: Path, base_dir: Path | None = None):
        self._source_repo = source_repo
        self._base_dir = base_dir or Path.home() / ".zen-portal" / "worktrees"

    def create_worktree(self, name: str, branch: str | None = None, from_branch: str = "main") -> WorktreeResult
    def remove_worktree(self, path: Path, force: bool = False) -> WorktreeResult
    def list_worktrees(self) -> list[WorktreeInfo]
    def worktree_exists(self, path: Path) -> bool
```

**Tests:** `zen_portal/tests/test_worktree.py`
- Test create with new branch
- Test create from existing branch
- Test remove
- Test list
- Test error handling (not a git repo, branch exists, etc.)

---

### 2. Extend Config System (`zen_portal/services/config.py`)

Add `WorktreeSettings` dataclass:

```python
@dataclass
class WorktreeSettings:
    enabled: bool = False
    base_dir: Path | None = None  # Default: ~/.zen-portal/worktrees
    source_repo: Path | None = None  # Default: resolved working_dir
    auto_cleanup: bool = True
    default_from_branch: str = "main"

    def to_dict(self) -> dict
    @classmethod
    def from_dict(cls, data: dict) -> "WorktreeSettings"
```

Update `FeatureSettings`:
```python
@dataclass
class FeatureSettings:
    working_dir: Path | None = None
    model: ClaudeModel | None = None
    session_prefix: str | None = None
    worktree: WorktreeSettings | None = None  # NEW
```

Update `resolve_features()` to handle worktree settings merge.

**Tests:** Add to `test_config.py`
- Test WorktreeSettings serialization
- Test worktree settings merge across tiers

---

### 3. Extend Session Model (`zen_portal/models/session.py`)

Add worktree fields to `SessionFeatures`:

```python
@dataclass
class SessionFeatures:
    working_dir: Path | None = None
    model: ClaudeModel | None = None
    use_worktree: bool | None = None  # Override config/portal
    worktree_branch: str | None = None  # Specific branch name
```

Add worktree tracking to `Session`:

```python
@dataclass
class Session:
    # ... existing fields ...
    worktree_path: Path | None = None  # Path to worktree if created
    worktree_branch: str | None = None  # Branch name
```

---

### 4. Integrate with SessionManager (`zen_portal/services/session_manager.py`)

Update `__init__`:
```python
def __init__(
    self,
    tmux: TmuxService,
    config_manager: ConfigManager,
    worktree_service: WorktreeService | None = None,  # NEW
    working_dir: Path | None = None,
    on_event: Callable | None = None,
):
```

Update `create_session()`:
1. Resolve worktree settings
2. If worktree enabled, call `WorktreeService.create_worktree()`
3. On success, use worktree path as working_dir
4. On failure, fall back to regular working_dir with warning
5. Store worktree info in Session

Update `prune_session()` and `remove_session()`:
1. If session has worktree_path, call `WorktreeService.remove_worktree()`
2. Handle cleanup errors gracefully

**Tests:** Update `test_session_manager.py`
- Test session creation with worktree
- Test session creation with worktree failure (fallback)
- Test session cleanup removes worktree

---

### 5. Update NewSessionModal (`zen_portal/screens/new_session.py`)

Add UI elements:
- Checkbox: "Create worktree" (default from resolved config)
- Input: "Branch name" (optional, defaults to session name)

Update `NewSessionResult`:
```python
@dataclass
class NewSessionResult:
    name: str
    prompt: str = ""
    features: SessionFeatures | None = None
    # features.use_worktree and features.worktree_branch populated from UI
```

---

### 6. Wire Up in App (`zen_portal/app.py`)

Create `WorktreeService` in `main()` and pass to `SessionManager`:

```python
def main():
    config = ConfigManager()
    resolved = config.resolve_features()

    worktree_service = None
    if resolved.worktree and resolved.worktree.enabled:
        source_repo = resolved.worktree.source_repo or resolved.working_dir
        if source_repo:
            worktree_service = WorktreeService(
                source_repo=source_repo,
                base_dir=resolved.worktree.base_dir,
            )

    manager = SessionManager(
        tmux=tmux,
        config_manager=config,
        worktree_service=worktree_service,
        working_dir=working_dir,
    )
```

---

## File Changes Summary

| File | Change Type |
|------|-------------|
| `zen_portal/services/worktree.py` | **New** |
| `zen_portal/tests/test_worktree.py` | **New** |
| `zen_portal/services/config.py` | Modify |
| `zen_portal/models/session.py` | Modify |
| `zen_portal/services/session_manager.py` | Modify |
| `zen_portal/screens/new_session.py` | Modify |
| `zen_portal/app.py` | Modify |
| `zen_portal/tests/test_config.py` | Modify |
| `zen_portal/tests/test_session_manager.py` | Modify |
| `zen_portal/tests/conftest.py` | Modify (add worktree fixtures) |

---

## Implementation Order

1. **WorktreeService** - Core functionality, can be developed independently
2. **Config extensions** - WorktreeSettings dataclass and serialization
3. **Session model updates** - Add worktree tracking fields
4. **SessionManager integration** - Wire worktree creation/cleanup
5. **UI updates** - Add checkbox and branch input to modal
6. **App wiring** - Connect everything in main()

---

## Acceptance Criteria

- [ ] Can create session with worktree enabled in config
- [ ] Session gets isolated worktree directory
- [ ] Claude Code runs in worktree directory
- [ ] Pruning session removes worktree
- [ ] Worktree creation failure falls back gracefully
- [ ] All existing tests pass
- [ ] New tests for worktree functionality pass

---

## Out of Scope (Phase 2+)

- Session list showing branch names
- Status indicators (dirty, ahead/behind)
- From-branch dropdown in modal
- Orphan worktree cleanup command
- Submodule handling
