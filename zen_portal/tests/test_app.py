"""Smoke tests for app initialization."""


def test_app_import():
    """App module imports without errors.

    This catches issues like shadowing Textual's built-in properties
    (e.g., 'notifications') which cause runtime errors.
    """
    from zen_portal.app import ZenPortalApp
    assert ZenPortalApp is not None


def test_app_instantiation(monkeypatch):
    """App can be instantiated without errors."""
    import shutil

    # Mock shutil.which to avoid dependency check failures
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mock")

    from zen_portal.app import ZenPortalApp
    app = ZenPortalApp()
    assert app is not None
    assert hasattr(app, "notification_service")
