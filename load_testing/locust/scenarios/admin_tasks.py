"""
Admin panel load test scenarios.

Tests admin endpoints under concurrent load to ensure they don't
degrade inference performance (resource contention on DB/Redis).
"""
from __future__ import annotations

from locust import HttpUser, TaskSet, task, between, tag
from locust.exception import StopUser

from utils.auth_helper import login, get_auth_headers
from config import TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME


class AdminTaskSet(TaskSet):
    """Admin panel read-heavy load — focuses on DB query performance."""

    token: str | None = None

    def on_start(self):
        self.token = login(
            self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME
        )
        if not self.token:
            raise StopUser()

    def _h(self) -> dict:
        return get_auth_headers(self.token or "")

    @task(5)
    @tag("admin", "usage")
    def usage_summary(self):
        with self.client.get(
            "/admin/usage/summary",
            headers=self._h(),
            catch_response=True,
            name="/admin/usage/summary",
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"Usage summary failed: {resp.status_code}")

    @task(3)
    @tag("admin", "usage", "daily")
    def usage_daily(self):
        with self.client.get(
            "/admin/usage/daily",
            headers=self._h(),
            catch_response=True,
            name="/admin/usage/daily",
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"Daily usage failed: {resp.status_code}")

    @task(2)
    @tag("admin", "users")
    def list_users(self):
        with self.client.get(
            "/admin/users",
            headers=self._h(),
            catch_response=True,
            name="/admin/users",
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"List users failed: {resp.status_code}")

    @task(2)
    @tag("admin", "orgs")
    def list_orgs(self):
        with self.client.get(
            "/admin/orgs",
            headers=self._h(),
            catch_response=True,
            name="/admin/orgs",
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"List orgs failed: {resp.status_code}")

    @task(1)
    @tag("admin", "api-keys")
    def list_api_keys(self):
        with self.client.get(
            "/admin/api-keys",
            headers=self._h(),
            catch_response=True,
            name="/admin/api-keys",
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"List API keys failed: {resp.status_code}")


class AdminUser(HttpUser):
    """Admin API read-load user."""
    tasks = [AdminTaskSet]
    wait_time = between(2.0, 8.0)
    weight = 1
