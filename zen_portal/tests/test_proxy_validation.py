"""Tests for ProxyValidator (y-router connectivity and configuration checks)."""

import os
import pytest
from unittest.mock import patch, MagicMock

from zen_portal.services.proxy_validation import (
    ProxyValidator,
    ProxyStatus,
    ProxyCheckResult,
    ProxyValidationResult,
    validate_proxy_settings,
    get_proxy_status_line,
)
from zen_portal.services.config import ProxySettings


class TestProxyCheckResult:
    """Tests for ProxyCheckResult dataclass."""

    def test_is_ok_when_status_ok(self):
        result = ProxyCheckResult(ProxyStatus.OK, "Test")
        assert result.is_ok is True
        assert result.is_error is False

    def test_is_error_when_status_error(self):
        result = ProxyCheckResult(ProxyStatus.ERROR, "Test")
        assert result.is_ok is False
        assert result.is_error is True

    def test_warning_is_neither_ok_nor_error(self):
        result = ProxyCheckResult(ProxyStatus.WARNING, "Test")
        assert result.is_ok is False
        assert result.is_error is False


class TestProxyValidationResult:
    """Tests for ProxyValidationResult aggregation."""

    def test_is_ok_when_all_ok(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "OK"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "OK"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
        )
        assert result.is_ok is True
        assert result.has_errors is False

    def test_has_errors_when_any_error(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.ERROR, "Error"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "OK"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
        )
        assert result.is_ok is False
        assert result.has_errors is True

    def test_summary_when_ok(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "OK"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "OK"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
        )
        assert result.summary == "proxy ready"

    def test_summary_lists_errors(self):
        result = ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.ERROR, "Error"),
            credentials=ProxyCheckResult(ProxyStatus.ERROR, "Error"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
        )
        assert "unreachable" in result.summary
        assert "no credentials" in result.summary


class TestProxyValidatorCredentials:
    """Tests for credential validation."""

    def test_disabled_proxy_always_ok(self):
        settings = ProxySettings(enabled=False)
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.is_ok

    def test_error_without_api_key(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="",
        )
        with patch.dict(os.environ, {}, clear=True):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_error
                assert "API key" in result.credentials.message

    def test_ok_with_api_key_in_settings(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key-12345",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.is_ok

    def test_ok_with_api_key_from_env(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="",
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-env-key-12345"}):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.credentials.is_ok

    def test_warning_for_non_openrouter_key_format(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="some-other-format-key",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.credentials.status == ProxyStatus.WARNING
            assert "sk-or-" in result.credentials.hint


class TestProxyValidatorConfiguration:
    """Tests for configuration validation."""

    def test_model_without_provider_prefix_warning(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key",
            default_model="claude-sonnet-4",  # Missing provider prefix
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.configuration.status == ProxyStatus.WARNING
            assert "provider" in result.configuration.hint.lower()

    def test_model_with_provider_prefix_ok(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key",
            default_model="anthropic/claude-sonnet-4",
        )
        validator = ProxyValidator(settings)
        with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
            result = validator.validate_sync()
            assert result.configuration.is_ok

    def test_missing_api_key_configuration_warning(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="",
        )
        with patch.dict(os.environ, {}, clear=True):
            validator = ProxyValidator(settings)
            with patch.object(validator, '_check_connectivity', return_value=ProxyCheckResult(ProxyStatus.OK, "Mocked")):
                result = validator.validate_sync()
                assert result.configuration.status == ProxyStatus.WARNING


class TestProxyValidatorConnectivity:
    """Tests for connectivity checks."""

    def test_connectivity_error_shows_hint(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="sk-or-test",
        )
        validator = ProxyValidator(settings)

        # Mock socket to fail
        with patch('socket.socket') as mock_socket:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError()
            mock_socket.return_value = mock_sock

            result = validator._check_connectivity(settings)
            assert result.is_error
            assert "y-router" in result.hint.lower()

    def test_connectivity_ok_when_disabled(self):
        settings = ProxySettings(enabled=False)
        validator = ProxyValidator(settings)
        result = validator._check_connectivity(settings)
        assert result.is_ok


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_validate_proxy_settings_with_callback(self):
        callback_called = []

        def callback(result):
            callback_called.append(result)

        settings = ProxySettings(enabled=False)
        result = validate_proxy_settings(settings, on_complete=callback)

        assert len(callback_called) == 1
        assert callback_called[0] == result

    def test_get_proxy_status_line_disabled(self):
        settings = ProxySettings(enabled=False)
        line = get_proxy_status_line(settings)
        assert line == "proxy: disabled"

    def test_get_proxy_status_line_none(self):
        line = get_proxy_status_line(None)
        assert line == "proxy: disabled"

    def test_get_proxy_status_line_ok(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="sk-or-test-key",
        )
        with patch.object(ProxyValidator, 'validate_sync') as mock_validate:
            mock_validate.return_value = ProxyValidationResult(
                connectivity=ProxyCheckResult(ProxyStatus.OK, "OK"),
                credentials=ProxyCheckResult(ProxyStatus.OK, "OK"),
                configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
            )
            line = get_proxy_status_line(settings)
            assert "y-router" in line

    def test_get_proxy_status_line_error(self):
        settings = ProxySettings(
            enabled=True,
            base_url="http://localhost:8787",
            api_key="",
        )
        with patch.object(ProxyValidator, 'validate_sync') as mock_validate:
            mock_validate.return_value = ProxyValidationResult(
                connectivity=ProxyCheckResult(ProxyStatus.ERROR, "Error"),
                credentials=ProxyCheckResult(ProxyStatus.OK, "OK"),
                configuration=ProxyCheckResult(ProxyStatus.OK, "OK"),
            )
            line = get_proxy_status_line(settings)
            assert "unreachable" in line
