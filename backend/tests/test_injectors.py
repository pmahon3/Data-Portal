"""The shared Keycloak admin client never writes its secret to the log."""
import logging

from core.services import injectors


def test_the_admin_secret_is_never_logged(monkeypatch, caplog):
    secret = "s3cr3t-value-that-must-not-be-logged"
    monkeypatch.setenv("KEYCLOAK_ADMIN_CLIENT_SECRET", secret)
    monkeypatch.setattr(injectors, "_keycloak_admin", None)
    monkeypatch.setattr(injectors, "KeycloakOpenIDConnection", lambda **kwargs: None)

    class FakeAdmin:
        def __init__(self, connection):
            pass

        def get_users(self, query):
            return []

    monkeypatch.setattr(injectors, "KeycloakAdmin", FakeAdmin)
    with caplog.at_level(logging.DEBUG):
        injectors._get_keycloak_admin()
    assert secret[:4] not in caplog.text
