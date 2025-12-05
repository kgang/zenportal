# Zen Portal Architecture

## Overview

Zen Portal is a contemplative TUI built with [Textual](https://textual.textualize.io/). It provides a minimal interface for interacting with Claude Code.

## Core Concepts

### AAU Budget System

"Arbitrary Agent Unit" is an attention budget that prevents notification fatigue:

```python
daily_budget: 1.0 AAU
  - pattern nudge: 0.15 AAU
  - assumption check: 0.25 AAU
  - question: 0.10 AAU
  - summary: 0.30 AAU
```

Budget resets daily. The agent queues nudges but only delivers them when:
1. Budget allows the cost
2. User requests reflection (`r` key)

This is **pull-based** by design - the agent suggests, but the developer controls when to receive interruptions.

### Garden Service (tmux integration)

The `Garden` service manages Claude sessions via tmux:

```python
# Plant a seed
tmux new-session -d -s zen-claude-{id} -c {cwd} claude --print "{prompt}"

# Check if session exists
tmux has-session -t zen-claude-{id}

# Capture output
tmux capture-pane -t zen-claude-{id} -p
```

Sessions are named `zen-claude-{8-char-uuid}` for easy identification.

## Module Structure

```
zen_portal/
├── app.py                 # Main App + command palette
├── models/__init__.py     # Dataclasses (Nudge, Session, JournalEntry)
├── agents/
│   └── reflection.py      # AAUBudget + ReflectionAgent
├── services/
│   └── garden.py          # Garden + Plant (tmux integration)
├── screens/
│   ├── ai_prompt.py      # Modal for planting seeds
│   └── help.py           # Key binding reference
└── widgets/
    ├── reflection.py     # Nudge display + budget indicator
    └── status.py         # Session time + AAU bar
```

## Textual Patterns

See `TEXTUAL_PATTERNS.md` for framework patterns reference.

## Design Decisions

### Why tmux?
- True background execution (survives TUI restarts)
- Easy output capture
- Session persistence
- Multiple parallel sessions

### Why AAU budget?
- Prevents notification spam
- Empowers developer control
- Makes interruption cost explicit
- Natural daily reset
