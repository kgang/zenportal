# OpenRouter Integration Plan

> Research and implementation plan for adding OpenRouter support to Zen Portal

## What is OpenRouter?

OpenRouter is a unified API gateway that provides access to 400+ AI models from multiple providers (OpenAI, Anthropic, Google, Meta, Mistral, etc.) through a single API endpoint and key. Key features:

- **OpenAI-compatible API**: Uses the same `/chat/completions` format
- **Provider fallback**: Automatic failover if a provider has issues
- **Model routing**: Can route to optimal models based on task type
- **Unified billing**: Single account for all providers
- **Multimodal support**: Text, images, PDFs

**API Endpoint**: `https://openrouter.ai/api/v1/chat/completions`

## Available CLI Tools

### Option 1: @openrouter/cli (Official, npm)

- **Focus**: Proxies Claude Code through OpenRouter
- **Install**: `npm install -g @openrouter/cli`
- **Usage**: `openrouter proxy start && openrouter code`
- **Pros**: Official, integrates with Claude Code directly
- **Cons**: Requires Node.js, more complex setup

### Option 2: orchat (Python, PyPI)

- **Focus**: Feature-rich interactive chat
- **Install**: `pip install orchat`
- **Usage**: `orchat` (after `orchat --setup` for API key)
- **Pros**:
  - Streaming responses with markdown rendering
  - Session management with auto-summarization
  - Token tracking with cost analytics
  - Model switching via `/model` command
  - File attachments with `@` symbol
- **Cons**: Heavier dependency footprint

### Option 3: openrouter-cli (Python, PyPI)

- **Focus**: Simple Ollama-like experience
- **Install**: `pip install openrouter-cli` or `uv tool install openrouter-cli`
- **Usage**: `openrouter-cli run <model>` (after `openrouter-cli configure`)
- **Pros**:
  - Lightweight
  - Persistent history
  - Temperature/effort controls
  - Works with Python 3.12+
- **Cons**: Fewer features than orchat

## Recommended Approach

### Add SessionType.OPENROUTER

Add OpenRouter as a new session type alongside existing CLAUDE, CODEX, GEMINI, SHELL types.

```python
# models/session.py
class SessionType(Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    SHELL = "shell"
    OPENROUTER = "openrouter"  # NEW
```

### CLI Tool Selection

**Recommended: `orchat`** for its rich feature set:
- Session management (compatible with our state persistence)
- Streaming responses
- Token tracking (can integrate with our TokenUsage system)
- Model switching without restarting

Alternative: `openrouter-cli` for simpler, lighter-weight integration.

### Configuration

Add OpenRouter settings to the 3-tier config system:

```python
# services/config.py
@dataclass
class OpenRouterSettings:
    default_model: str = "anthropic/claude-3.5-sonnet"
    api_key_env: str = "OPENROUTER_API_KEY"  # Environment variable name
    temperature: float = 0.7
```

### Implementation Steps

1. **Add dependency check** in `app.py`:
   ```python
   if not shutil.which("orchat"):
       warnings.append("orchat not found - OpenRouter sessions won't work")
   ```

2. **Add SessionType.OPENROUTER** to `models/session.py`

3. **Add OpenRouterSettings** to `services/config.py`

4. **Update SessionManager.create_session()** in `services/session_manager.py`:
   ```python
   elif session_type == SessionType.OPENROUTER:
       model = resolved.openrouter.default_model if resolved.openrouter else "anthropic/claude-3.5-sonnet"
       command_args = ["orchat", "--model", model]
       if prompt:
           # orchat accepts initial message as argument
           command_args.append(prompt)
   ```

5. **Update binary validation**:
   ```python
   binary_map = {
       SessionType.OPENROUTER: "orchat",
       # ... existing mappings
   }
   ```

6. **Add to new session modal** in `screens/new_session.py`:
   - Add OPENROUTER to session type selector
   - Add model picker for OpenRouter (populate from `orchat models` or hardcode popular ones)

7. **Update revive logic** for OpenRouter sessions (if orchat supports session resume)

### Model Selection

Popular OpenRouter models to offer:

| Model | Provider | Context | Best For |
|-------|----------|---------|----------|
| anthropic/claude-3.5-sonnet | Anthropic | 200k | General, coding |
| openai/gpt-4o | OpenAI | 128k | General, vision |
| google/gemini-2.0-flash-exp | Google | 1M | Long context |
| meta-llama/llama-3.3-70b-instruct | Meta | 128k | Open weights |
| mistralai/mistral-large | Mistral | 128k | European option |

### API Key Management

OpenRouter requires an API key. Options:

1. **Environment variable**: `OPENROUTER_API_KEY`
2. **orchat config**: `~/.orchat/config.json` (created by `orchat --setup`)
3. **Zen Portal config**: Add to `~/.config/zen-portal/config.json`

Recommended: Let orchat handle its own API key via `orchat --setup`, keeping zen-portal simple.

## Risks and Considerations

1. **API Key Security**: OpenRouter keys should never be committed. Using env vars or orchat's built-in config is safest.

2. **Cost Tracking**: OpenRouter uses credits. Users should monitor usage on OpenRouter's dashboard.

3. **Model Availability**: Models can be removed or have rate limits. Handle gracefully.

4. **Session Persistence**: orchat has session management, but may not be compatible with zen-portal's tmux-based approach. Test thoroughly.

## Timeline Estimate

| Phase | Tasks |
|-------|-------|
| 1 | Add SessionType.OPENROUTER, dependency check |
| 2 | Update SessionManager create/revive logic |
| 3 | Add to new session modal with model picker |
| 4 | Update config system with OpenRouter settings |
| 5 | Testing and documentation |

## Sources

- [OpenRouter API Reference](https://openrouter.ai/docs/api/reference/overview)
- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart)
- [OrChat GitHub](https://github.com/oop7/OrChat)
- [openrouter-cli PyPI](https://pypi.org/project/openrouter-cli/)
- [@openrouter/cli npm](https://www.npmjs.com/package/@openrouter/cli)
