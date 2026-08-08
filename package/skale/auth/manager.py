"""SkaleData auth manager: proxy-trusted per-user identity for Airflow 3.

The SkaleData data-plane proxy authenticates every browser request (Clerk
session -> signed data-plane JWT) and injects the verified identity as the
``X-Forwarded-Email`` header, after stripping any client-sent value. This
auth manager turns that header into a real per-user Airflow identity so the
audit log (``Log.owner``), manual-run attribution
(``DagRun.triggering_user_name``), and DAG-run/task-instance note authorship
all record WHO did it.

Roles: the user's role (ADMIN / OP / USER / VIEWER — SimpleAuthManager's
built-in tiers) is resolved from a roster file the SkaleData control plane
maintains as a Kubernetes Secret mounted at ``/etc/skaledata/identity/
roles.json``::

    {"default_role": "ADMIN", "users": {"jane@customer.com": "VIEWER"}}

Emails match case-insensitively. Users absent from the roster get
``default_role``. A missing or unparseable roster fails OPEN to everyone-
ADMIN — byte-for-byte the ``simple_auth_manager_all_admins`` posture this
manager originally replaced — so deployments without the mount (or predating
it) keep today's behavior. The roster is re-read when the file's mtime
changes, which the kubelet's secret-refresh symlink swap triggers within
about a minute of a control-plane update; no pod restart needed. Role
changes take effect at the next JWT mint (login/token exchange) — existing
signed sessions keep their role until expiry.

Trust model: unchanged for machine traffic. The api-server is reachable only
through the SkaleData proxy path (NGINX ingress allowlisted to the proxy
egress IP); in-cluster callers could mint an anonymous admin token from
``GET /auth/token`` under all-admins, and still can here — the machine
identity is pinned ADMIN so the proxy's token exchange and in-pod CLI never
lose access. The header only ever *names* the browser actor; its role comes
from the control-plane-owned roster, never from the client. Do NOT enable
``[core] simple_auth_manager_all_admins`` with this manager: that config
would install ``SimpleAllAdminMiddleware``, which stamps an anonymous Bearer
token on every request and (being higher precedence than the session cookie)
would erase per-user attribution again.

Machine tokens: the SkaleData proxy exchanges API keys / app tokens for an
upstream Airflow JWT via an unauthenticated ``GET /auth/token`` — a route
shape only SimpleAuthManager provides. This manager keeps that route
byte-compatible (plus the POST variants for in-pod ``airflow`` CLI use), so
`skale app token` / `skale app exec` and ``sdk_`` API keys keep working with
zero proxy changes.

Local development (``skale airflow init`` docker-compose) does not use this
manager — the compose file pins its own auth config — so nothing here
affects local pipeline testing.
"""

from __future__ import annotations

import json
import logging
import os

from airflow.api_fastapi.auth.managers.base_auth_manager import COOKIE_NAME_JWT_TOKEN
from airflow.api_fastapi.auth.managers.simple.datamodels.login import LoginResponse
from airflow.api_fastapi.auth.managers.simple.simple_auth_manager import SimpleAuthManager
from airflow.api_fastapi.auth.managers.simple.user import SimpleAuthManagerUser
from airflow.api_fastapi.common.router import AirflowRouter
from airflow.configuration import conf
from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse

# Injected by the SkaleData proxy for browser traffic (anti-spoof stripped at
# the proxy; see skaledata/apps/proxy/cmd/proxy/main.go). Absent on direct
# in-cluster requests, which fall back to the anonymous machine identity.
IDENTITY_HEADER = "X-Forwarded-Email"

# Actor recorded when no identity header is present (machine/API access and
# any non-proxied path). Distinct from SimpleAuthManager's "Anonymous" so
# audit rows distinguish "programmatic" from "pre-identity legacy".
MACHINE_USERNAME = "api@skaledata"

# Mounted by Airflow at {API_ROOT_PATH}auth — import kept lazy-safe: the
# constant lives in airflow.api_fastapi.app in 3.2.x, but hardcoding the
# public prefix avoids importing the whole app module at class-definition
# time in non-api-server processes (scheduler, workers, CLI parsing).
AUTH_PREFIX = "/auth"

# Control-plane-owned roster secret, mounted read-only into the api-server.
# SKALE_IDENTITY_ROLES_FILE is a dev/test override only.
ROLES_FILE_ENV = "SKALE_IDENTITY_ROLES_FILE"
DEFAULT_ROLES_FILE = "/etc/skaledata/identity/roles.json"

# Fail-open role: no roster (or a broken one) must reproduce the pre-roster
# everyone-ADMIN behavior, never lock a fleet out.
FALLBACK_ROLE = "ADMIN"

_VALID_ROLES = frozenset({"ADMIN", "OP", "USER", "VIEWER"})

log = logging.getLogger(__name__)

# (mtime, default_role, users-by-lowercased-email). mtime -1.0 marks the
# "file absent/unreadable" parse; os.stat is re-run on every resolve, so an
# appearing file invalidates immediately.
_roster_cache: tuple[float, str, dict[str, str]] | None = None


def _load_roster() -> tuple[str, dict[str, str]]:
    """Return (default_role, users) from the roster file, mtime-cached.

    The kubelet updates a mounted Secret by swapping the ``..data`` symlink,
    which bumps the file's mtime — so a plain stat is enough to detect
    control-plane roster updates without re-parsing on every request.
    """
    global _roster_cache
    path = os.environ.get(ROLES_FILE_ENV, DEFAULT_ROLES_FILE)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        _roster_cache = (-1.0, FALLBACK_ROLE, {})
        return FALLBACK_ROLE, {}

    if _roster_cache is not None and _roster_cache[0] == mtime:
        return _roster_cache[1], _roster_cache[2]

    default_role = FALLBACK_ROLE
    users: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        candidate = str(raw.get("default_role", FALLBACK_ROLE)).upper()
        if candidate in _VALID_ROLES:
            default_role = candidate
        else:
            log.warning(
                "identity roster: invalid default_role %r, using %s", candidate, FALLBACK_ROLE
            )
        for email, role in (raw.get("users") or {}).items():
            role_up = str(role).upper()
            if role_up in _VALID_ROLES:
                users[str(email).strip().lower()] = role_up
            else:
                log.warning("identity roster: dropping %r with invalid role %r", email, role)
    except Exception:
        # Fail open: a malformed roster must not lock anyone out.
        log.exception(
            "identity roster: failed to parse %s; falling back to everyone-%s",
            path,
            FALLBACK_ROLE,
        )
        _roster_cache = (mtime, FALLBACK_ROLE, {})
        return FALLBACK_ROLE, {}

    _roster_cache = (mtime, default_role, users)
    return default_role, users


def _resolve_role(username: str) -> str:
    """Roster role for ``username``; machine identity is always ADMIN."""
    if username == MACHINE_USERNAME:
        # The proxy's machine-token exchange and in-pod CLI must never lose
        # access, regardless of what the roster says.
        return "ADMIN"
    default_role, users = _load_roster()
    return users.get(username.strip().lower(), default_role)


class SkaleDataAuthManager(SimpleAuthManager):
    """Per-user identity from the proxy header; role from the roster secret."""

    def init(self) -> None:
        # Skip SimpleAuthManager.init(): it generates and prints a passwords
        # file for its static user list, which this manager doesn't use.
        return None

    def _user_from_request(self, request: Request) -> SimpleAuthManagerUser:
        username = (request.headers.get(IDENTITY_HEADER) or "").strip() or MACHINE_USERNAME
        return SimpleAuthManagerUser(username=username, role=_resolve_role(username))

    def get_url_login(self, **kwargs) -> str:
        return AUTH_PREFIX + "/identity/login"

    def get_fastapi_app(self) -> FastAPI | None:
        # Deferred: airflow.api_fastapi.app pulls in the full app config —
        # only the api-server (the sole caller of this method) pays for it.
        from airflow.api_fastapi.app import get_cookie_path

        router = AirflowRouter(tags=["SkaleDataAuthManagerLogin"])
        manager = self

        @router.get("/identity/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        def identity_login(request: Request) -> RedirectResponse:
            """Mint a JWT for the proxy-verified user and set the session cookie."""
            user = manager._user_from_request(request)
            response = RedirectResponse(url=conf.get("api", "base_url", fallback="/"))
            secure = request.base_url.scheme == "https" or bool(
                conf.get("api", "ssl_cert", fallback="")
            )
            response.set_cookie(
                COOKIE_NAME_JWT_TOKEN,
                manager.generate_jwt(user),
                path=get_cookie_path(),
                secure=secure,
                httponly=True,
            )
            return response

        @router.get("/token", status_code=status.HTTP_201_CREATED)
        def create_token_get(request: Request) -> LoginResponse:
            """Anonymous machine token — byte-compatible with the proxy's exchange."""
            user = manager._user_from_request(request)
            return LoginResponse(access_token=manager.generate_jwt(user))

        @router.post("/token", status_code=status.HTTP_201_CREATED)
        def create_token_post(request: Request) -> LoginResponse:
            """POST variant; any body is ignored (identity comes from the header)."""
            user = manager._user_from_request(request)
            return LoginResponse(access_token=manager.generate_jwt(user))

        @router.post("/token/cli", status_code=status.HTTP_201_CREATED)
        def create_token_cli(request: Request) -> LoginResponse:
            """CLI token for in-pod ``airflow`` commands."""
            expiration = conf.getint("api_auth", "jwt_cli_expiration_time")
            return LoginResponse(
                access_token=manager.generate_jwt(
                    manager._user_from_request(request), expiration_time_in_seconds=expiration
                )
            )

        app = FastAPI(
            title="SkaleData auth manager sub application",
            description=(
                "Login + token routes for the SkaleData auth manager. Browser identity "
                "comes from the proxy-verified X-Forwarded-Email header with its role "
                "resolved from the control-plane roster secret; machine tokens are "
                "issued anonymously and always carry ADMIN."
            ),
        )
        app.include_router(router)
        return app
