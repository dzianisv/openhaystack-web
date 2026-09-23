#!/usr/bin/env python3

import asyncio
import ipaddress
import logging
import os
import sys

from sanic import Sanic
from sanic.response import json

from sanic_cors import CORS

# backend/app.py is executed as a script, so sys.path[0] is backend/ - add the
# repository root so the shared lib/ package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import findmy_backend
from lib.findmy_backend import AccountNotConfiguredError, AccountStateError
from lib.trackers import get_tracker_locations, validate_tracker_list

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_HOURS = 24

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

app = Sanic("tracker_app")

# Messages returned to HTTP clients. They are deliberately static: the
# underlying exceptions embed the account file path (and therefore the local
# username), so only the actionable remediation step is exposed, and the full
# detail goes to the server log.
NOT_CONFIGURED_MESSAGE = (
    "No Apple account session is configured on the server. "
    f"Run `python {findmy_backend.LOGIN_COMMAND}` once on this host to sign in, "
    "then retry."
)
ACCOUNT_STATE_MESSAGE = (
    "The saved Apple account session is unusable. Delete "
    f"~/.config/{findmy_backend.APP_DIR_NAME}/{findmy_backend.ACCOUNT_FILE_NAME} "
    f"and re-run `python {findmy_backend.LOGIN_COMMAND}`."
)


def get_bind_host() -> str:
    return os.environ.get("BIND_HOST") or os.environ.get("HOST") or DEFAULT_HOST


def get_bind_port() -> int:
    raw = os.environ.get("PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"Invalid PORT value: {raw!r}")


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def get_allowed_origins(port: int) -> list:
    configured = os.environ.get("ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    origins = []
    for eel_port in {port, 8000}:
        origins.append(f"http://localhost:{eel_port}")
        origins.append(f"http://127.0.0.1:{eel_port}")
    return origins


# CORS is configured once, globally. The per-route @cross_origin decorator that
# used to be here was redundant with this and only re-applied the same defaults.
CORS(
    app,
    resources={r"/api/v1/*": {"origins": get_allowed_origins(get_bind_port())}},
    automatic_options=True,
)


def validate_trackers(payload) -> list:
    """Return the tracker list, or raise ValueError with a user-facing message."""
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    # Per-tracker rules live in lib.trackers so both entry points share them.
    return validate_tracker_list(payload.get("trackers", []))


@app.before_server_start
async def open_account_session(current_app):
    """Restore one Apple session for the whole process, if one exists.

    One long-lived AppleAccount is reused across requests: every fresh restore
    re-provisions anisette against Apple, which is precisely the behaviour that
    gets an Apple ID rate-limited or flagged.

    A missing/broken session must NOT abort startup - the operator needs the
    server (and /api/v1/health) up to discover that they have to log in. So a
    failure here is logged and the session is retried lazily per request, which
    also means a login performed while the server is running is picked up
    without a restart.
    """
    current_app.ctx.account = None
    current_app.ctx.account_lock = asyncio.Lock()
    try:
        await asyncio.to_thread(_restore_account, current_app)
    except (AccountNotConfiguredError, AccountStateError) as e:
        logger.warning("Apple account session unavailable at startup: %s", e)
    except Exception:
        logger.exception("Unexpected error restoring the Apple account session")


@app.after_server_stop
async def close_account_session(current_app):
    account = getattr(current_app.ctx, "account", None)
    if account is not None:
        current_app.ctx.account = None
        await asyncio.to_thread(findmy_backend.close_account, account)


def _restore_account(current_app):
    """Blocking: load the cached account onto ``app.ctx``. Raises on failure."""
    account = findmy_backend.load_account()
    current_app.ctx.account = account
    logger.info("Apple account session restored")
    return account


async def get_account(current_app):
    """Return the shared account, restoring it on first successful use."""
    account = getattr(current_app.ctx, "account", None)
    if account is not None:
        return account
    async with current_app.ctx.account_lock:
        account = getattr(current_app.ctx, "account", None)
        if account is not None:
            return account
        return await asyncio.to_thread(_restore_account, current_app)


@app.route("/api/v1/health", methods=["GET"])
async def get_health(request):
    """Liveness plus a plain answer to 'am I logged in?'.

    Always 200: the process is up. ``account_configured`` distinguishes "never
    logged in" from "up and ready" without the operator reading the log.
    """
    configured = await asyncio.to_thread(findmy_backend.has_account)
    return json(
        {
            "status": "ok",
            "account_configured": configured,
            "account_session_loaded": getattr(request.app.ctx, "account", None) is not None,
            "detail": None if configured else NOT_CONFIGURED_MESSAGE,
        }
    )


@app.route("/api/v1/locations", methods=["POST"])
async def post_locations(request):
    try:
        payload = request.json
    except Exception:
        payload = None
    if payload is None:
        return json({"error": "Request body must be valid JSON"}, status=400)

    try:
        trackers = validate_trackers(payload)
    except ValueError as e:
        return json({"error": str(e)}, status=400)

    # 503, not 500/401: the request itself is fine and the client can do
    # nothing about it - the *server* is not yet provisioned, and the condition
    # goes away once the operator runs the login tool (no restart needed).
    try:
        account = await get_account(request.app)
    except AccountNotConfiguredError as e:
        logger.error("Apple account not configured: %s", e)
        return json({"error": NOT_CONFIGURED_MESSAGE}, status=503)
    except AccountStateError as e:
        logger.error("Apple account session unusable: %s", e)
        return json({"error": ACCOUNT_STATE_MESSAGE}, status=503)
    except Exception:
        logger.exception("Unexpected error restoring the Apple account session")
        return json({"error": "Failed to load the Apple account session"}, status=503)

    try:
        # The lookup performs blocking network I/O; keep it off the event loop.
        r = await asyncio.to_thread(get_tracker_locations, trackers, DEFAULT_HOURS, account)
    except ValueError as e:
        return json({"error": str(e)}, status=400)
    except AccountNotConfiguredError as e:
        logger.error("Apple account not configured: %s", e)
        return json({"error": NOT_CONFIGURED_MESSAGE}, status=503)
    except AccountStateError as e:
        logger.error("Apple account session unusable: %s", e)
        return json({"error": ACCOUNT_STATE_MESSAGE}, status=503)
    except Exception:
        # Never echo the upstream exception: it can carry session/account detail.
        logger.exception("Failed to fetch locations from upstream")
        return json(
            {"error": "Failed to fetch locations from Apple's Find My service"},
            status=502,
        )
    return json(r)


def serve():
    host = get_bind_host()
    port = get_bind_port()
    if not is_loopback(host):
        logger.warning(
            "Binding to %s exposes an UNAUTHENTICATED endpoint that accepts tracker "
            "private keys and returns physical location history to anyone who can "
            "reach this host. Only do this on a trusted network.",
            host,
        )
    app.run(host=host, port=port)


if __name__ == "__main__":
    serve()
