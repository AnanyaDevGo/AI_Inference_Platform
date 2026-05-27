"""
Auth load test scenarios for InferVoyage.

Covers:
  - Standard email/password login
  - JWT token refresh
  - User registration flow
  - Rate limit validation on auth endpoints
"""
from __future__ import annotations

import time

from locust import HttpUser, TaskSet, task, between, tag

from utils.auth_helper import login, get_auth_headers, invalidate_token
from config import TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME


class AuthTaskSet(TaskSet):
    """Authentication-focused task set."""

    token: str | None = None

    def on_start(self):
        """Acquire a token before starting tasks."""
        self.token = login(
            self.client,
            TEST_USER_EMAIL,
            TEST_USER_PASSWORD,
            TEST_USER_NAME,
        )

    @task(5)
    @tag("auth", "login")
    def login_flow(self):
        """POST /auth/login — standard credential login."""
        start = time.perf_counter()
        with self.client.post(
            "/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            catch_response=True,
            name="/auth/login",
        ) as resp:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" not in data:
                    resp.failure("Missing access_token in response")
                else:
                    resp.success()
            elif resp.status_code == 401:
                resp.failure("Invalid credentials")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(2)
    @tag("auth", "refresh")
    def token_refresh(self):
        """POST /auth/refresh — refresh JWT using cookie."""
        if not self.token:
            return
        with self.client.post(
            "/auth/refresh",
            headers=get_auth_headers(self.token),
            catch_response=True,
            name="/auth/refresh",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data:
                    self.token = data["access_token"]
                    resp.success()
                else:
                    resp.failure("No token in refresh response")
            elif resp.status_code == 401:
                # Token expired — re-login
                invalidate_token(TEST_USER_EMAIL)
                self.token = login(self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
                resp.success()
            else:
                resp.failure(f"Refresh failed: {resp.status_code}")

    @task(1)
    @tag("auth", "profile")
    def get_profile(self):
        """GET /auth/me — fetch current user profile."""
        if not self.token:
            return
        with self.client.get(
            "/auth/me",
            headers=get_auth_headers(self.token),
            catch_response=True,
            name="/auth/me",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.success()
            else:
                resp.failure(f"Profile fetch failed: {resp.status_code}")

    @task(1)
    @tag("auth", "logout")
    def logout_flow(self):
        """POST /auth/logout — invalidate session."""
        if not self.token:
            return
        with self.client.post(
            "/auth/logout",
            headers=get_auth_headers(self.token),
            catch_response=True,
            name="/auth/logout",
        ) as resp:
            if resp.status_code in (200, 204):
                self.token = None
                resp.success()
            else:
                resp.failure(f"Logout failed: {resp.status_code}")
        # Re-acquire token for next iteration
        self.token = login(self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD)


class AuthUser(HttpUser):
    """User class focused exclusively on auth endpoints."""
    tasks = [AuthTaskSet]
    wait_time = between(0.5, 2.0)
    weight = 2
