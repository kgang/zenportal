# Security Analysis: Zen Portal Multi-Session Manager

Concrete security risks and mitigations for the tmux-based Claude session manager.

---

## Threat Model

### Assets to Protect

| Asset | Value | Impact if Compromised |
|-------|-------|----------------------|
| User's filesystem | High | Data loss, malware installation |
| Running sessions | Medium | Work disruption, resource abuse |
| Credentials in environment | High | Account compromise |
| System resources | Medium | DoS, degraded performance |

### Threat Actors

| Actor | Capability | Motivation |
|-------|------------|------------|
| Malicious prompt | Low | Exploit via injected commands |
| Compromised dependency | Medium | Supply chain attack |
| Local user (multi-tenant) | Medium | Session hijacking |
| Network attacker | Low | Limited (local-only tool) |

---

## Risk 1: Command Injection via Session Names

### Vulnerability

The current implementation passes user prompts to tmux:

```python
# garden.py line 83-101
full_prompt = f"""In the zen_portal codebase:

{plant.prompt}

Keep changes minimal and zen."""

cmd = [
    "tmux",
    "new-session",
    "-d",
    "-s",
    plant.tmux_session,  # Derived from UUID - SAFE
    "-c",
    str(zen_portal_dir),
    "claude",
    "--print",
    full_prompt,  # User input - RISK
]
```

### Attack Vector

A malicious prompt could include shell metacharacters:

```
User prompt: `rm -rf /` && echo pwned
```

### Current Mitigation (Partial)

- Using list form of subprocess (no `shell=True`) - GOOD
- Arguments passed as separate list items - GOOD

### Analysis

With `shell=False` and list arguments, the prompt is passed as a single argument to Claude, not interpreted by shell. The risk is **LOW** for direct command injection.

However, Claude itself will see the malicious prompt and could potentially execute harmful commands if it interprets them.

### Recommendation

1. **Input validation**: Reject prompts containing suspicious patterns
2. **Length limits**: Cap prompt length to prevent buffer issues
3. **Audit logging**: Log all prompts for forensic review

```python
import re

SUSPICIOUS_PATTERNS = [
    r'`[^`]+`',           # Backticks
    r'\$\([^)]+\)',       # Command substitution
    r'&&|\|\|',           # Command chaining
    r';\s*\w+',           # Semicolon commands
    r'>\s*/',             # Redirect to root
    r'rm\s+-rf',          # Dangerous rm
]

def validate_prompt(prompt: str) -> tuple[bool, str | None]:
    """Validate prompt for suspicious content."""
    if len(prompt) > 1000:
        return False, "Prompt too long (max 1000 chars)"

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, prompt):
            return False, f"Suspicious pattern detected"

    return True, None
```

**Risk Level**: LOW (with current implementation), MEDIUM (if shell=True ever used)

---

## Risk 2: Session Hijacking via tmux

### Vulnerability

tmux sessions are accessible to any process running as the same user.

```bash
# Any process can list sessions
tmux list-sessions

# Any process can attach
tmux attach -t zen-claude-abc123

# Any process can send keys
tmux send-keys -t zen-claude-abc123 "malicious command" Enter
```

### Attack Vector

1. Malicious script on user's machine enumerates zen-portal sessions
2. Attacker attaches to session or sends commands
3. Claude executes attacker's commands with user's privileges

### Current Mitigation

- Session names use predictable prefix (`zen-claude-`) making enumeration trivial
- No authentication on tmux sessions

### Recommendation

1. **Random session names**: Use full UUID, not truncated

```python
# Current (predictable)
plant_id = str(uuid.uuid4())[:8]  # Only 8 chars

# Better (less predictable)
plant_id = str(uuid.uuid4())  # Full UUID
tmux_session = f"zp-{plant_id}"
```

2. **Socket isolation**: Use dedicated tmux socket

```python
SOCKET_PATH = Path.home() / ".zen-portal" / "tmux.sock"

cmd = [
    "tmux",
    "-S", str(SOCKET_PATH),  # Dedicated socket
    "new-session",
    ...
]
```

3. **Socket permissions**: Restrict socket file

```python
import os
import stat

def ensure_socket_dir():
    socket_dir = Path.home() / ".zen-portal"
    socket_dir.mkdir(mode=0o700, exist_ok=True)
```

**Risk Level**: MEDIUM (local multi-user systems), LOW (single-user systems)

---

## Risk 3: Resource Exhaustion

### Vulnerability

No limits on number of concurrent sessions or resource consumption.

### Attack Vector

1. User (or malicious script) creates many sessions
2. Each session spawns Claude process
3. System runs out of memory/CPU
4. DoS against user's own system

### Current Mitigation

None - unlimited sessions allowed.

### Recommendation

1. **Session limits**: Enforce maximum concurrent sessions

```python
MAX_SESSIONS = 10
MAX_GROWING_SESSIONS = 5

def plant_seed(self, prompt: str) -> Plant | None:
    active = len([p for p in self.plants.values()
                  if p.state == PlantState.GROWING])

    if len(self.plants) >= MAX_SESSIONS:
        raise SessionLimitError("Maximum sessions reached")

    if active >= MAX_GROWING_SESSIONS:
        raise SessionLimitError("Too many active sessions")

    # ... proceed with planting
```

2. **Resource monitoring**: Track combined resource usage

```python
import psutil

def get_session_resource_usage() -> dict:
    """Get combined CPU/memory of Claude processes."""
    total_cpu = 0
    total_memory = 0

    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        if 'claude' in proc.info['name'].lower():
            total_cpu += proc.info['cpu_percent']
            total_memory += proc.info['memory_info'].rss

    return {
        'cpu_percent': total_cpu,
        'memory_mb': total_memory / (1024 * 1024)
    }
```

3. **Timeout enforcement**: Kill sessions that exceed time limits

```python
SESSION_TIMEOUT_MINUTES = 60

def tend_garden(self) -> None:
    """Update state and enforce timeouts."""
    for plant in list(self.plants.values()):
        self.check_plant(plant.id)

        if (plant.state == PlantState.GROWING and
            plant.age_minutes > SESSION_TIMEOUT_MINUTES):
            self.prune_plant(plant.id)
            self._log_timeout(plant)
```

**Risk Level**: MEDIUM

---

## Risk 4: Sensitive Data in Output

### Vulnerability

Claude output may contain sensitive data captured from the environment or filesystem.

### Attack Vector

1. Claude reads `.env` file or credentials
2. Output containing secrets displayed in TUI
3. Output persisted in tmux history
4. Secrets exposed via shoulder surfing or screen capture

### Current Mitigation

None - all output displayed verbatim.

### Recommendation

1. **Output filtering**: Redact known secret patterns

```python
import re

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*[\'"]?([^\s\'"]+)',
     r'\1=***REDACTED***'),
    (r'(?i)bearer\s+[a-zA-Z0-9._-]+',
     'Bearer ***REDACTED***'),
    (r'sk-[a-zA-Z0-9]{48}',  # OpenAI keys
     'sk-***REDACTED***'),
]

def redact_secrets(output: str) -> str:
    """Redact known secret patterns from output."""
    for pattern, replacement in SECRET_PATTERNS:
        output = re.sub(pattern, replacement, output)
    return output
```

2. **History limits**: Don't persist full output

```python
# Limit tmux history
cmd = [
    "tmux",
    "new-session",
    "-d",
    "-s", session_name,
    # Limit scrollback
    "set-option", "-t", session_name, "history-limit", "1000",
]
```

3. **Clear on close**: Optionally clear history when pruning

```python
def prune_plant(self, plant_id: str, clear_history: bool = True) -> bool:
    if clear_history:
        subprocess.run([
            "tmux", "clear-history", "-t", plant.tmux_session
        ], timeout=2, capture_output=True)

    # Then kill session
    subprocess.run([
        "tmux", "kill-session", "-t", plant.tmux_session
    ], timeout=2)
```

**Risk Level**: MEDIUM

---

## Risk 5: Dependency Supply Chain

### Vulnerability

Python dependencies (Textual, etc.) could be compromised.

### Attack Vector

1. Attacker compromises PyPI package
2. User installs malicious update
3. Malicious code executes with user privileges

### Current Mitigation

- Using `uv` for dependency management
- `pyproject.toml` specifies dependencies

### Recommendation

1. **Pin dependencies**: Use exact versions

```toml
[project]
dependencies = [
    "textual==0.89.1",  # Exact version
]
```

2. **Hash verification**: Use pip's hash checking

```toml
[tool.uv]
verify-hashes = true
```

3. **Audit regularly**: Check for known vulnerabilities

```bash
# Add to CI/CD
uv pip audit
```

4. **Minimal dependencies**: Remove unused packages

**Risk Level**: LOW (with pinning), MEDIUM (without)

---

## Risk 6: Path Traversal

### Vulnerability

Working directory passed to tmux could be manipulated.

### Current Code

```python
zen_portal_dir = Path(__file__).parent.parent
# ...
"-c", str(zen_portal_dir),
```

### Analysis

Current implementation uses a fixed path derived from the module location. No user input affects the path. **Risk is LOW**.

### Potential Future Risk

If working directory becomes user-configurable:

```python
# DANGEROUS if user_path not validated
cmd = [
    "tmux", "new-session",
    "-c", user_path,  # Could be "../../../etc"
    ...
]
```

### Recommendation

If paths become configurable:

```python
from pathlib import Path

def validate_working_dir(path: str) -> Path:
    """Validate and resolve working directory."""
    resolved = Path(path).resolve()

    # Must exist
    if not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")

    # Must be directory
    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {resolved}")

    # Must be within home directory
    home = Path.home()
    if not str(resolved).startswith(str(home)):
        raise ValueError(f"Path must be within home directory")

    return resolved
```

**Risk Level**: LOW (current), MEDIUM (if paths become configurable)

---

## Risk 7: Subprocess Timeout Handling

### Vulnerability

Subprocess calls could hang indefinitely.

### Current Mitigation

Timeouts are set on most subprocess calls:

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
```

### Gap

Some operations may need longer timeouts, and timeout handling could be improved:

```python
try:
    result = subprocess.run(cmd, timeout=5)
except subprocess.TimeoutExpired:
    plant.state = PlantState.WILTED
    plant.output = str(e)
    # Process may still be running!
```

### Recommendation

Kill process on timeout:

```python
import signal

def run_with_timeout(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    """Run command with proper timeout handling."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        # Kill the process group
        if e.cmd and hasattr(e, 'pid'):
            os.killpg(os.getpgid(e.pid), signal.SIGKILL)
        raise
```

**Risk Level**: LOW

---

## Security Checklist

### Before Production

- [ ] Input validation on all user-provided prompts
- [ ] Session name uses full UUID
- [ ] Dedicated tmux socket with restricted permissions
- [ ] Session limits enforced (max 10, max 5 active)
- [ ] Dependencies pinned to exact versions
- [ ] Subprocess timeouts on all calls

### Monitoring

- [ ] Log all session creation/deletion
- [ ] Log all prompts (for audit, not display)
- [ ] Alert on unusual session counts
- [ ] Monitor Claude process resource usage

### Future Considerations

- [ ] Output secret redaction (if needed)
- [ ] Session encryption at rest (if persisting)
- [ ] Rate limiting on session creation
- [ ] Sandboxing Claude process (containers/VMs)

---

## Summary

| Risk | Severity | Likelihood | Mitigation Priority |
|------|----------|------------|---------------------|
| Command injection | High | Low | Medium |
| Session hijacking | Medium | Low | High |
| Resource exhaustion | Medium | Medium | High |
| Sensitive data exposure | High | Medium | Medium |
| Supply chain | High | Low | Medium |
| Path traversal | High | Low | Low (current) |
| Timeout handling | Low | Medium | Low |

### Immediate Actions (MVP)

1. Add session limits (5 active, 10 total)
2. Use full UUID for session names
3. Add basic input validation
4. Pin all dependencies

### Deferred Actions (V2)

1. Dedicated tmux socket
2. Output redaction
3. Resource monitoring
4. Audit logging
