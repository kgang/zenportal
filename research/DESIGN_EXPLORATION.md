# Design Exploration: Multi-Session Claude Code Manager

Creative brainstorm for evolving the Zen Portal prototype into a production-ready session manager.

---

## Design Principles

Before exploring approaches, establish core principles:

| Principle | Meaning | Anti-pattern |
|-----------|---------|--------------|
| **Intuitive** | Understand at a glance | Cryptic symbols, hidden features |
| **Minimal** | Show only what matters | Feature creep, visual noise |
| **Progressive** | Reveal complexity on demand | All-at-once overwhelm |
| **Responsive** | Sub-100ms feedback | Blocking operations, spinners |
| **Keyboard-first** | Efficient without mouse | Mouse-required actions |
| **Zen aesthetic** | Calm, focused, breathing room | Dense dashboards, bright colors |

---

## Approach 1: The Garden (Organic Metaphor)

### Concept

Extend the existing garden metaphor. Sessions are plants that grow, bloom, or wilt. The interface feels like tending a garden rather than managing processes.

### Visual

```
                    zen garden
    ________________________________________________

      sprouting      growing        bloomed
         .            |              *
         .          | | |          * * *
        ---        /__|__\        /--*--\
      seed-01     grow-02        done-03

    ________________________________________________
    [s]eed  [t]end  [p]rune  [w]atch  [?]help
```

### Interaction Model

- `s` - Plant a seed (new session)
- `t` - Tend selected plant (send input)
- `p` - Prune (kill session)
- `w` - Watch (attach to output)
- `j/k` - Move between plants
- Space - Toggle detail view

### Progressive Disclosure

1. **Garden view**: ASCII art overview of all sessions
2. **Plant focus**: Select plant to see recent output
3. **Greenhouse**: Full-screen output streaming
4. **Attach**: Direct tmux attach for intervention

### Strengths

- Unique, memorable experience
- Gentle vocabulary reduces stress
- Natural lifecycle mapping

### Weaknesses

- Metaphor may feel forced for technical users
- ASCII art limits information density
- "Cute" may not suit all workflows

---

## Approach 2: The Dashboard (Data-Dense)

### Concept

Information-rich dashboard inspired by btop/k9s. Maximum visibility into all sessions simultaneously. Professional, utilitarian.

### Visual

```
+-- Sessions (3/10) --------+-- Output ----------------+
| > [*] fix-auth    5m  CPU |  Analyzing codebase...   |
|   [+] add-tests   12m  -- |  Found 3 patterns:       |
|   [-] refactor    2m  ERR |  - Service layer missing |
|                           |  - No input validation   |
+---------------------------+  - Hardcoded config      |
| Status: 2 active, 1 error |                          |
| Budget: 0.45/1.0 AAU      |  > Implementing fix...   |
+---------------------------+--------------------------+
| [n]ew  [k]ill  [a]ttach  [/]filter  [?]help  [q]uit |
+----------------------------------------------------+
```

### Interaction Model

- `n` - New session
- `k` - Kill selected
- `a` - Attach to tmux
- `Enter` - Focus output panel
- `/` - Filter sessions
- `Tab` - Cycle panels
- `1-9` - Quick jump to session

### Progressive Disclosure

1. **Summary row**: Status icon + name + age + indicator
2. **Output panel**: Live stream of selected session
3. **Full screen**: `f` toggles output to full screen
4. **Attach**: `a` leaves TUI, enters tmux

### Strengths

- High information density
- Familiar to k9s/htop users
- Professional appearance

### Weaknesses

- Can feel overwhelming
- Less distinctive/memorable
- Dense UI harder to scan

---

## Approach 3: The Timeline (Temporal)

### Concept

Sessions as events on a timeline. Focus on the temporal aspect of work: what's running now, what ran recently, what completed.

### Visual

```
                     zen timeline
  ________________________________________________

  NOW         5m ago      10m ago     15m ago
   |            |            |            |
   *----------->|            |            |
   fix-auth     |            |            |
                |            |            |
                +----------->*            |
                add-tests (done)          |
                             |            |
                             +---X        |
                             refactor     |
                             (failed)     |
  ________________________________________________
  [n]ew  [j/k]select  [Enter]view  [?]help
```

### Interaction Model

- Timeline scrolls horizontally
- `j/k` moves between session "tracks"
- `h/l` scrolls time
- Current time anchored at left
- Completed sessions fade right

### Progressive Disclosure

1. **Timeline**: Bird's eye view of all sessions
2. **Track focus**: Select track for output preview
3. **Event detail**: Enter for full session view

### Strengths

- Natural representation of concurrent work
- Shows duration visually
- Unique among TUIs

### Weaknesses

- Horizontal scrolling unusual in terminals
- Complex rendering
- May not scale to many sessions

---

## Approach 4: The Minimalist (Zen Extreme)

### Concept

Maximum reduction. Single session focus with seamless switching. Trust the user to hold context.

### Visual

```


                    fix-auth
                   ___________

        Analyzing authentication patterns in
        app/auth/service.py...

        Found: JWT validation missing expiry check



                    * * *

             [j] next   [k] prev   [?] help


```

### Interaction Model

- `j/k` - Cycle through sessions (no list visible)
- Status shown via subtle indicators only
- Help reveals all bindings
- Everything else hidden

### Progressive Disclosure

1. **Single view**: One session at a time
2. **Session picker**: `Ctrl+S` opens session list modal
3. **Full context**: `?` reveals all status

### Strengths

- Maximum focus
- Zen aesthetic
- Trivial to understand

### Weaknesses

- No overview capability
- Hard to track multiple sessions
- May feel too sparse for power users

---

## Approach 5: The Hybrid (Recommended)

### Concept

Combine the best elements:
- Garden metaphor for vocabulary (seeds, plants, pruning)
- Dashboard layout for information density
- Minimal aesthetic for visual calm
- Progressive disclosure for complexity management

### Visual (Default View)

```
  zen portal                              0.45 AAU
  ________________________________________________

   [*] fix-auth          5m    analyzing...
   [+] add-tests        12m    completed
   [-] refactor          2m    error: timeout

  ________________________________________________
  j/k:move  Enter:view  n:new  p:prune  ?:help
```

### Visual (Focused View - Enter)

```
  zen portal > fix-auth                   0.45 AAU
  ________________________________________________

  Analyzing authentication patterns...

  Found 3 issues:
    1. JWT validation missing expiry check
    2. No rate limiting on login endpoint
    3. Password reset token not invalidated

  Implementing fixes...
  ________________________________________________
  Esc:back  a:attach  p:prune  w:water  ?:help
```

### Visual (Attached View - a)

```
  [Leaves TUI, enters tmux session directly]
  [Ctrl+B d to detach back to TUI]
```

### Interaction Model

| Key | Default View | Focused View |
|-----|--------------|--------------|
| `j/k` | Move selection | Scroll output |
| `Enter` | Focus session | N/A |
| `Esc` | N/A | Back to default |
| `n` | New session | New session |
| `p` | Prune selected | Prune current |
| `a` | Attach selected | Attach current |
| `w` | Water selected | Water current |
| `/` | Filter sessions | Search output |
| `?` | Help overlay | Help overlay |
| `q` | Quit | Back to default |

### Progressive Disclosure Levels

```
Level 0: List view
  - Session name, status glyph, age
  - Bottom hint bar

Level 1: Focus view (Enter)
  - Full output stream
  - Session-specific actions

Level 2: Attach (a)
  - Direct tmux interaction
  - Full Claude Code experience

Level 3: Help overlay (?)
  - All keybindings
  - Current AAU budget
  - Session statistics
```

### Status Glyphs

| Glyph | State | Color |
|-------|-------|-------|
| `[*]` | Growing/Active | Default |
| `[+]` | Bloomed/Complete | Green (if supported) |
| `[-]` | Wilted/Error | Red (if supported) |
| `[.]` | Sprouting/Starting | Dim |
| `[~]` | Dormant/Idle | Dim |

### Strengths

- Balances density and calm
- Progressive complexity
- Garden vocabulary without forced ASCII art
- Familiar TUI patterns

---

## Notification Patterns

### Pull-Based (Current)

User explicitly requests updates:
```
[r] to check reflections
```

**Pros**: Never interrupts flow
**Cons**: May miss important events

### Push with Budget (Recommended)

Notifications appear but respect AAU budget:
```
                                    [!] Session complete
```

- Appears in corner, auto-dismisses
- Costs AAU, respects daily budget
- User can disable entirely

### Ambient Indicators

Subtle changes that don't demand attention:
- Status glyph changes color
- Session row highlights briefly
- Sound cue (optional, off by default)

---

## Search and Filter

### Filter Syntax

```
/                    # Enter filter mode
/growing             # Show only growing sessions
/fix                 # Show sessions matching "fix"
/status:error        # Show only error sessions
Esc                  # Clear filter
```

### Command Palette

```
Ctrl+P               # Open command palette
> attach fix-auth    # Fuzzy match commands
> new                # Start new session
> prune all          # Prune all sessions
```

---

## Scaling Considerations

### Many Sessions (10+)

| Count | Adaptation |
|-------|------------|
| 1-5 | Show all in list |
| 6-10 | Show all, enable scrolling |
| 11-20 | Virtual scroll, show count |
| 20+ | Require filter, warn about resource usage |

### Long Output

| Lines | Adaptation |
|-------|------------|
| 0-100 | Show all |
| 100-1000 | Virtual scroll |
| 1000+ | Truncate with "show more" |

### Resource Monitoring

```
Sessions: 5/20 (soft limit)
CPU: Claude processes using 45% combined
Memory: ~500MB allocated
```

---

## Accessibility Considerations

1. **Color independence**: Status conveyed by glyph, not just color
2. **Screen reader**: Meaningful widget labels
3. **High contrast**: Test with limited color palettes
4. **Keyboard only**: All features accessible without mouse

---

## Recommendation Summary

Implement **Approach 5: The Hybrid** with:

1. **Clean list view** as default
2. **Focus view** for output streaming
3. **Direct attach** for full interaction
4. **Garden vocabulary** for actions (plant, prune, water)
5. **Minimal aesthetic** (whitespace, calm colors)
6. **Progressive disclosure** (3 levels)
7. **Pull-based notifications** with optional push

### MVP Features

- [ ] Session list with status glyphs
- [ ] j/k navigation
- [ ] Enter for focus view
- [ ] `n` for new session
- [ ] `p` for prune
- [ ] `a` for attach
- [ ] `?` for help overlay
- [ ] AAU budget display

### V2 Features

- [ ] `/` filter
- [ ] `Ctrl+P` command palette
- [ ] `w` water (send input)
- [ ] Output search
- [ ] Session persistence across TUI restarts

### V3 Features

- [ ] Multi-select operations
- [ ] Session templates
- [ ] Output export
- [ ] Notification push mode
- [ ] Resource monitoring
