# TUI Design Patterns Research

Research findings on TUI best practices from established projects and frameworks.

## Executive Summary

Modern TUIs share common patterns: keyboard-first navigation with discoverability hints, panel-based layouts with clear focus indicators, progressive disclosure of complexity, and context-aware command systems. The best TUIs feel fast because they prioritize perceived responsiveness over feature completeness.

---

## Source Projects Analyzed

| Project | Domain | Key Innovation |
|---------|--------|----------------|
| [Textual](https://textual.textualize.io/) | Framework | CSS-like styling, reactive attributes, web-inspired architecture |
| [k9s](https://k9scli.io/) | Kubernetes | Context-aware shortcuts, resource-type navigation |
| [lazygit](https://github.com/jesseduffield/lazygit) | Git | Multi-panel with consistent behavior, vim-style defaults |
| [btop](https://github.com/aristocratos/btop) | System monitor | Region toggling, ASCII graphs, high information density |
| [htop](https://htop.dev/) | Process viewer | Function key conventions, ncurses patterns |

---

## Pattern 1: Panel-Based Layout

### Observation

All successful TUIs organize information into distinct visual regions ("panels" or "views") that remain consistently positioned.

### lazygit Implementation

```
+----------+----------+
| Status   | Files    |
+----------+----------+
| Branches | Commits  |
+----------+----------+
| Stash    | Preview  |
+----------+----------+
```

- **6 panels** visible simultaneously
- Panels remain visible during most operations
- Clear focus indicator (highlighted border)
- Panel switching via arrow keys or number keys (1-5)

### k9s Implementation

```
+--------------------------------+
| Header (cluster info + hints)  |
+--------------------------------+
| Resource List                  |
|                                |
| (dynamic based on resource)    |
+--------------------------------+
```

- **2 regions**: header and content
- Header adapts to show relevant shortcuts
- Content entirely changes based on resource type
- `:` command mode for resource navigation

### btop Implementation

```
+----------+----------+----------+
| CPU (1)  | Memory(2)| Network(3)|
+----------+----------+----------+
| Disk (d) | Process List (4-5)  |
+----------+----------+----------+
```

- **6 regions** with toggle keys (1-5 + d)
- Each region can be hidden/shown independently
- Provides maximum information density when all shown
- Graceful degradation when regions hidden

### Zen Portal Implication

For a session manager, consider:
- **3-panel layout**: Session list | Session detail | Output preview
- Allow output preview to be toggled for space
- Session list should always be visible for context

---

## Pattern 2: Navigation Models

### Vim-style (lazygit, k9s)

```
Movement:    h/j/k/l  or  arrows
Actions:     single letters (d=delete, e=edit, l=logs)
Command:     : (colon) enters command mode
Search:      / (slash)
Help:        ?
Quit:        q
```

**Pros**: Familiar to developers, efficient once learned
**Cons**: Steeper learning curve, requires memorization

### Function Key style (htop)

```
F1=Help  F2=Setup  F3=Search  F5=Tree  F9=Kill  F10=Quit
```

**Pros**: Discoverable (always visible), no memorization
**Cons**: Requires reaching for function keys, limited slots

### Hybrid (btop)

- Single letters for common actions
- Full mouse support as alternative
- Key hints in header
- Number keys for region toggling

### Recommendation for Zen Portal

Adopt **vim-style with discoverability**:
- `j/k` for list navigation
- `Enter` to select/expand
- `?` for help overlay
- Bottom bar shows context-sensitive hints
- Command palette (Ctrl+P) as escape hatch

---

## Pattern 3: Progressive Disclosure

### Definition

Initially show only essential information. Reveal complexity on demand.

### Implementation Techniques

| Technique | Example | Use Case |
|-----------|---------|----------|
| Accordion | Section headers expand to show details | Hierarchical data |
| Tabs | Multiple views of same data | Different perspectives |
| Drill-down | Select item to see details | Master-detail |
| Toggle regions | Show/hide panels | Customizable density |
| Help overlay | `?` shows all bindings | Discoverability |

### k9s Progressive Disclosure

1. **Level 0**: Resource list (pods, deployments, etc.)
2. **Level 1**: Press Enter to see resource details
3. **Level 2**: Press `l` for logs, `d` for describe
4. **Level 3**: Press `y` for full YAML

### lazygit Progressive Disclosure

1. **Level 0**: Panel overview shows file list
2. **Level 1**: File selected shows diff in preview
3. **Level 2**: Enter on file shows detailed hunk view
4. **Level 3**: `e` opens in editor

### Zen Portal Implication

For Claude sessions:
1. **Level 0**: Session list (name, status, age)
2. **Level 1**: Select session shows recent output snippet
3. **Level 2**: Enter session shows full output stream
4. **Level 3**: `a` attaches to tmux session directly

---

## Pattern 4: Status Communication

### Visual Status Indicators

| Symbol | Meaning | Project |
|--------|---------|---------|
| Colored dot | Status (green=ok, red=error) | k9s |
| Spinner | In progress | Multiple |
| Progress bar | Completion | btop |
| Glyphs | State (checkmark, X, arrow) | lazygit |
| Color bands | Urgency levels | htop |

### btop Status Regions

Each region shows real-time graphs/meters:
- CPU: per-core utilization bars
- Memory: usage bar + swap indicator
- Network: throughput graphs
- Disk: I/O activity

### Zen Portal Implication

For session status:
- `*` = active/growing
- `+` = completed/bloomed
- `-` = error/wilted
- `~` = idle/dormant

Consider a mini status bar per session showing:
```
[*] fix-auth | 5m | CPU: low | Output: 42 lines
```

---

## Pattern 5: Textual-Specific Patterns

### Reactive Attributes

```python
from textual.reactive import reactive

class SessionWidget(Static):
    status = reactive("idle")
    output_lines = reactive(0)

    def watch_status(self, new_status: str) -> None:
        self.add_class(new_status)
```

- Changes trigger automatic re-render
- Watch methods for side effects
- `var=True` for non-rendering reactives

### Unidirectional Data Flow

> "Attributes down, messages up"

- Parent sets child attributes directly
- Child sends messages to parent
- Prevents tangled state

### Data Binding

```python
def compose(self) -> ComposeResult:
    yield SessionDetail()

def on_mount(self) -> None:
    detail = self.query_one(SessionDetail)
    detail.data_bind(SessionList.selected)
```

### CSS Variables (Design Tokens)

```css
$background    /* App background */
$surface       /* Elevated panels */
$primary       /* Accent color */
$text          /* Primary text */
$text-muted    /* Secondary text */
$success       /* Green indicators */
$error         /* Red indicators */
```

### Command Palette

```python
class ZenCommands(Provider):
    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for cmd in self.commands:
            score = matcher.match(cmd.name)
            if score > 0:
                yield Hit(score, cmd.name, cmd.callback)
```

- Fuzzy matching built-in
- Async for expensive searches
- Escape hatch for any action

---

## Pattern 6: Performance Patterns

### Why TUI Speed Matters

> "Terminal users expect TUIs to be fast, because they value speed more than other people. So TUI devs put extra effort towards speed." - Jesse Duffield (lazygit author)

### Techniques

| Technique | Implementation | Benefit |
|-----------|----------------|---------|
| Virtual scrolling | Only render visible rows | Handle 10k+ items |
| Debounced updates | Rate-limit re-renders | Smooth streaming output |
| Background polling | Async status checks | Non-blocking UI |
| Lazy loading | Load details on demand | Fast initial render |

### Textual Performance

```python
# Batch updates
with self.app.batch_update():
    for session in sessions:
        self.add_session(session)

# Worker for background tasks
@work(exclusive=True)
async def poll_sessions(self) -> None:
    while True:
        await self.update_statuses()
        await asyncio.sleep(1)
```

---

## Pattern 7: Error State Handling

### Graceful Degradation

| Scenario | Response |
|----------|----------|
| tmux not installed | Show error, disable session features |
| Session died | Update status, keep in list for review |
| Network timeout | Show cached data with "stale" indicator |
| Permission denied | Clear error message with remediation hint |

### Error Display Patterns

1. **Inline**: Error message replaces expected content
2. **Toast/Notification**: Temporary overlay (Textual's `notify()`)
3. **Status bar**: Persistent error indicator
4. **Modal**: Blocking error requiring acknowledgment

### Recommendation

Use tiered approach:
- **Minor**: Toast notification (auto-dismiss)
- **Recoverable**: Status bar warning + retry hint
- **Fatal**: Modal with clear action (retry/quit)

---

## Pattern 8: Testing Patterns

### Textual Testing

```python
import pytest
from textual.pilot import Pilot

@pytest.mark.asyncio
async def test_session_navigation():
    app = ZenPortal()
    async with app.run_test() as pilot:
        # Simulate key presses
        await pilot.press("j")  # Down
        await pilot.press("enter")  # Select

        # Assert state
        assert app.selected_session is not None
```

### Snapshot Testing

```python
from textual.testing import snapshot

@pytest.mark.asyncio
async def test_visual_regression():
    app = ZenPortal()
    async with app.run_test() as pilot:
        # Compare SVG screenshot
        assert await pilot.snapshot() == expected_svg
```

### Unit Testing Services

```python
def test_garden_plant_seed(mock_subprocess):
    garden = Garden()
    plant = garden.plant_seed("test prompt")

    assert plant.state == PlantState.GROWING
    mock_subprocess.assert_called_with(["tmux", ...])
```

---

## Key Takeaways for Zen Portal

1. **Panel layout**: 2-3 panels with clear focus indicators
2. **Vim-style navigation**: j/k/Enter with `?` help overlay
3. **Progressive disclosure**: List -> Detail -> Full output -> Attach
4. **Status glyphs**: Consistent visual language for session states
5. **Reactive updates**: Use Textual's reactive system for live output
6. **Performance first**: Virtual scroll for sessions, debounce output
7. **Error tiers**: Toast for minor, modal for fatal
8. **Test coverage**: Pilot for integration, mocks for services

---

## Sources

- [Textual Documentation](https://textual.textualize.io/)
- [Textual Reactivity Guide](https://textual.textualize.io/guide/reactivity/)
- [Textual Testing Guide](https://textual.textualize.io/guide/testing/)
- [k9s GitHub](https://github.com/derailed/k9s)
- [k9s Documentation](https://k9scli.io/)
- [lazygit GitHub](https://github.com/jesseduffield/lazygit)
- [Lazygit Turns 5: Musings on Git, TUIs, and Open Source](https://jesseduffield.com/Lazygit-5-Years-On/)
- [btop GitHub](https://github.com/aristocratos/btop)
- [htop](https://htop.dev/)
- [8 TUI Patterns to Turn Python Scripts Into Apps](https://medium.com/@Nexumo_/8-tui-patterns-to-turn-python-scripts-into-apps-ce6f964d3b6f)
- [7 Things I've learned building a modern TUI Framework](https://www.textualize.io/blog/7-things-ive-learned-building-a-modern-tui-framework/)
- [Progressive Disclosure - NN/g](https://www.nngroup.com/articles/progressive-disclosure/)
