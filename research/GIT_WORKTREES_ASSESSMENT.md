# Git Worktrees Integration Assessment for Zen Portal

## Executive Summary

This document assesses the feasibility and value of incorporating git worktrees into zen-portal, a TUI application for managing multiple Claude Code sessions via tmux. The assessment concludes that **worktrees would be a high-value addition** that naturally complements the multi-session workflow, with a recommended phased implementation approach.

---

## 1. What Are Git Worktrees?

Git worktrees allow you to check out multiple branches of a repository simultaneously in different directories, all sharing the same `.git` directory. This enables parallel work without cloning the repository multiple times.

**Key characteristics:**
- Each worktree is a separate directory with a full working copy
- All worktrees share the same git history and objects
- Changes in one worktree don't affect uncommitted work in others
- Worktrees can be easily created and deleted

**Basic commands:**
```bash
# Create a worktree for a new branch
git worktree add ../feature-x -b feature-x

# Create a worktree from existing branch
git worktree add ../bugfix-y bugfix-y

# List all worktrees
git worktree list

# Remove a worktree
git worktree remove ../feature-x
```

---

## 2. Integration Scenarios

### 2.1 How Worktrees Enhance Multi-Session Workflow

The current zen-portal architecture allows sessions to specify a working directory, but multiple sessions pointing to the same directory can cause conflicts when Claude makes concurrent changes. Worktrees solve this elegantly:

| Current State | With Worktrees |
|--------------|----------------|
| Multiple sessions may edit same files | Each session gets isolated workspace |
| Git conflicts from concurrent work | No conflicts - separate working copies |
| Manual branch management | Automatic branch-per-session option |
| Difficult to track which session is on which branch | Clear mapping: session = worktree = branch |

**Natural fit:** Zen-portal's garden metaphor (sprout, grow, bloom, wilt) maps beautifully to worktrees:
- **Sprout**: Create worktree + session
- **Grow**: Claude works in isolated worktree
- **Bloom**: Work complete, ready to merge
- **Wilt**: Clean up worktree

### 2.2 Automatic Worktree Per Session

**Proposed flow:**
```
User creates session "fix-auth-bug"
  |
  v
Zen-portal creates worktree:
  git worktree add ~/.zen-portal/worktrees/fix-auth-bug-abc123 -b fix-auth-bug
  |
  v
Session working_dir = ~/.zen-portal/worktrees/fix-auth-bug-abc123
  |
  v
Claude Code runs in isolated worktree
```

**Worktree naming convention:**
```
~/.zen-portal/worktrees/{session-name}-{session-id-short}/
```

### 2.3 Integration with 3-Tier Config System

The current config hierarchy:
```
session > portal > config > system defaults
```

Proposed extension for worktrees:

| Tier | Setting | Description |
|------|---------|-------------|
| Config | `worktree.enabled` | Global default (true/false) |
| Config | `worktree.base_dir` | Where to create worktrees |
| Config | `worktree.auto_cleanup` | Delete on session remove |
| Portal | `worktree.enabled` | Override for this project |
| Portal | `worktree.source_repo` | Base repo for worktrees |
| Session | `worktree.enabled` | Per-session override |
| Session | `worktree.branch` | Specific branch to use |

**Example config.json:**
```json
{
  "features": {
    "working_dir": "/Users/me/projects",
    "worktree": {
      "enabled": false,
      "base_dir": "~/.zen-portal/worktrees",
      "auto_cleanup": true
    }
  }
}
```

**Example portal.json (project-specific):**
```json
{
  "features": {
    "working_dir": "/Users/me/projects/agent_services",
    "worktree": {
      "enabled": true,
      "source_repo": "/Users/me/projects/agent_services"
    }
  },
  "description": "Working on agent_services with worktrees"
}
```

---

## 3. Benefits

### 3.1 Problems Solved

| Problem | How Worktrees Solve It |
|---------|----------------------|
| **Concurrent edit conflicts** | Each session has isolated working copy |
| **Lost context on branch switch** | No switching - parallel branches |
| **Dirty state blocking work** | Uncommitted changes stay in their worktree |
| **"Which session is on which branch?"** | 1:1 mapping of session to worktree/branch |
| **Fear of parallel experiments** | Create worktrees freely, delete if unneeded |

### 3.2 Developer Experience Improvements

1. **Fearless parallelism**: Start multiple Claude sessions working on different features simultaneously without coordination overhead

2. **Clean mental model**: Session = isolated workspace = branch. No confusion about shared state.

3. **Easy comparison**: Open two tmux sessions side-by-side, each in its own worktree, to compare approaches

4. **Reduced context switching cost**: Don't need to stash/commit before jumping to another task - just create a new session

5. **Better Claude utilization**: Claude can work uninterrupted without worrying about stepping on other sessions' changes

6. **Natural PR workflow**: Each session/worktree maps to a PR; clean separation of concerns

---

## 4. Challenges and Risks

### 4.1 Complexity Added

| Area | Complexity Increase |
|------|-------------------|
| Session creation | Moderate - add worktree creation step |
| Session cleanup | Moderate - need worktree removal logic |
| UI | Low - minimal changes needed |
| Configuration | Moderate - new settings tier |
| Error handling | High - many git edge cases |

### 4.2 Edge Cases

**Submodules:**
- Worktrees don't automatically set up submodules
- Need explicit `git submodule update --init` after worktree creation
- Could cause confusion if Claude expects submodule code

**Dirty state on source repo:**
- Can create worktree from dirty repo, but certain operations may fail
- Need to handle gracefully

**Worktree pointing to same branch:**
- Git prevents two worktrees on the same branch
- Need to detect and handle this case

**Disk space:**
- Each worktree uses disk space for working copy
- Not as much as full clone (shared objects), but still meaningful for large repos
- Need cleanup strategy

**Locked worktrees:**
- If zen-portal crashes, worktrees may remain
- Need orphan detection and cleanup

### 4.3 User Mental Model Changes

| Current Model | New Model |
|---------------|-----------|
| Session = tmux session | Session = tmux session + worktree |
| Working dir is shared | Working dir is isolated |
| Changes persist after session ends | Changes in worktree need merge/push |
| Simple cleanup | Cleanup includes git operations |

**Risk mitigation:** Make worktrees opt-in initially, with clear documentation.

---

## 5. Implementation Approach

### 5.1 New Service: WorktreeService

**Location:** `/zen_portal/services/worktree.py`

**Responsibilities:**
- Create worktrees for sessions
- List existing worktrees
- Remove worktrees (with safety checks)
- Handle git errors gracefully
- Track worktree-to-session mapping

**Interface sketch:**
```python
@dataclass
class WorktreeResult:
    success: bool
    path: Path | None = None
    branch: str = ""
    error: str = ""

class WorktreeService:
    def __init__(self, base_dir: Path, source_repo: Path):
        ...

    def create_worktree(
        self,
        name: str,
        branch: str | None = None,  # None = create new branch
        from_branch: str = "main",
    ) -> WorktreeResult:
        """Create a new worktree, optionally with new branch."""
        ...

    def remove_worktree(
        self,
        path: Path,
        force: bool = False,
    ) -> WorktreeResult:
        """Remove a worktree. Force ignores uncommitted changes."""
        ...

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all worktrees for the source repo."""
        ...

    def get_worktree_status(self, path: Path) -> WorktreeStatus:
        """Check for uncommitted changes, ahead/behind, etc."""
        ...

    def cleanup_orphans(self) -> list[Path]:
        """Find and remove worktrees without active sessions."""
        ...
```

### 5.2 SessionManager Integration

Modify `SessionManager.create_session()`:

```python
def create_session(
    self,
    name: str,
    prompt: str = "",
    features: SessionFeatures | None = None,
) -> Session:
    # ... existing code ...

    # If worktree enabled, create one
    if resolved.worktree_enabled and self._worktree_service:
        wt_result = self._worktree_service.create_worktree(
            name=f"{name}-{session.id[:8]}",
            branch=features.worktree_branch if features else None,
        )
        if wt_result.success:
            # Override working_dir with worktree path
            working_dir = wt_result.path
            session.worktree_path = wt_result.path
            session.worktree_branch = wt_result.branch
        else:
            # Fall back to regular working dir, log warning
            self._log_warning(f"Worktree creation failed: {wt_result.error}")

    # ... rest of session creation ...
```

Modify cleanup methods to handle worktree removal.

### 5.3 UI Changes

**NewSessionModal additions:**

| New Field | Description |
|-----------|-------------|
| `[x] Create worktree` | Checkbox (default from resolved config) |
| `Branch name` | Optional - defaults to session name |
| `From branch` | Dropdown: main, current, or type custom |

**Session list enhancements:**

| Current Display | Enhanced Display |
|-----------------|-----------------|
| `* fix-auth-bug 5m` | `* fix-auth-bug [feature/fix-auth] 5m` |

**Status indicators for worktree state:**
- `!` - has uncommitted changes
- `^` - ahead of remote
- `v` - behind remote

### 5.4 Configuration Schema Extensions

**FeatureSettings updates:**
```python
@dataclass
class WorktreeSettings:
    enabled: bool = False
    base_dir: Path | None = None  # Default: ~/.zen-portal/worktrees
    source_repo: Path | None = None  # Default: portal working_dir
    auto_cleanup: bool = True
    default_from_branch: str = "main"

@dataclass
class FeatureSettings:
    working_dir: Path | None = None
    model: ClaudeModel | None = None
    session_prefix: str | None = None
    worktree: WorktreeSettings | None = None  # NEW
```

**SessionFeatures updates:**
```python
@dataclass
class SessionFeatures:
    working_dir: Path | None = None
    model: ClaudeModel | None = None
    use_worktree: bool | None = None  # Override config/portal setting
    worktree_branch: str | None = None  # Specific branch name
```

---

## 6. Alternatives Considered

### 6.1 Containers (Docker)

**Approach:** Each session runs Claude in a container with its own filesystem.

| Pros | Cons |
|------|------|
| Complete isolation | Heavy resource usage |
| Consistent environment | Complexity of container orchestration |
| Can include dev tools | Slower startup |
| | Requires Docker installed |
| | Volume mounting complexity |

**Verdict:** Overkill for the isolation needed. Git worktrees are lightweight and git-native.

### 6.2 Branch Switching

**Approach:** Each session stashes, switches branch, works, then switches back.

| Pros | Cons |
|------|------|
| No new concepts | Only one session can be active |
| Works today | Stash conflicts possible |
| No disk overhead | Poor UX for parallel work |
| | Context loss between switches |

**Verdict:** Doesn't enable parallel work, which is the core zen-portal value proposition.

### 6.3 Multiple Clones

**Approach:** Each session works in a separate full clone of the repo.

| Pros | Cons |
|------|------|
| Complete isolation | Massive disk usage |
| Simple mental model | No shared history |
| | Slow to create |
| | Hard to keep in sync |
| | Submodules need separate init |

**Verdict:** Worktrees provide the same isolation with shared objects, much lighter weight.

### 6.4 Directory Copies (rsync)

**Approach:** Copy the repo directory for each session.

| Pros | Cons |
|------|------|
| Simple | Large disk usage |
| No git dependency | No git integration |
| | Changes are orphaned |
| | No branch concept |

**Verdict:** Loses all git benefits. Not suitable for development workflows.

### Why Worktrees Win

| Criterion | Worktrees | Containers | Branch Switch | Clones | Copies |
|-----------|-----------|------------|---------------|--------|--------|
| Isolation | Good | Excellent | Poor | Excellent | Good |
| Resource usage | Low | High | None | High | Medium |
| Git integration | Native | Separate | Native | Separate | None |
| Startup speed | Fast | Slow | Instant | Slow | Medium |
| Parallel work | Yes | Yes | No | Yes | Yes |
| Complexity | Low | High | Low | Low | Low |

---

## 7. Recommendation

### Should This Be Implemented?

**Yes.** Git worktrees are a natural fit for zen-portal's multi-session model:

1. **Core value alignment:** Zen-portal is about managing parallel Claude sessions. Worktrees directly enable truly parallel, isolated work.

2. **Low additional complexity:** The WorktreeService is a thin wrapper around git commands, similar to the existing TmuxService pattern.

3. **User demand:** Anyone using zen-portal for serious development work will quickly hit the "two sessions editing the same file" problem.

4. **Graceful degradation:** If worktree creation fails, fall back to shared working directory with a warning. No blocking failures.

5. **Garden metaphor fit:** Sessions naturally map to worktrees, enhancing the existing design philosophy.

### MVP Scope

**Phase 1: Core Worktree Support (MVP)**
- [ ] `WorktreeService` with create/remove/list
- [ ] Integration with `SessionManager`
- [ ] Config system extension (config/portal level)
- [ ] Basic UI: checkbox in new session modal
- [ ] Auto-cleanup on session remove
- [ ] Error handling and fallback

**Phase 2: Enhanced UX**
- [ ] Session list shows branch name
- [ ] Status indicators (dirty, ahead/behind)
- [ ] From-branch selection in modal
- [ ] Orphan worktree detection and cleanup command
- [ ] Help screen updates

**Phase 3: Advanced Features**
- [ ] Session-level worktree override
- [ ] Bulk worktree cleanup command
- [ ] Worktree status view (git status for all worktrees)
- [ ] Integration with git hooks
- [ ] Submodule handling

### Estimated Effort

| Phase | Effort | Complexity |
|-------|--------|------------|
| Phase 1 (MVP) | 2-3 days | Medium |
| Phase 2 | 1-2 days | Low |
| Phase 3 | 2-3 days | Medium |

### Risks to Monitor

1. **Disk space accumulation:** Implement cleanup reminders or automatic cleanup
2. **User confusion:** Clear documentation and in-app help
3. **Git edge cases:** Comprehensive error handling with user-friendly messages
4. **Submodule support:** May need explicit handling, document limitations initially

---

## 8. Appendix: Technical Details

### Git Worktree Commands Reference

```bash
# Create worktree with new branch from main
git worktree add /path/to/worktree -b new-branch main

# Create worktree from existing branch
git worktree add /path/to/worktree existing-branch

# List worktrees (machine-readable)
git worktree list --porcelain

# Remove worktree
git worktree remove /path/to/worktree

# Force remove (ignores uncommitted changes)
git worktree remove --force /path/to/worktree

# Prune stale worktree references
git worktree prune
```

### Worktree Directory Structure

```
~/.zen-portal/
├── worktrees/
│   ├── fix-auth-bug-a1b2c3d4/     # Session worktree
│   │   ├── .git (file pointing to main repo)
│   │   └── ... (working copy)
│   ├── add-feature-x-e5f6g7h8/
│   │   └── ...
│   └── .metadata/                  # Worktree tracking
│       └── sessions.json
└── config/
    ├── config.json
    └── portal.json
```

### Session-Worktree Mapping

```json
// ~/.zen-portal/worktrees/.metadata/sessions.json
{
  "mappings": [
    {
      "session_id": "a1b2c3d4-...",
      "worktree_path": "/Users/me/.zen-portal/worktrees/fix-auth-bug-a1b2c3d4",
      "branch": "feature/fix-auth-bug",
      "source_repo": "/Users/me/projects/agent_services",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

## 9. Conclusion

Git worktrees are a compelling addition to zen-portal that would significantly enhance its value proposition for parallel development workflows. The implementation is tractable, aligns with existing architecture patterns, and provides graceful degradation when worktrees aren't available or desired.

**Recommended next steps:**
1. Validate this assessment with stakeholders
2. Implement Phase 1 MVP
3. Gather user feedback before Phase 2

---

*Assessment created: 2024-12-04*
*Author: argonaut agent*
