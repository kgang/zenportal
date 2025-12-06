"""Tests for proxy validation service."""

import os
from unittest.mock import patch, MagicMock
import pytest

from zen_portal.services.config import OpenRouterProxySettings, ProxyAuthType
from zen_portal.services.proxy_validation import (
    ProxyValidator,
    ProxyStatus,
    ProxyCheckResult,
    ProxyValidationResult,
    validate_proxy_settings,
    get_proxy_status_line,
    get_proxy_auth_hint,
)


class TestProxyCheckResult:
    """Tests for ProxyCheckResult dataclass."""

    def test_is_ok_when_ok(self):
        result = ProxyCheckResult(ProxyStatus.OK, "Success")
        assert result.is_ok is True
        assert result.is_error is False

    def test_is_error_when_error(self):
        result = ProxyCheckResult(ProxyStatus.ERROR, "Failed")
        assert result.is_ok is False
        assert result.is_error is True

    def test_warning_is_neither(self):
        result = ProxyCheckResult(ProxyStatus.WARNING, "Warning")
        assert result.is_ok is False
        assert result.is_error is False


class TestProxyValidationResult:
    """Tests for ProxyValidationResult aggregation."""

    def test_is_ok_when_all_ok(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "Connected"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "Configured"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Valid"),
        )
        assert result.is_ok is True
        assert result.has_errors is False

    def test_has_errors_with_connectivity_error(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.ERROR, "Unreachable"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "Configured"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Valid"),
        )
        assert result.is_ok is False
        assert result.has_errors is True
        assert "unreachable" in result.summary

    def test_has_errors_with_credentials_error(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "Connected"),
            credentials=ProxyCheckResult(ProxyStatus.ERROR, "Missing"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Valid"),
        )
        assert result.is_ok is False
        assert result.has_errors is True
        assert "no credentials" in result.summary

    def test_has_errors_with_config_error(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "Connected"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "Configured"),
            configuration=ProxyCheckResult(ProxyStatus.ERROR, "Invalid"),
        )
        assert result.is_ok is False
        assert result.has_errors is True
        assert "misconfigured" in result.summary

    def test_summary_with_multiple_errors(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.ERROR, "Unreachable"),
            credentials=ProxyCheckResult(ProxyStatus.ERROR, "Missing"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Valid"),
        )
        summary = result.summary
        assert "unreachable" in summary
        assert "no credentials" in summary

    def test_summary_with_warnings_only(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "Connected"),
            credentials=ProxyCheckResult(ProxyStatus.WARNING, "Maybe invalid"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Valid"),
        )
        assert result.is_ok is False
        assert result.has_errors is False
        assert "check warnings" in result.summary


class TestProxyValidatorCredentials:
    """Tests for credential validation."""

    def test_disabled_proxy_returns_ok(self):
        settings = OpenRouterProxySettings(enabled=False)
        validator = ProxyValidator(settings)
        result = validator.validate_sync()
        assert result.credentials.is_ok

    def test_passthrough_mode_ok_without_credentials(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8080",
        )
        validator = ProxyValidator(settings)
        # Mock connectivity to not actually connect
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.is_ok
            assert "Claude Account" in result.credentials.message

    def test_api_key_mode_error_without_key(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="",
        )
        # Clear env var if set
        with patch.dict(os.environ, {}, clear=True):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_error
                assert "API key not configured" in result.credentials.message

    def test_api_key_mode_ok_with_key(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key-12345",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.is_ok

    def test_api_key_mode_warning_wrong_prefix(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="wrong-prefix-key-12345",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.status == ProxyStatus.WARNING
            assert "sk-or-" in result.credentials.hint

    def test_api_key_from_env_var(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="",  # Empty in settings
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key-12345"}):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_ok

    def test_oauth_mode_error_without_token(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:8787",
            oauth_token="",
        )
        with patch.dict(os.environ, {}, clear=True):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_error
                assert "OAuth token not configured" in result.credentials.message
                # Should suggest Claude Account mode instead
                assert "Claude Account" in result.credentials.hint

    def test_oauth_mode_ok_with_jwt_token(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:8787",
            oauth_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.is_ok
            # OAuth mode is deprecated, should suggest Claude Account
            assert "deprecated" in result.credentials.hint.lower() or "Claude Account" in result.credentials.hint

    def test_oauth_mode_with_short_token_still_ok(self):
        """OAuth mode accepts any token (deprecated mode, simplified validation)."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:8787",
            oauth_token="short",  # Any token is accepted
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            # OAuth mode is deprecated but still functional
            assert result.credentials.is_ok
            assert "deprecated" in result.credentials.hint.lower()

    def test_oauth_from_env_var(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:8787",
            oauth_token="",
        )
        with patch.dict(os.environ, {"CLAUDE_OAUTH_TOKEN": "eyJ.test.token"}):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_ok


class TestProxyValidatorConfiguration:
    """Tests for configuration validation."""

    def test_disabled_proxy_returns_ok(self):
        settings = OpenRouterProxySettings(enabled=False)
        validator = ProxyValidator(settings)
        result = validator.validate_sync()
        assert result.configuration.is_ok

    def test_openrouter_mode_without_api_key_warning(self):
        """Warn when OpenRouter mode is used without API key."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,  # Normalized to OPENROUTER
            base_url="http://localhost:8787",
            api_key="",  # No API key
        )
        with patch.dict(os.environ, {}, clear=True):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.configuration.status == ProxyStatus.WARNING
                assert "api key" in result.configuration.message.lower()

    def test_oauth_mode_valid_config(self):
        """OAuth mode with token has valid configuration."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.OAUTH,
            base_url="http://localhost:8787",
            oauth_token="some-token",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            # OAuth mode config is valid (even though deprecated)
            assert result.configuration.is_ok

    def test_claude_account_with_remote_url_warning(self):
        """Warn when using Claude Account mode with non-localhost URL."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,  # Normalized to CLAUDE_ACCOUNT
            base_url="https://remote-proxy.example.com",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.configuration.status == ProxyStatus.WARNING
            assert "remote" in result.configuration.message.lower()

    def test_model_without_provider_prefix_warning(self):
        """Warn when model name lacks provider prefix for API_KEY mode."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key",
            default_model="claude-sonnet-4",  # Missing provider/ prefix
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.configuration.status == ProxyStatus.WARNING
            assert "provider" in result.configuration.message.lower()

    def test_model_with_provider_prefix_ok(self):
        """Accept model name with provider prefix."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key",
            default_model="anthropic/claude-sonnet-4",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.configuration.is_ok


class TestProxyValidatorConnectivity:
    """Tests for connectivity checks."""

    def test_disabled_proxy_returns_ok(self):
        settings = OpenRouterProxySettings(enabled=False)
        validator = ProxyValidator(settings)
        result = validator.validate_sync()
        assert result.connectivity.is_ok

    def test_empty_url_uses_default(self):
        """Empty base_url uses mode-appropriate default (effective_base_url)."""
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="",  # Empty URL
        )
        validator = ProxyValidator(settings)
        # Should try to connect to default localhost:8787 (OpenRouter default)
        result = validator.validate_sync()
        # Will fail to connect but error message shows it used the default port
        assert "8787" in result.connectivity.message or result.connectivity.is_ok

    def test_invalid_url_returns_error(self):
        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="not-a-valid-url",
        )
        validator = ProxyValidator(settings)
        result = validator.validate_sync()
        assert result.connectivity.is_error

    @patch('socket.socket')
    def test_connection_success(self, mock_socket_class):
        """Test successful connection."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.return_value = None

        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test",
        )
        validator = ProxyValidator(settings)
        result = validator.validate_sync()

        assert result.connectivity.is_ok
        mock_socket.connect.assert_called_once_with(("localhost", 8787))

    @patch('socket.socket')
    def test_connection_refused_yrouter_hint(self, mock_socket_class):
        """Test connection refused with y-router hint."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = ConnectionRefusedError()

        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test",
        )
        validator = ProxyValidator(settings)
        result = validator.validate_sync()

        assert result.connectivity.is_error
        assert "docker-compose" in result.connectivity.hint.lower()

    @patch('socket.socket')
    def test_connection_refused_cliproxyapi_hint(self, mock_socket_class):
        """Test connection refused with CLIProxyAPI hint."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = ConnectionRefusedError()

        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.PASSTHROUGH,
            base_url="http://localhost:8080",
        )
        validator = ProxyValidator(settings)
        result = validator.validate_sync()

        assert result.connectivity.is_error
        assert "cliproxyapi" in result.connectivity.hint.lower()


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_validate_proxy_settings_none(self):
        result = validate_proxy_settings(None)
        assert result.connectivity.status == ProxyStatus.UNKNOWN

    def test_validate_proxy_settings_disabled(self):
        settings = OpenRouterProxySettings(enabled=False)
        result = validate_proxy_settings(settings)
        assert result.connectivity.is_ok

    def test_get_proxy_status_line_disabled(self):
        settings = OpenRouterProxySettings(enabled=False)
        line = get_proxy_status_line(settings)
        assert line == "proxy: disabled"

    def test_get_proxy_status_line_none(self):
        line = get_proxy_status_line(None)
        assert line == "proxy: disabled"

    @patch('socket.socket')
    def test_get_proxy_status_line_ok(self, mock_socket_class):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.return_value = None

        settings = OpenRouterProxySettings(
            enabled=True,
            auth_type=ProxyAuthType.API_KEY,
            base_url="http://localhost:8787",
            api_key="sk-or-test",
        )
        line = get_proxy_status_line(settings)
        assert "OpenRouter" in line

    def test_get_proxy_auth_hint_api_key(self):
        hint = get_proxy_auth_hint(ProxyAuthType.API_KEY)
        assert "openrouter" in hint.lower()

    def test_get_proxy_auth_hint_oauth(self):
        """OAuth mode (deprecated) returns empty hint."""
        hint = get_proxy_auth_hint(ProxyAuthType.OAUTH)
        # OAuth is deprecated, no specific setup hint
        assert hint == ""

    def test_get_proxy_auth_hint_passthrough(self):
        hint = get_proxy_auth_hint(ProxyAuthType.PASSTHROUGH)
        assert "login" in hint.lower()
