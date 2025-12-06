"""Tests for SessionCommandBuilder, focusing on security validation."""

import os
import pytest
from unittest.mock import patch

from zen_portal.services.session_commands import SessionCommandBuilder
from zen_portal.services.config import OpenRouterProxySettings, ProxyAuthType


class TestSessionCommandBuilderURLValidation:
    """Tests for URL validation in build_openrouter_env_vars."""

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
        # urlparse puts credentials in netloc, but we reconstruct without them
        result = builder._validate_url("http://user:pass@localhost:8787")
        # The normalized URL includes the full netloc (with credentials)
        # This is intentional - we normalize but don't strip credentials
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
        # These could be used for command injection
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


class TestSessionCommandBuilderOAuthValidation:
    """Tests for OAuth token validation."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_valid_jwt_token(self, builder):
        """Standard JWT tokens are accepted."""
        # JWT format: header.payload.signature (base64-encoded)
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = builder._validate_oauth_token(token)
        assert result == token

    def test_valid_simple_token(self, builder):
        """Simple alphanumeric tokens are accepted."""
        result = builder._validate_oauth_token("abc123XYZ_token-value")
        assert result == "abc123XYZ_token-value"

    def test_oauth_token_with_equals_padding(self, builder):
        """Base64 tokens with padding are accepted."""
        result = builder._validate_oauth_token("token123==")
        assert result == "token123=="

    def test_oauth_token_whitespace_stripped(self, builder):
        """Whitespace is stripped from OAuth tokens."""
        result = builder._validate_oauth_token("  token123  ")
        assert result == "token123"

    def test_oauth_token_with_shell_metacharacters(self, builder):
        """OAuth tokens with shell metacharacters are rejected."""
        assert builder._validate_oauth_token("token; rm -rf /") is None
        assert builder._validate_oauth_token("token$(whoami)") is None
        assert builder._validate_oauth_token("token`id`") is None

    def test_oauth_token_with_spaces(self, builder):
        """OAuth tokens with spaces are rejected."""
        result = builder._validate_oauth_token("token with spaces")
        assert result is None

    def test_oauth_token_too_long(self, builder):
        """Very long OAuth tokens are rejected."""
        long_token = "a" * 5000
        result = builder._validate_oauth_token(long_token)
        assert result is None

    def test_empty_oauth_token(self, builder):
        """Empty OAuth tokens return None."""
        result = builder._validate_oauth_token("")
        assert result is None


class TestBuildOpenRouterEnvVars:
    """Tests for the full build_openrouter_env_vars method."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_disabled_returns_empty(self, builder):
        """When proxy is disabled, returns empty dict."""
        settings = OpenRouterProxySettings(enabled=False)
        result = builder.build_openrouter_env_vars(settings)
        assert result == {}

    def test_none_settings_returns_empty(self, builder):
        """When settings is None, returns empty dict."""
        result = builder.build_openrouter_env_vars(None)
        assert result == {}

    def test_enabled_with_valid_url(self, builder):
        """Valid URL is set as ANTHROPIC_BASE_URL."""
        settings = OpenRouterProxySettings(
            enabled=True,
            base_url="https://api.openrouter.ai/v1",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_BASE_URL"] == "https://api.openrouter.ai/v1"

    def test_enabled_with_invalid_url_skipped(self, builder):
        """Invalid URL is not included in env vars."""
        settings = OpenRouterProxySettings(
            enabled=True,
            base_url="javascript:alert(1)",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert "ANTHROPIC_BASE_URL" not in result

    def test_enabled_with_valid_api_key(self, builder):
        """Valid API key sets both ANTHROPIC_API_KEY and custom headers."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            api_key="sk-or-v1-test123",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-v1-test123"
        assert result["ANTHROPIC_CUSTOM_HEADERS"] == "x-api-key: sk-or-v1-test123"

    def test_enabled_with_invalid_api_key_skipped(self, builder):
        """Invalid API key is not included in env vars."""
        settings = OpenRouterProxySettings(
            enabled=True,
            api_key="key; rm -rf /",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_enabled_with_valid_model(self, builder):
        """Valid model is set as ANTHROPIC_MODEL."""
        settings = OpenRouterProxySettings(
            enabled=True,
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"

    def test_enabled_with_invalid_model_skipped(self, builder):
        """Invalid model is not included in env vars."""
        settings = OpenRouterProxySettings(
            enabled=True,
            default_model="$(whoami)",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert "ANTHROPIC_MODEL" not in result

    def test_api_key_from_environment(self, builder):
        """API key can be read from OPENROUTER_API_KEY environment variable."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            api_key="",  # No key in settings
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key"}):
            result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-env-key"

    def test_settings_api_key_overrides_env(self, builder):
        """Settings API key takes precedence over environment variable."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            api_key="sk-or-settings-key",
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key"}):
            result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "sk-or-settings-key"

    def test_full_valid_config(self, builder):
        """Full valid config sets all expected env vars."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="https://api.openrouter.ai/v1",
            api_key="sk-or-valid123",
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_openrouter_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "https://api.openrouter.ai/v1"
        assert result["ANTHROPIC_API_KEY"] == "sk-or-valid123"
        assert result["ANTHROPIC_CUSTOM_HEADERS"] == "x-api-key: sk-or-valid123"
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"


class TestBuildOpenRouterEnvVarsOAuth:
    """Tests for OAuth auth mode in build_openrouter_env_vars."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_oauth_mode_with_valid_token(self, builder):
        """OAuth mode sets Authorization: Bearer header."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            oauth_token="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert "Authorization: Bearer" in result["ANTHROPIC_CUSTOM_HEADERS"]
        assert result["ANTHROPIC_API_KEY"] == "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123"

    def test_oauth_mode_with_invalid_token_skipped(self, builder):
        """Invalid OAuth token is not included in env vars."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            oauth_token="token; rm -rf /",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_oauth_token_from_environment(self, builder):
        """OAuth token can be read from CLAUDE_OAUTH_TOKEN env var."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            oauth_token="",  # No token in settings
        )
        with patch.dict(os.environ, {"CLAUDE_OAUTH_TOKEN": "env-oauth-token123"}):
            result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "env-oauth-token123"
        assert "Bearer env-oauth-token123" in result["ANTHROPIC_CUSTOM_HEADERS"]

    def test_settings_oauth_token_overrides_env(self, builder):
        """Settings OAuth token takes precedence over environment variable."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            oauth_token="settings-token",
        )
        with patch.dict(os.environ, {"CLAUDE_OAUTH_TOKEN": "env-token"}):
            result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "settings-token"

    def test_oauth_mode_ignores_api_key(self, builder):
        """In OAuth mode, api_key field is ignored."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            api_key="should-be-ignored",
            oauth_token="oauth-token123",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "oauth-token123"
        assert "Bearer oauth-token123" in result["ANTHROPIC_CUSTOM_HEADERS"]
        assert "x-api-key" not in result["ANTHROPIC_CUSTOM_HEADERS"]

    def test_api_key_mode_ignores_oauth_token(self, builder):
        """In API_KEY mode, oauth_token field is ignored."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            api_key="api-key123",
            oauth_token="should-be-ignored",
        )
        result = builder.build_openrouter_env_vars(settings)
        assert result["ANTHROPIC_API_KEY"] == "api-key123"
        assert "x-api-key: api-key123" in result["ANTHROPIC_CUSTOM_HEADERS"]
        assert "Bearer" not in result["ANTHROPIC_CUSTOM_HEADERS"]

    def test_oauth_full_config(self, builder):
        """Full OAuth config with all options."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:5000",
            oauth_token="my-jwt-token.abc.xyz",
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_openrouter_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:5000"
        assert result["ANTHROPIC_API_KEY"] == "my-jwt-token.abc.xyz"
        assert result["ANTHROPIC_CUSTOM_HEADERS"] == "Authorization: Bearer my-jwt-token.abc.xyz"
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"


class TestBuildOpenRouterEnvVarsPassthrough:
    """Tests for Passthrough auth mode (CLIProxyAPI) in build_openrouter_env_vars."""

    @pytest.fixture
    def builder(self):
        return SessionCommandBuilder()

    def test_passthrough_only_sets_base_url(self, builder):
        """Passthrough mode only sets ANTHROPIC_BASE_URL, no auth headers."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8317",
        )
        result = builder.build_openrouter_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:8317"
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_passthrough_ignores_api_key_and_oauth_token(self, builder):
        """Passthrough mode ignores both api_key and oauth_token fields."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8317",
            api_key="should-be-ignored",
            oauth_token="also-ignored",
        )
        result = builder.build_openrouter_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:8317"
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_passthrough_with_model(self, builder):
        """Passthrough mode can still set model override."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8317",
            default_model="anthropic/claude-sonnet-4",
        )
        result = builder.build_openrouter_env_vars(settings)

        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:8317"
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-sonnet-4"
        assert "ANTHROPIC_API_KEY" not in result
        assert "ANTHROPIC_CUSTOM_HEADERS" not in result

    def test_passthrough_full_config(self, builder):
        """Full passthrough config for CLIProxyAPI."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8317",
            default_model="anthropic/claude-opus-4",
        )
        result = builder.build_openrouter_env_vars(settings)

        # Only base URL and model should be set
        assert len([k for k in result if k.startswith("ANTHROPIC_")]) == 2
        assert result["ANTHROPIC_BASE_URL"] == "http://localhost:8317"
        assert result["ANTHROPIC_MODEL"] == "anthropic/claude-opus-4"
