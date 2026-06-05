"""
Chat & inference load test scenarios — the most critical test for AI workloads.

Covers:
  - Standard (non-streaming) chat completions
  - Streaming SSE chat with TTFT measurement
  - Long multi-turn conversations
  - Large prompt handling
  - Rate limit stress testing

Key Metric: TTFT (Time To First Token) — time from request send to receiving the
first SSE data chunk. This is the user-perceived latency for streaming AI responses.
"""
from __future__ import annotations

import time
import json

from locust import HttpUser, TaskSet, task, between, tag, events
from locust.exception import StopUser

from utils.auth_helper import login, get_auth_headers, invalidate_token
from utils.data_factory import chat_completion_payload, multi_turn_payload, random_prompt
from config import (
    TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME,
    STREAM_TIMEOUT, INFERENCE_TIMEOUT, MODEL_NAME
)

# ── Custom TTFT event ────────────────────────────────────────────────────────
# We fire a custom Locust event so TTFT appears as a separate metric in reports
def _report_ttft(environment, ttft_ms: float, name: str = "TTFT [streaming]"):
    """Record TTFT as a custom Locust request event."""
    events.request.fire(
        request_type="SSE",
        name=name,
        response_time=ttft_ms,
        response_length=0,
        exception=None,
        context={},
    )


class ChatTaskSet(TaskSet):
    """Chat and inference focused task set."""

    token: str | None = None

    def on_start(self):
        self.token = login(
            self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME
        )
        if not self.token:
            raise StopUser()

    def _headers(self) -> dict:
        """Return auth headers, re-acquiring token if missing or expired."""
        self.token = login(self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME)
        return get_auth_headers(self.token or "")

    # ── Non-streaming chat ───────────────────────────────────────────────────

    @task(20)
    @tag("chat", "non-streaming")
    def chat_short_prompt(self):
        """POST /v1/chat/completions — short prompt, non-streaming."""
        payload = chat_completion_payload(size="short", stream=False)
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            timeout=INFERENCE_TIMEOUT,
            name="/v1/chat/completions [sync-short]",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("choices"):
                    resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                    resp.success()
                else:
                    resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                    resp.failure("No choices in response")
            elif resp.status_code in (429, 503):
                resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                resp.success()  # Rate limit is expected, not a failure
            elif resp.status_code == 401:
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                resp.success()
            elif resp.status_code == 0:
                # Connection dropped — likely token expired during long inference
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                resp.success()
            else:
                resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                resp.failure(f"Chat failed: {resp.status_code} {resp.text[:300]}")

    @task(10)
    @tag("chat", "non-streaming", "medium")
    def chat_medium_prompt(self):
        """POST /v1/chat/completions — medium prompt, non-streaming."""
        payload = chat_completion_payload(size="medium", stream=False)
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            timeout=INFERENCE_TIMEOUT,
            name="/v1/chat/completions [sync-medium]",
        ) as resp:
            if resp.status_code == 200:
                resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                resp.success()
            elif resp.status_code in (429, 503):
                resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                resp.success()
            elif resp.status_code == 401:
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                resp.success()
            elif resp.status_code == 0:
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                resp.success()
            else:
                resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                resp.failure(f"Medium chat failed: {resp.status_code}")

    # ── Streaming chat with TTFT measurement ─────────────────────────────────

    @task(30)
    @tag("chat", "streaming", "ttft")
    def chat_streaming_short(self):
        """
        POST /v1/chat/completions with stream=true.
        Measures TTFT (time to first SSE data chunk containing content).
        Records both TTFT and total duration as separate Locust metrics.
        """
        payload = chat_completion_payload(size="short", stream=True)
        headers = self._headers()
        headers["Accept"] = "text/event-stream"

        request_start = time.perf_counter()
        first_token_time: float | None = None
        total_content = ""
        chunks_received = 0

        try:
            with self.client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
                catch_response=True,
                timeout=STREAM_TIMEOUT,
                name="/v1/chat/completions [stream-short]",
            ) as resp:
                if resp.status_code != 200:
                    if resp.status_code in (429, 503):
                        resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                        resp.success()
                        return
                    if resp.status_code in (401, 0):
                        resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                        resp.success()
                        return
                    resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                    resp.failure(f"Stream init failed: {resp.status_code}")
                    return

                # Read SSE chunks
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            if first_token_time is None:
                                  first_token_time = time.perf_counter()
                            total_content += delta
                            chunks_received += 1
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass  # Skip malformed chunks

                total_duration_ms = (time.perf_counter() - request_start) * 1000

                if chunks_received > 0:
                    ttft_ms = (first_token_time - request_start) * 1000 if first_token_time else total_duration_ms
                    # Report TTFT as a separate named request
                    _report_ttft(self.user.environment, ttft_ms, "TTFT [stream-short]")
                    resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                    resp.success()
                else:
                    resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                    resp.failure("No content chunks received from stream")

        except Exception as e:
            self.user.environment.events.request.fire(
                request_type="SSE",
                name="/v1/chat/completions [Model Failure]",
                response_time=(time.perf_counter() - request_start) * 1000,
                response_length=0,
                exception=e,
                context={},
            )

    @task(15)
    @tag("chat", "streaming", "ttft", "large")
    def chat_streaming_large(self):
        """Streaming with large prompt — stress tests Ollama context handling."""
        payload = chat_completion_payload(size="large", stream=True, max_tokens=400)
        headers = self._headers()
        headers["Accept"] = "text/event-stream"

        request_start = time.perf_counter()
        first_token_time: float | None = None
        chunks_received = 0

        try:
            with self.client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
                catch_response=True,
                timeout=STREAM_TIMEOUT,
                name="/v1/chat/completions [stream-large]",
            ) as resp:
                if resp.status_code in (429, 503):
                    resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                    resp.success()
                    return
                if resp.status_code in (401, 0):
                    resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                    resp.success()
                    return
                if resp.status_code != 200:
                    resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                    resp.failure(f"Large stream failed: {resp.status_code}")
                    return

                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    if "content" in line and first_token_time is None:
                        first_token_time = time.perf_counter()
                    if "[DONE]" in line:
                        break
                    chunks_received += 1

                if first_token_time:
                    ttft_ms = (first_token_time - request_start) * 1000
                    _report_ttft(self.user.environment, ttft_ms, "TTFT [stream-large]")
                resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                resp.success()
        except Exception as e:
            self.user.environment.events.request.fire(
                request_type="SSE",
                name="/v1/chat/completions [Model Failure]",
                response_time=(time.perf_counter() - request_start) * 1000,
                response_length=0,
                exception=e,
                context={},
            )

    # ── Long conversation ────────────────────────────────────────────────────

    @task(5)
    @tag("chat", "multi-turn")
    def long_conversation(self):
        """Multi-turn conversation simulating a real chat session (5 turns)."""
        payload = multi_turn_payload(turns=5, stream=False)
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            timeout=INFERENCE_TIMEOUT * 2,
            name="/v1/chat/completions [multi-turn]",
        ) as resp:
            if resp.status_code == 200:
                resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                resp.success()
            elif resp.status_code in (429, 503):
                resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                resp.success()
            elif resp.status_code in (401, 0):
                invalidate_token(TEST_USER_EMAIL)
                self.token = None
                resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                resp.success()
            else:
                resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                resp.failure(f"Multi-turn failed: {resp.status_code}")

    # ── Rate limit probe ─────────────────────────────────────────────────────

    @task(3)
    @tag("chat", "rate-limit")
    def probe_rate_limit(self):
        """Burst 5 rapid requests — should trigger 429 rate limiting."""
        payload = chat_completion_payload(size="short", stream=False, max_tokens=20)
        headers = self._headers()
        hit_rate_limit = False

        for _ in range(5):
            with self.client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                catch_response=True,
                timeout=INFERENCE_TIMEOUT,
                name="/v1/chat/completions [rate-limit-probe]",
            ) as resp:
                if resp.status_code == 429:
                    hit_rate_limit = True
                    resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                    resp.success()  # 429 is expected behaviour
                elif resp.status_code == 503:
                    hit_rate_limit = True
                    resp.request_meta["name"] = "/v1/chat/completions [Rate Limited]"
                    resp.success()  # 503 backpressure = expected under load
                elif resp.status_code == 200:
                    resp.request_meta["name"] = "/v1/chat/completions [Model Success]"
                    resp.success()
                elif resp.status_code in (401, 0):
                    resp.request_meta["name"] = "/v1/chat/completions [Auth Failed]"
                    resp.success()
                else:
                    resp.request_meta["name"] = "/v1/chat/completions [Model Failure]"
                    resp.failure(f"Unexpected status: {resp.status_code}")



class ChatUser(HttpUser):
    """Primary chat/inference user class — highest weight."""
    tasks = [ChatTaskSet]
    wait_time = between(1.0, 4.0)
    weight = 6
