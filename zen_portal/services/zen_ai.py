"""Zen AI - Lightweight AI invocation without tmux sessions.

Provides direct AI queries via:
- Claude -p (pipe mode) for Claude models
- OpenRouter API for other models

Designed for quick, ephemeral interactions within Zenportal.

NOTE: This backend is currently unused in the UI. The previous modal UX
(blocking wait for response) was poor. Future plans:
- Lightweight chat sidebar that doesn't block main workflow
- Background query with notification when response ready
- Integration with session context via @refs

The API is stable and tested - only the UX needs redesign.
See: services/context_parser.py for @ref syntax
See: services/config.py ZenAIConfig for settings
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import ProxySettings, ZenAIConfig, ZenAIModel, ZenAIProvider


logger = logging.getLogger(__name__)


# OpenRouter model IDs for each tier
OPENROUTER_MODELS = {
    ZenAIModel.HAIKU: "anthropic/claude-3-haiku",
    ZenAIModel.SONNET: "anthropic/claude-sonnet-4-20250514",
    ZenAIModel.OPUS: "anthropic/claude-opus-4-20250514",
}


@dataclass
class ZenAIResult:
    """Result of a Zen AI query."""

    success: bool
    response: str
    error: str = ""
    tokens_used: int = 0


class ZenAI:
    """Lightweight AI invocation service.

    Provides quick AI queries without creating tmux sessions.
    Uses claude -p for Claude, OpenRouter API for other models.
    """

    # Timeout for subprocess queries (seconds)
    SUBPROCESS_TIMEOUT = 60

    # Timeout for API requests (seconds)
    API_TIMEOUT = 30

    # Maximum response length (characters)
    MAX_RESPONSE_LENGTH = 10000

    def __init__(
        self,
        config: ZenAIConfig,
        proxy_settings: ProxySettings | None = None,
    ):
        self.config = config
        self.proxy_settings = proxy_settings

    @property
    def is_available(self) -> bool:
        """Check if Zen AI is available and configured."""
        if not self.config.enabled:
            return False

        if self.config.provider == ZenAIProvider.CLAUDE:
            # Check if claude binary exists
            return shutil.which("claude") is not None

        elif self.config.provider == ZenAIProvider.OPENROUTER:
            # Check if API key is available
            return bool(self._get_api_key())

        return False

    def _get_api_key(self) -> str:
        """Get OpenRouter API key from config or environment."""
        if self.proxy_settings and self.proxy_settings.api_key:
            return self.proxy_settings.api_key
        return os.environ.get("OPENROUTER_API_KEY", "")

    async def query(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> ZenAIResult:
        """Execute an AI query.

        Args:
            prompt: The user's question/prompt
            system_prompt: Optional system context (from @refs)

        Returns:
            ZenAIResult with response or error
        """
        if not self.is_available:
            return ZenAIResult(
                success=False,
                response="",
                error="zen ai not available",
            )

        if self.config.provider == ZenAIProvider.CLAUDE:
            return await self._query_claude_pipe(prompt, system_prompt)
        else:
            return await self._query_openrouter_api(prompt, system_prompt)

    async def _query_claude_pipe(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> ZenAIResult:
        """Query Claude using pipe mode subprocess."""
        try:
            # Build command
            cmd = ["claude", "-p"]
            if self.config.model == ZenAIModel.OPUS:
                cmd.extend(["--model", "opus"])
            elif self.config.model == ZenAIModel.SONNET:
                cmd.extend(["--model", "sonnet"])
            else:
                cmd.extend(["--model", "haiku"])

            # Combine system prompt and user prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

            # Build environment with proxy settings if configured
            env = os.environ.copy()
            if self.proxy_settings and self.proxy_settings.enabled:
                env["ANTHROPIC_BASE_URL"] = self.proxy_settings.effective_base_url
                api_key = self._get_api_key()
                if api_key:
                    env["ANTHROPIC_API_KEY"] = api_key

            # Run subprocess
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT,
                env=env,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "unknown error"
                return ZenAIResult(
                    success=False,
                    response="",
                    error=error_msg[:200],  # Truncate long errors
                )

            response = result.stdout.strip()
            if len(response) > self.MAX_RESPONSE_LENGTH:
                response = response[:self.MAX_RESPONSE_LENGTH] + "..."

            return ZenAIResult(
                success=True,
                response=response,
            )

        except subprocess.TimeoutExpired:
            return ZenAIResult(
                success=False,
                response="",
                error="query timed out",
            )
        except FileNotFoundError:
            return ZenAIResult(
                success=False,
                response="",
                error="claude not found",
            )
        except Exception as e:
            return ZenAIResult(
                success=False,
                response="",
                error=str(e)[:100],
            )

    async def _query_openrouter_api(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> ZenAIResult:
        """Query OpenRouter API directly."""
        api_key = self._get_api_key()
        if not api_key:
            return ZenAIResult(
                success=False,
                response="",
                error="no api key configured",
            )

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Build request
            payload = {
                "model": self.config.effective_model,
                "messages": messages,
                "max_tokens": 2048,
            }

            request = Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/zenportal/zenportal",
                    "X-Title": "Zen Portal",
                },
                method="POST",
            )

            # Execute request in thread pool
            def do_request():
                with urlopen(request, timeout=self.API_TIMEOUT) as resp:
                    return json.loads(resp.read().decode())

            data = await asyncio.to_thread(do_request)

            # Extract response
            if "choices" in data and len(data["choices"]) > 0:
                response = data["choices"][0]["message"]["content"]
                if len(response) > self.MAX_RESPONSE_LENGTH:
                    response = response[:self.MAX_RESPONSE_LENGTH] + "..."

                tokens = 0
                if "usage" in data:
                    tokens = data["usage"].get("total_tokens", 0)

                return ZenAIResult(
                    success=True,
                    response=response,
                    tokens_used=tokens,
                )
            else:
                return ZenAIResult(
                    success=False,
                    response="",
                    error="no response from api",
                )

        except HTTPError as e:
            error_msg = f"api error: {e.code}"
            try:
                body = e.read().decode()
                error_data = json.loads(body)
                if "error" in error_data:
                    error_msg = error_data["error"].get("message", error_msg)[:100]
            except Exception as parse_error:
                logger.debug(f"Failed to parse API error response: {parse_error}")
            return ZenAIResult(
                success=False,
                response="",
                error=error_msg,
            )
        except URLError as e:
            return ZenAIResult(
                success=False,
                response="",
                error=f"network error: {str(e.reason)[:50]}",
            )
        except TimeoutError:
            return ZenAIResult(
                success=False,
                response="",
                error="api request timed out",
            )
        except Exception as e:
            return ZenAIResult(
                success=False,
                response="",
                error=str(e)[:100],
            )

    async def stream_query(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        """Stream AI response (yields chunks as they arrive).

        For now, this is a simple wrapper that yields the full response.
        True streaming can be added later for better UX.
        """
        result = await self.query(prompt, system_prompt)
        if result.success:
            # Simulate streaming by yielding in chunks
            chunk_size = 50
            for i in range(0, len(result.response), chunk_size):
                yield result.response[i:i + chunk_size]
                await asyncio.sleep(0.02)  # Small delay for visual effect
        else:
            yield f"[error: {result.error}]"
