"""
The file service without administrator access (GATEWAY_ACCESS=account): it must hold the data, and
it can't be combined with a helper.

Verifies: PX-8.
"""
import pytest

from app.config import Settings
from app.main import _file_access
from app.broker import DirectAccess


def test_it_serves_the_data_as_the_account_that_holds_it(tmp_path):
    assert isinstance(_file_access(Settings(root=tmp_path, namespace="ns", jwks_url="", account_mode=True)), DirectAccess)


def test_it_refuses_to_start_if_it_cant_reach_the_data(tmp_path):
    (tmp_path / "data").mkdir(mode=0o000)
    try:
        with pytest.raises(RuntimeError, match="can't read and write"):
            _file_access(Settings(root=tmp_path / "data", namespace="ns", jwks_url="", account_mode=True))
    finally:
        (tmp_path / "data").chmod(0o700)


@pytest.mark.parametrize("extra", [{"helper_socket": "/run/x.sock"}, {"require_isolation": True}])
def test_it_cant_be_combined_with_the_helper(tmp_path, extra):
    with pytest.raises(RuntimeError, match="can't be combined"):
        _file_access(Settings(root=tmp_path, namespace="ns", jwks_url="", account_mode=True, **extra))


def test_the_setting_is_read_from_the_environment(monkeypatch, tmp_path):
    for name, value in {"GATEWAY_ROOT": str(tmp_path), "GATEWAY_NAMESPACE": "ns", "GATEWAY_JWKS_URL": "http://k/j",
                        "GATEWAY_ACCESS": "account"}.items():
        monkeypatch.setenv(name, value)
    assert Settings.from_env().account_mode
