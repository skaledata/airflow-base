"""SkaleData auth manager: proxy-trusted per-user identity for Airflow 3.

The SkaleData data-plane proxy authenticates every browser request (Clerk
session -> signed data-plane JWT) and injects the verified identity as the
``X-Forwarded-Email`` header, after stripping any client-sent value. This
auth manager turns that header into a real per-user Airflow identity so the
audit log (``Log.owner``), manual-run attribution
(``DagRun.triggering_user_name``), and DAG-run/task-instance note authorship
all record WHO did it — while keeping every user ADMIN, exactly like the
``simple_auth_manager_all_admins`` fleet default it replaces.

Trust model: identical to all-admins mode. The api-server is reachable only
through the SkaleData proxy path (NGINX ingress allowlisted to the proxy
egress IP); in-cluster callers could already mint an anonymous admin token
from ``GET /auth/token`` under all-admins, and still can here — the header
only ever *names* the actor, it never grants more than the ADMIN everyone
already has. Do NOT enable ``[core] simple_auth_manager_all_admins`` with
this manager: that config would install ``SimpleAllAdminMiddleware``, which
stamps an anonymous Bearer token on every request and (being higher
precedence than the session cookie) would erase per-user attribution again.

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


class SkaleDataAuthManager(SimpleAuthManager):
    """Per-user identity from the proxy header; everyone stays ADMIN."""

    def init(self) -> None:
        # Skip SimpleAuthManager.init(): it generates and prints a passwords
        # file for its static user list, which this manager doesn't use.
        return None

    def _user_from_request(self, request: Request) -> SimpleAuthManagerUser:
        username = (request.headers.get(IDENTITY_HEADER) or "").strip() or MACHINE_USERNAME
        return SimpleAuthManagerUser(username=username, role="ADMIN")

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
                "comes from the proxy-verified X-Forwarded-Email header; machine tokens "
                "are issued anonymously with the same ADMIN role, matching the trust "
                "model of SimpleAuthManager's all-admins mode."
            ),
        )
        app.include_router(router)
        return app
