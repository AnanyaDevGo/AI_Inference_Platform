"""
Auth helper utilities — shared login and token management for all Locust tasks.
Handles token caching, refresh, and multi-tenant credential management.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# Thread-safe token cache: email -> {access_token, refresh_token, expires_at}
_token_cache: dict[str, dict] = {}
_lock = threading.Lock()


def login(client, email: str, password: str, name: str = "Load Test User") -> Optional[str]:
    """
    Log in and return the access_token. Caches token per email.
    Returns None on failure.
    """
    with _lock:
        cached = _token_cache.get(email)
        if cached and cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]

    with client.post(
        "/auth/login",
        json={"email": email, "password": password},
        catch_response=True,
        name="/auth/login",
    ) as resp:
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            if token:
                with _lock:
                    _token_cache[email] = {
                        "access_token": token,
                        "expires_at": time.time() + 3500,  # ~1 hour
                    }
                return token
            resp.failure(f"No access_token in response: {resp.text[:200]}")
            return None
        elif resp.status_code == 404:
            # User doesn't exist — attempt registration then login
            resp.success()
            if _register_user(client, email, password, name):
                return login(client, email, password, name)
            return None
        else:
            resp.failure(f"Login failed: {resp.status_code} {resp.text[:200]}")
            return None


def _register_user(client, email: str, password: str, name: str) -> bool:
    """Auto-register a load test user if not found."""
    with client.post(
        "/auth/register",
        json={"email": email, "password": password, "name": name},
        catch_response=True,
        name="/auth/register [setup]",
    ) as resp:
        if resp.status_code in (200, 201):
            resp.success()
            return True
        # 400 = already exists = fine
        if resp.status_code == 400:
            resp.success()
            return True
        resp.failure(f"Registration failed: {resp.status_code}")
        return False


def get_auth_headers(token: str) -> dict:
    """Return Authorization header dict for a given token."""
    return {"Authorization": f"Bearer {token}"}


def invalidate_token(email: str) -> None:
    """Remove a token from cache (e.g., after 401)."""
    with _lock:
        _token_cache.pop(email, None)
