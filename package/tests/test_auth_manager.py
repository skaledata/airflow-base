"""Tests for the SkaleData auth manager (proxy-trusted per-user identity).

Run inside the built image in CI (airflow importable). The FastAPI routes
are exercised with TestClient; JWT signing uses a test secret injected via
env before airflow config is touched.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("AIRFLOW__API_AUTH__JWT_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skale.auth.manager import (  # noqa: E402
    IDENTITY_HEADER,
    MACHINE_USERNAME,
    SkaleDataAuthManager,
)


@pytest.fixture(scope="session", autouse=True)
def _airflow_db() -> None:
    """Token validation consults the revoked-token table — migrate sqlite once."""
    import subprocess

    subprocess.run(["airflow", "db", "migrate"], check=True, capture_output=True)


def _manager() -> SkaleDataAuthManager:
    try:
        return SkaleDataAuthManager()
    except TypeError:
        # 3.3+ managers may take context kwargs; fall back to no-arg via base
        return SkaleDataAuthManager.__new__(SkaleDataAuthManager)


def test_login_url_points_at_identity_route() -> None:
    assert _manager().get_url_login() == "/auth/identity/login"


def test_header_identity_becomes_admin_user() -> None:
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    resp = client.get("/token", headers={IDENTITY_HEADER: "jane@customer.com"})
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    user = asyncio.run(manager.get_user_from_token(token))
    assert user.get_name() == "jane@customer.com"
    assert user.role == "ADMIN"


def test_missing_header_falls_back_to_machine_identity() -> None:
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    resp = client.get("/token")
    assert resp.status_code == 201
    user = asyncio.run(manager.get_user_from_token(resp.json()["access_token"]))
    assert user.get_name() == MACHINE_USERNAME
    assert user.role == "ADMIN"


def test_post_token_variants_exist_for_cli() -> None:
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    assert client.post("/token").status_code == 201
    assert client.post("/token/cli").status_code == 201


def test_identity_login_sets_cookie_and_redirects() -> None:
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    resp = client.get(
        "/identity/login",
        headers={IDENTITY_HEADER: "jane@customer.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert "_token" in resp.cookies
    user = asyncio.run(manager.get_user_from_token(resp.cookies["_token"]))
    assert user.get_name() == "jane@customer.com"


def test_admin_user_passes_authorization() -> None:
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    user = asyncio.run(
        manager.get_user_from_token(
            client.get("/token", headers={IDENTITY_HEADER: "jane@customer.com"}).json()["access_token"]
        )
    )
    assert manager.is_authorized_dag(method="PUT", user=user)
    assert manager.is_authorized_configuration(method="GET", user=user)
    assert manager.is_authorized_variable(method="DELETE", user=user)


def test_spoofed_header_cannot_escalate_role() -> None:
    # The header only names the actor; role is pinned ADMIN server-side and
    # tokens are signed — a forged token body fails signature validation.
    manager = _manager()
    client = TestClient(manager.get_fastapi_app())
    token = client.get("/token", headers={IDENTITY_HEADER: "x@y.z"}).json()["access_token"]
    tampered = token[:-10] + ("A" * 10)
    try:
        asyncio.run(manager.get_user_from_token(tampered))
        raised = False
    except Exception:
        raised = True
    assert raised
