# Token Drains: Lowest-Priority Context Utilization

> Research on leveraging "would-be-wasted" tokens for background tasks. December 2025.

---

## Problem Statement

Modern LLM applications face a fundamental tension:

1. **Context windows are finite** - Claude Opus 4.5 has a 200k token limit
2. **Context is expensive** - Tokens cost money and degrade performance
3. **Context is often underutilized** - Many sessions don't use full capacity
4. **Context resets are wasteful** - Starting new sessions discards potential value

**Core question**: Can we repurpose "leftover" token budget for low-priority background tasks without impacting primary workflows?

---

## Concept: Lowest-Priority Token Drains

A **token drain** is a mechanism that consumes unused token capacity for tasks that:

- Have **no time constraints** (can be delayed indefinitely)
- Generate **ambient value** (nice-to-have, not mission-critical)
- Are **interruptible** (can be paused/stopped at any moment)
- Respect **donor preferences** (customizable, opt-in)

Think: garbage collection for tokens, or power-saving mode for computing.

---

## Real-World Analogies

| Domain | Analogy | Mechanism |
|--------|---------|-----------|
| **Computing** | Idle CPU cycles | SETI@home, Folding@home (donate spare compute) |
| **Memory** | Garbage collection | Reclaim unused memory during idle periods |
| **Power** | Sleep mode | Lower power state when not in active use |
| **Economics** | Micro-donations | Round-up spare change to charity |
| **Bandwidth** | Background sync | Download updates when network is idle |

**Pattern**: Opportunistically use surplus resources for low-priority tasks.

---

## Architecture Patterns

### Pattern 1: Funnel Design (Universal Drain)

All sessions donate to a **shared token pool** that services background tasks.

```
Session A (10k unused) ─┐
Session B (5k unused)  ─┼──> Universal Token Pool ──> Background Tasks
Session C (20k unused) ─┘       (35k available)        - Summarization
                                                        - Code review
                                                        - Documentation
```

**Pros**:
- Simple implementation
- Efficient pooling
- Predictable behavior

**Cons**:
- Loss of donor control
- Generic tasks may not align with session context
- Privacy concerns (cross-session data)

### Pattern 2: Customized Drains (Per-Session)

Each session defines **custom drain behaviors** aligned with its purpose.

```
Session A (Claude Code)
  └─> Drain: "Review my recent commits when idle"

Session B (Data Analysis)
  └─> Drain: "Explore dataset correlations in background"

Session C (Writing)
  └─> Drain: "Generate outline expansions for drafts"
```

**Pros**:
- Context-aware tasks
- User control over drain behavior
- Privacy preserved (session-scoped)

**Cons**:
- Complex configuration
- Requires per-session drain definitions
- Less efficient (can't pool resources)

### Pattern 3: Hybrid (Tiered Drains)

Combine funnel + customization with **priority tiers**.

```
Session Token Budget (200k)
├─ [Tier 0] Active work (primary use)         → 0-150k
├─ [Tier 1] Session-specific drains (custom)  → 150k-180k
└─ [Tier 2] Universal drains (funnel)         → 180k-200k
```

**Behavior**:
1. Primary work always gets priority (Tier 0)
2. Session-specific drains activate when Tier 1 budget available
3. Universal drains consume remaining capacity (Tier 2)

**Example**:
- Session using 80k tokens → 70k available for custom drains, 20k for universal
- Session using 170k tokens → 10k for custom, 0k for universal
- Session using 50k tokens → 130k for custom, 20k for universal

---

## Token Drain Types

### 1. Session Reflection Drains

**Purpose**: Analyze session behavior to improve future work.

**Examples**:
- "What patterns emerge from my git commits?"
- "Which files do I edit most frequently?"
- "Are there recurring errors I should fix?"

**Value**: Meta-learning, gradual improvement.

### 2. Code Maintenance Drains

**Purpose**: Background code hygiene.

**Examples**:
- "Find unused imports across the codebase"
- "Identify functions that could be simplified"
- "Suggest test coverage improvements"

**Value**: Technical debt reduction.

### 3. Documentation Drains

**Purpose**: Auto-generate or improve docs.

**Examples**:
- "Generate docstrings for undocumented functions"
- "Update README with recent feature additions"
- "Create architecture diagrams from code structure"

**Value**: Improved onboarding, reduced context load.

### 4. Exploration Drains

**Purpose**: Discover interesting patterns or insights.

**Examples**:
- "What are the most complex modules in this project?"
- "Are there security vulnerabilities I should know about?"
- "Which dependencies could be upgraded?"

**Value**: Proactive discovery, preventive maintenance.

### 5. Learning Drains

**Purpose**: Extract reusable knowledge.

**Examples**:
- "What coding patterns do I prefer?"
- "Which libraries do I use most often?"
- "What are my common git commit message styles?"

**Value**: Personalized AI assistance over time.

---

## Implementation Strategies

### Strategy 1: Opportunistic Polling

**Mechanism**: Periodically check for unused tokens and trigger drains.

```python
class TokenDrainManager:
    POLL_INTERVAL = 60  # seconds
    MIN_DRAIN_TOKENS = 10_000  # minimum tokens to activate drain

    async def poll_and_drain(self, session: Session):
        """Check if session has unused tokens and activate drains."""
        used = session.token_stats.total if session.token_stats else 0
        limit = session.token_limit or 200_000
        available = limit - used

        if available >= self.MIN_DRAIN_TOKENS:
            await self._activate_drain(session, budget=available)
```

**Triggers**:
- Session is idle (no new messages for N minutes)
- Session completes primary task
- User explicitly invokes drain

### Strategy 2: Proactive Reservation

**Mechanism**: Reserve token budget upfront for drains.

```python
class SessionConfig:
    primary_budget: int = 180_000    # 90% for main work
    drain_budget: int = 20_000       # 10% reserved for drains
    drain_tasks: list[DrainTask]     # what to run
```

**Benefits**:
- Predictable behavior
- No surprise token consumption
- Clear separation of concerns

### Strategy 3: Deferred Execution Queue

**Mechanism**: Queue drain tasks to run after session completes.

```python
@dataclass
class DrainTask:
    description: str
    priority: int
    token_budget: int
    session_context: dict  # captured from session

class DrainQueue:
    async def enqueue(self, task: DrainTask):
        """Add task to queue, execute when capacity available."""
        self._queue.append(task)

    async def process(self):
        """Run queued tasks with available tokens."""
        while self._queue and self._has_capacity():
            task = self._queue.pop(0)
            await self._execute_drain(task)
```

**Benefits**:
- No interference with active sessions
- Can accumulate tasks across multiple sessions
- Run drains in batch for efficiency

---

## Zenportal Integration Points

### 1. Token Tracking Enhancement

Currently, zenportal tracks token usage:

```
tokens  12.5k  (8.2k↓ 4.3k↑)
```

**Enhancement**: Show drain allocation and activity:

```
tokens  12.5k / 200k  (8.2k↓ 4.3k↑)
drain   2.1k consumed  ·  3 tasks pending
```

### 2. Drain Configuration UI

Add drain settings to session config screen:

```
[Drains]
  ☑ Enable token drains
  Budget: [20000] tokens

  Custom drains:
    ☑ Review recent commits
    ☑ Find unused imports
    ☐ Generate docstrings

  Universal drains:
    ☑ Contribute to shared pool
```

### 3. Drain Task Viewer

New modal to view drain results:

```
Press `D` to view drain tasks

Recent Drain Tasks:
  ● Review commits     · completed · 1.2k tokens · 5m ago
  ● Find unused        · running   · 0.8k tokens · 2m ago
  ○ Generate docs      · pending   · ~2k tokens
```

### 4. Zen AI Drain Queries

Use `/` Zen AI with drain-specific prompts:

```
/drain analyze my session patterns
/drain what improvements can you suggest?
/drain find technical debt in my code
```

---

## Token Accounting Model

### Drain Budget Calculation

```python
def calculate_drain_budget(session: Session) -> int:
    """Calculate available budget for drains."""
    # Base limit (200k for Opus 4.5)
    base_limit = get_token_limit(session.model)

    # Current usage
    used = session.token_stats.total if session.token_stats else 0

    # Safety margin (keep 10% buffer)
    safety_margin = int(base_limit * 0.1)

    # Available for drains
    available = base_limit - used - safety_margin

    return max(0, available)
```

### Priority-Based Allocation

```python
@dataclass
class DrainPriority:
    CRITICAL = 0   # Primary work (never drain)
    HIGH = 1       # Session-specific drains
    MEDIUM = 2     # Shared drains
    LOW = 3        # Universal background tasks

class TokenAllocator:
    def allocate(self, budget: int) -> dict[DrainPriority, int]:
        """Allocate tokens across priority tiers."""
        return {
            DrainPriority.HIGH: int(budget * 0.7),    # 70% to custom
            DrainPriority.MEDIUM: int(budget * 0.2),  # 20% to shared
            DrainPriority.LOW: int(budget * 0.1),     # 10% to universal
        }
```

---

## Privacy and Safety Considerations

### 1. Opt-In by Default

Drains should be **explicitly enabled** by users, not automatic.

```python
class DrainConfig:
    enabled: bool = False  # default: OFF
    require_confirmation: bool = True
    max_budget_per_drain: int = 5000
```

### 2. Session Isolation

Drains should **not cross session boundaries** unless explicitly configured.

- Session A's drains cannot access Session B's context
- Universal drains operate on aggregated, anonymized data only
- User can opt-in to cross-session drains (e.g., "analyze all my Python sessions")

### 3. Cost Transparency

Users should see **clear cost reporting** for drains.

```
Drain Activity (Last 7 Days):
  Tokens consumed: 45.2k
  Estimated cost:  $0.18
  Tasks completed: 12

  Top drains:
    1. Commit review     · 12.1k tokens · $0.05
    2. Code analysis     · 8.3k tokens  · $0.03
    3. Doc generation    · 7.2k tokens  · $0.03
```

### 4. Interrupt Mechanisms

Drains must be **immediately stoppable**.

```python
class DrainTask:
    async def execute(self):
        """Execute drain with cancellation support."""
        try:
            async with self._cancellation_token:
                result = await self._run()
        except DrainCancelled:
            self._cleanup()
```

---

## Cost-Benefit Analysis

### Costs

1. **Token consumption**: Drains use tokens that could be saved
2. **Complexity**: Additional code, configuration, UI
3. **Maintenance**: Managing drain tasks, queue, results
4. **Risk**: Potential for runaway token usage if misconfigured

### Benefits

1. **Ambient improvement**: Continuous background work without user effort
2. **Value extraction**: Leverage sunk costs (active sessions already paid for)
3. **Learning**: Build personalized insights over time
4. **Proactive discovery**: Find issues before they become critical

### Break-Even Analysis

**Scenario**: User has 5 active sessions per day, each using 50k/200k tokens.

- **Unused capacity**: 150k tokens/session × 5 sessions = 750k tokens/day
- **Drain allocation**: 10% = 75k tokens/day
- **Cost**: ~$0.30/day (at $4/M tokens for Opus)
- **Value**: If drains find 1 bug, save 1 hour of debugging → $30+ value

**ROI**: If drains provide value 1% of the time, they pay for themselves.

---

## Recommendation for Zenportal

### Phase 1: MVP (Minimal Viable Product)

**Goal**: Prove value with simplest possible implementation.

**Features**:
1. Track unused token capacity per session
2. Add single universal drain: "Session reflection"
3. Manual trigger only (user presses `D` to activate drain)
4. Display drain results in modal

**Implementation**:
- `services/drain.py` - core drain logic (~200 lines)
- `screens/drain_modal.py` - view results (~150 lines)
- Update `TokenManager` to track available budget (~50 lines)

**Success criteria**: Users find drain results useful enough to trigger manually.

### Phase 2: Customization

**Goal**: Allow user-defined drains.

**Features**:
1. Drain configuration in session config
2. Multiple drain types (reflection, code review, docs)
3. Automatic triggering when idle
4. Priority-based allocation

**Implementation**:
- `models/drain.py` - drain task dataclasses (~100 lines)
- Extend `services/drain.py` - custom drains (~200 lines)
- UI for drain config (~150 lines)

### Phase 3: Ecosystem

**Goal**: Build drain marketplace.

**Features**:
1. Shareable drain templates
2. Community drain library
3. Drain analytics (ROI tracking)
4. Cross-session drains (with opt-in)

**Implementation**:
- Plugin system for custom drains
- Drain marketplace UI
- Analytics dashboard

---

## Open Questions

1. **Threshold tuning**: What's the minimum token budget to make drains worthwhile? (10k? 20k?)
2. **Interruption policy**: Should drains auto-cancel when user activity resumes?
3. **Result persistence**: Where to store drain outputs? (session metadata? separate files?)
4. **Cross-session learning**: How to aggregate insights without violating privacy?
5. **Drain composition**: Can drains chain together? (e.g., "analyze code" → "generate docs")

---

## Related Work

### LLM Context Management

Modern LLM applications use several techniques to manage context:

1. **Session Management**: Start new sessions for new tasks, clearing context window
2. **Memory Optimization**: Pull only relevant exchanges based on current query (20-40% token reduction)
3. **Truncation and Chunking**: Split large texts, retrieve only relevant sections via vector search
4. **Compression**: Natural language is verbose; LLMs can understand compressed prompts

Source: [LLM Context Management Guide](https://eval.16x.engineer/blog/llm-context-management-guide)

### Anthropic Token Limits (2025)

- Claude Opus 4.5: 200k token context window
- Output limit: 32k tokens (default), 128k for Claude 3.7 Sonnet with beta header
- Rate limits: Token bucket algorithm (continuous replenishment)
- Cache-aware limits: Cached tokens don't count toward ITPM on Claude 3.7 Sonnet

Sources:
- [Claude Rate Limits Documentation](https://docs.claude.com/en/api/rate-limits)
- [Token-Saving Updates on Anthropic API](https://www.anthropic.com/news/token-saving-updates)
- [Claude Context Window 2025 Rules](https://www.datastudios.org/post/claude-context-window-token-limits-memory-policy-and-2025-rules)

### Token Optimization Strategies

Industry best practices:

1. **Smart Routing**: Route simple queries to cheaper models (Haiku), complex to Opus
2. **Prompt Caching**: Cache static context (system prompts, docs) to reduce input tokens
3. **Context Pruning**: Remove redundant information from chat history
4. **Batch Processing**: Combine multiple queries to amortize fixed costs

Sources:
- [LLM Cost Optimization via Smart Routing](https://www.kosmoy.com/post/llm-cost-management-stop-burning-money-on-tokens)
- [Token Budgeting for Long-Context Apps](https://dev.co/ai/token-budgeting-strategies-for-long-context-llm-apps)

---

## Conclusion

**Lowest-priority token drains** represent a novel approach to extracting value from underutilized LLM capacity. By treating unused tokens as an opportunity rather than waste, we can:

1. Generate **ambient improvements** (code quality, docs, insights)
2. Leverage **sunk costs** (sessions already paid for)
3. Enable **background learning** (personalized assistance over time)

The key design principles:

- **Opt-in**: Users must explicitly enable drains
- **Customizable**: Drain behavior aligned with session purpose
- **Interruptible**: No interference with primary work
- **Transparent**: Clear cost accounting and value reporting

For zenportal, start with **Phase 1 MVP**: manual session reflection drains. Validate user value before building complex infrastructure.

The analogy to garbage collection is apt: just as GC reclaims unused memory during idle periods, token drains reclaim unused context capacity for background value creation.

---

## Sources

- [LLM Context Management Guide](https://eval.16x.engineer/blog/llm-context-management-guide)
- [LLM Cost Optimization: Smart Routing](https://www.kosmoy.com/post/llm-cost-management-stop-burning-money-on-tokens)
- [Token Compression Strategies](https://medium.com/@yashpaddalwar/token-compression-how-to-slash-your-llm-costs-by-80-without-sacrificing-quality-bfd79daf7c7c)
- [Top Techniques to Manage Context Lengths](https://agenta.ai/blog/top-6-techniques-to-manage-context-length-in-llms)
- [Claude Rate Limits Documentation](https://docs.claude.com/en/api/rate-limits)
- [Anthropic Token-Saving Updates](https://www.anthropic.com/news/token-saving-updates)
- [Claude Context Window 2025 Rules](https://www.datastudios.org/post/claude-context-window-token-limits-memory-policy-and-2025-rules)
- [Token Budgeting for Long-Context Apps](https://dev.co/ai/token-budgeting-strategies-for-long-context-llm-apps)
- [Optimizing Token Usage in Agent-Based Assistants](https://medium.com/elementor-engineers/optimizing-token-usage-in-agent-based-assistants-ffd1822ece9c)
