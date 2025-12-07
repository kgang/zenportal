"""Token usage parsing from Claude JSONL session files."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# OpenRouter pricing per token (as of Dec 2024)
# Format: {model_pattern: (input_price, output_price, cache_read_price, cache_write_price)}
OPENROUTER_PRICING: dict[str, tuple[float, float, float, float]] = {
    # Claude Opus 4.5 - $5/$25 per 1M tokens
    "claude-opus-4": (0.000005, 0.000025, 0.0000005, 0.00000625),
    "claude-4-opus": (0.000005, 0.000025, 0.0000005, 0.00000625),
    # Claude Sonnet 4 - $3/$15 per 1M tokens
    "claude-sonnet-4": (0.000003, 0.000015, 0.0000003, 0.00000375),
    "claude-4-sonnet": (0.000003, 0.000015, 0.0000003, 0.00000375),
    "claude-4.5-sonnet": (0.000003, 0.000015, 0.0000003, 0.00000375),
    # Claude Haiku 4.5 - $1/$5 per 1M tokens
    "claude-haiku-4": (0.000001, 0.000005, 0.0000001, 0.00000125),
    "claude-4-haiku": (0.000001, 0.000005, 0.0000001, 0.00000125),
    "claude-4.5-haiku": (0.000001, 0.000005, 0.0000001, 0.00000125),
    # Claude 3.5 Sonnet - $3/$15 per 1M tokens
    "claude-3.5-sonnet": (0.000003, 0.000015, 0.0000003, 0.00000375),
    "claude-3-5-sonnet": (0.000003, 0.000015, 0.0000003, 0.00000375),
    # Default fallback (Sonnet pricing)
    "default": (0.000003, 0.000015, 0.0000003, 0.00000375),
}


def _get_pricing(model: str) -> tuple[float, float, float, float]:
    """Get pricing tuple for a model name."""
    model_lower = model.lower()
    for pattern, pricing in OPENROUTER_PRICING.items():
        if pattern != "default" and pattern in model_lower:
            return pricing
    return OPENROUTER_PRICING["default"]


@dataclass
class TokenUsage:
    """Token usage statistics for a session or message."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)."""
        return self.input_tokens + self.output_tokens

    @property
    def cache_tokens(self) -> int:
        """Total cache-related tokens."""
        return self.cache_creation_tokens + self.cache_read_tokens

    def estimate_cost(self, model: str = "") -> float:
        """Estimate OpenRouter cost in USD based on model pricing.

        Args:
            model: Model name to look up pricing (e.g., "claude-sonnet-4")

        Returns:
            Estimated cost in USD
        """
        input_price, output_price, cache_read_price, cache_write_price = _get_pricing(model)
        return (
            self.input_tokens * input_price
            + self.output_tokens * output_price
            + self.cache_read_tokens * cache_read_price
            + self.cache_creation_tokens * cache_write_price
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Combine two token usages."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )


@dataclass
class SessionTokenStats:
    """Complete token statistics for a Claude session."""

    session_id: str
    total_usage: TokenUsage = field(default_factory=TokenUsage)
    message_count: int = 0
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    model: str = ""


class TokenParser:
    """Parser for Claude Code session JSONL files."""

    CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

    def __init__(self, claude_dir: Path | None = None):
        self._claude_dir = claude_dir or self.CLAUDE_PROJECTS_DIR

    def get_project_dir(self, working_dir: Path) -> Path | None:
        """Get Claude project directory for a working directory.

        Claude encodes paths like /Users/foo/bar as -Users-foo-bar
        """
        encoded_path = str(working_dir).replace("/", "-")
        project_dir = self._claude_dir / encoded_path
        return project_dir if project_dir.exists() else None

    def list_session_files(self, project_dir: Path) -> list[Path]:
        """List all JSONL session files in a project directory."""
        if not project_dir.exists():
            return []
        return sorted(
            project_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def parse_session_file(self, jsonl_path: Path) -> SessionTokenStats:
        """Parse a single session JSONL file for token statistics."""
        stats = SessionTokenStats(session_id=jsonl_path.stem)

        try:
            with open(jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        usage = self._extract_usage(entry)
                        if usage:
                            stats.total_usage = stats.total_usage + usage
                            stats.message_count += 1

                            # Track timestamps
                            timestamp = self._parse_timestamp(entry)
                            if timestamp:
                                if stats.first_message_at is None:
                                    stats.first_message_at = timestamp
                                stats.last_message_at = timestamp

                            # Track model
                            model = entry.get("message", {}).get("model", "")
                            if model:
                                stats.model = model
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return stats

    def _extract_usage(self, entry: dict) -> TokenUsage | None:
        """Extract token usage from a JSONL entry."""
        message = entry.get("message", {})
        usage = message.get("usage")
        if not usage:
            return None

        return TokenUsage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        )

    def _parse_timestamp(self, entry: dict) -> datetime | None:
        """Parse timestamp from JSONL entry."""
        ts = entry.get("timestamp")
        if not ts:
            return None
        try:
            # Handle ISO format with Z suffix
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    def get_session_stats(
        self,
        claude_session_id: str,
        working_dir: Path | None = None,
    ) -> SessionTokenStats | None:
        """Get token stats for a specific Claude session ID.

        If working_dir is provided, searches that project directory.
        Otherwise searches all project directories.
        """
        if not claude_session_id:
            return None

        if working_dir:
            project_dir = self.get_project_dir(working_dir)
            if project_dir:
                session_file = project_dir / f"{claude_session_id}.jsonl"
                if session_file.exists():
                    return self.parse_session_file(session_file)

        # Search all project directories
        if self._claude_dir.exists():
            for project_dir in self._claude_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                session_file = project_dir / f"{claude_session_id}.jsonl"
                if session_file.exists():
                    return self.parse_session_file(session_file)

        return None

    def get_token_history(
        self,
        claude_session_id: str,
        working_dir: Path | None = None,
    ) -> list[int]:
        """Get cumulative token counts over time for sparkline visualization.

        Returns list of cumulative total tokens at each API response.
        Useful for showing token usage trend in a sparkline.

        Args:
            claude_session_id: Claude session ID
            working_dir: Working directory to search in

        Returns:
            List of cumulative token totals (empty if session not found)
        """
        if not claude_session_id:
            return []

        session_file = None

        if working_dir:
            project_dir = self.get_project_dir(working_dir)
            if project_dir:
                candidate = project_dir / f"{claude_session_id}.jsonl"
                if candidate.exists():
                    session_file = candidate

        # Search all project directories if not found
        if not session_file and self._claude_dir.exists():
            for project_dir in self._claude_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                candidate = project_dir / f"{claude_session_id}.jsonl"
                if candidate.exists():
                    session_file = candidate
                    break

        if not session_file:
            return []

        history = []
        running_total = 0

        try:
            with open(session_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        usage = self._extract_usage(entry)
                        if usage:
                            running_total += usage.total_tokens
                            history.append(running_total)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return history
