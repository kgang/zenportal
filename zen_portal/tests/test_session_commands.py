"""Tests for SessionCommandBuilder, focusing on security validation."""

import os
import pytest
from unittest.mock import patch

from zen_portal.services.session_commands import SessionCommandBuilder
from zen_portal.services.config import ProxySettings


class TestSessionCommandBuilderURLValidation:
    """Tests for URL validation in build_proxy_env_vars."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_valid_http_url(self, builder):
        """Valid HTTP URL is accepted."""
        result = builder._validate_url("http://localhost:8787")
        assert result == "http://localhost:8787"

    def test_valid_https_url(self, builder):
        """Valid HTTPS URL is accepted."""
        result = builder._validate_url("https://api.openrouter.ai/v1")
        assert result == "https://api.openrouter.ai/v1"

    def test_url_trailing_slash_stripped(self, builder):
        """Trailing slashes are normalized."""
        result = builder._validate_url("http://localhost:8787/")
        assert result == "http://localhost:8787"

    def test_invalid_scheme_file(self, builder):
        """File scheme URLs are rejected."""
        result = builder._validate_url("file:///etc/passwd")
        assert result is None

    def test_invalid_scheme_javascript(self, builder):
        """JavaScript URLs are rejected."""
        result = builder._validate_url("javascript:alert(1)")
        assert result is None

    def test_invalid_scheme_ftp(self, builder):
        """FTP URLs are rejected."""
        result = builder._validate_url("ftp://evil.com/malware")
        assert result is None

    def test_url_without_scheme(self, builder):
        """URLs without scheme are rejected."""
        result = builder._validate_url("localhost:8787")
        assert result is None

    def test_url_too_long(self, builder):
        """Very long URLs are rejected."""
        long_url = "https://example.com/" + "a" * 3000
        result = builder._validate_url(long_url)
        assert result is None

    def test_empty_url(self, builder):
        """Empty URLs return None."""
        result = builder._validate_url("")
        assert result is None

    def test_url_with_credentials(self, builder):
        """URLs with embedded credentials are normalized (credentials stripped)."""
        result = builder._validate_url("http://user:pass@localhost:8787")
        assert result is not None
        assert "localhost" in result


class TestSessionCommandBuilderAPIKeyValidation:
    """Tests for API key validation."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_valid_api_key_alphanumeric(self, builder):
        """Standard alphanumeric API keys are accepted."""
        result = builder._validate_api_key("sk-or-v1-abc123def456")
        assert result == "sk-or-v1-abc123def456"

    def test_valid_api_key_with_underscores(self, builder):
        """API keys with underscores are accepted."""
        result = builder._validate_api_key("sk_ant_api03_key")
        assert result == "sk_ant_api03_key"

    def test_valid_api_key_with_dashes(self, builder):
        """API keys with dashes are accepted."""
        result = builder._validate_api_key("sk-or-12345-abcde")
        assert result == "sk-or-12345-abcde"

    def test_api_key_whitespace_stripped(self, builder):
        """Whitespace is stripped from API keys."""
        result = builder._validate_api_key("  sk-or-key  ")
        assert result == "sk-or-key"

    def test_api_key_with_shell_metacharacters(self, builder):
        """API keys with shell metacharacters are rejected."""
        assert builder._validate_api_key("key; rm -rf /") is None
        assert builder._validate_api_key("key$(whoami)") is None
        assert builder._validate_api_key("key`id`") is None
        assert builder._validate_api_key("key | cat /etc/passwd") is None

    def test_api_key_with_newlines(self, builder):
        """API keys with newlines are rejected."""
        result = builder._validate_api_key("key\nmalicious")
        assert result is None

    def test_api_key_too_long(self, builder):
        """Very long API keys are rejected."""
        long_key = "a" * 300
        result = builder._validate_api_key(long_key)
        assert result is None

    def test_empty_api_key(self, builder):
        """Empty API keys return None."""
        result = builder._validate_api_key("")
        assert result is None


class TestSessionCommandBuilderModelValidation:
    """Tests for model name validation."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_valid_model_anthropic(self, builder):
        """Anthropic model names are accepted."""
        result = builder._validate_model_name("anthropic/claude-sonnet-4")
        assert result == "anthropic/claude-sonnet-4"

    def test_valid_model_openai(self, builder):
        """OpenAI model names are accepted."""
        result = builder._validate_model_name("openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_valid_model_with_colon(self, builder):
        """Model names with version suffixes are accepted."""
        result = builder._validate_model_name("openai/gpt-4o:beta")
        assert result == "openai/gpt-4o:beta"

    def test_valid_model_with_period(self, builder):
        """Model names with periods are accepted."""
        result = builder._validate_model_name("anthropic/claude-3.5-sonnet")
        assert result == "anthropic/claude-3.5-sonnet"

    def test_model_with_shell_metacharacters(self, builder):
        """Model names with shell metacharacters are rejected."""
        assert builder._validate_model_name("model; rm -rf /") is None
        assert builder._validate_model_name("$(whoami)") is None
        assert builder._validate_model_name("model`id`") is None

    def test_model_with_spaces(self, builder):
        """Model names with spaces are rejected."""
        result = builder._validate_model_name("anthropic claude")
        assert result is None

    def test_model_too_long(self, builder):
        """Very long model names are rejected."""
        long_model = "anthropic/" + "a" * 130
        result = builder._validate_model_name(long_model)
        assert result is None

    def test_empty_model(self, builder):
        """Empty model names return None."""
        result = builder._validate_model_name("")
        assert result is None


class TestBuildProxyEnvVars:
    """Tests for the build_proxy_env_vars method (y-router / OpenRouter)."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_disabled_returns_empty(self, builder):
        """When proxy is disabled, returns empty dict."""
        settings = ProxySettings(enabled=False)
        result = builder.build_proxy_env_vars(settings)
        assert result == {}

    def test_none_settings_returns_empty(self, builder):
        """When settings is None, returns empty dict."""
        result = builder.build_proxy_env_vars(None)
        assert result == {}

    def test_enabled_with_valid_url(self, builder):
        """Valid URL is set as ANTHROPIC_BASE_URL."""
        settings = ProxySettings(
            enabled=True,
            base_url="https://api.openrouter.ai/v1",
        )
        result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_BASE_URL"] == "https://api.openrouter.ai/v1"

    def test_enabled_with_invalid_url_skipped(self, builder):
        """Invalid URL is not included in env vars."""
        settings = ProxySettings(
            enabled=True,
            base_url="javascript:alert(1)",
        )
        result = builder.build_proxy_env_vars(settings)
        assert "ANTHROPIC_BASE_URL" not in result

    def test_enabled_with_valid_api_key(self, builder):
        """Valid API key sets both ANTHROPIC_API_KEY and custom headers."""
        settings = ProxySettings(
            enabled=True,
            api_key="sk-or-v1-test123",
        )
        result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-v1-test123"
        assert result["ANTHROPIC_CUSTOM_HEADERS"] == "x-api-key: sk-or-v1-test123"

    def test_enabled_with_invalid_api_key_skipped(self, builder):
        """Invalid API key is not included in env vars."""
        settings = ProxySettings(
            enabled=True,
            api_key="key; rm -rf /",
        )
        result = builder.build_proxy_env_vars(settings)
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_enabled_with_valid_model(self, builder):
        """Valid model is set as ANTHROPIC_MODEL."""
        settings = ProxySettings(
            enabled=True,
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"

    def test_enabled_with_invalid_model_skipped(self, builder):
        """Invalid model is not included in env vars."""
        settings = ProxySettings(
            enabled=True,
            default_model="$(whoami)",
        )
        result = builder.build_proxy_env_vars(settings)
        assert "ANTHROPIC_MODEL" not in result

    def test_api_key_from_environment(self, builder):
        """API key can be read from OPENROUTER_API_KEY environment variable."""
        settings = ProxySettings(
            enabled=True,
            api_key="",  # No key in settings
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key"}):
            result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-env-key"

    def test_settings_api_key_overrides_env(self, builder):
        """Settings API key takes precedence over environment variable."""
        settings = ProxySettings(
            enabled=True,
            api_key="sk-or-settings-key",
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key"}):
            result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-settings-key"

    def test_full_valid_config(self, builder):
        """Full valid config sets all expected env vars."""
        settings = ProxySettings(
            enabled=True,
            base_url="https://api.openrouter.ai/v1",
            api_key="sk-or-valid123",
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_proxy_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "https://api.openrouter.ai/v1"
        assert result["ANTHROPIC_API_KEY"] == "sk-or-valid123"
        assert result["ANTHROPIC_CUSTOM_HEADERS"] == "x-api-key: sk-or-valid123"
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"

    def test_default_base_url_used_when_empty(self, builder):
        """Default y-router URL is used when base_url is empty."""
        settings = ProxySettings(
            enabled=True,
            api_key="sk-or-test",
        )
        result = builder.build_proxy_env_vars(settings)
        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:8787"


class TestBuildOpenRouterEnvVarsAlias:
    """Test backwards compatibility alias."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_alias_calls_build_proxy_env_vars(self, builder):
        """build_openrouter_env_vars is an alias for build_proxy_env_vars."""
        settings = ProxySettings(
            enabled=True,
            api_key="sk-or-test",
        )
        result1 = builder.build_proxy_env_vars(settings)
        result2 = builder.build_openrouter_env_vars(settings)
        assert result1 == result2
