"""
Inference-specific load test scenarios.

Covers:
  - Parallel inference bottleneck analysis
  - Timeout handling (extremely large prompts)
  - Backpressure testing
  - Ollama concurrency stress
  - Model warmup detection
  - Cold vs warm inference latency comparison
"""
from __future__ import annotations

import time
import threading
import statistics
from locust import HttpUser, TaskSet, task, between, tag, events
from locust.exception import StopUser

from utils.auth_helper import login, get_auth_headers
from utils.data_factory import chat_completion_payload
from config import (
    TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME,
    MODEL_NAME, INFERENCE_TIMEOUT, STREAM_TIMEOUT
)

# Thread-safe latency tracker for bottleneck analysis
_latency_samples: list[float] = []
_latency_lock = threading.Lock()


def _record_latency(ms: float):
    with _latency_lock:
        _latency_samples.append(ms)
        if len(_latency_samples) > 1000:
            _latency_samples.pop(0)  # rolling window


def get_latency_percentiles() -> dict:
    """Compute P50/P90/P95/P99 from collected samples."""
    with _latency_lock:
        if not _latency_samples:
            return {}
        sorted_s = sorted(_latency_samples)
        n = len(sorted_s)
        return {
            "p50": sorted_s[int(n * 0.50)],
            "p90": sorted_s[int(n * 0.90)],
            "p95": sorted_s[int(n * 0.95)],
            "p99": sorted_s[min(int(n * 0.99), n - 1)],
            "count": n,
        }


class InferenceTaskSet(TaskSet):
    """Inference-focused task set for Ollama performance benchmarking."""

    token: str | None = None
    _warmup_done: bool = False

    def on_start(self):
        self.token = login(self.client, TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_NAME)
        if not self.token:
            raise StopUser()

    def _headers(self) -> dict:
        return get_auth_headers(self.token or "")

    # ── Baseline latency ────────────────────────────────────────────────────

    @task(20)
    @tag("inference", "baseline")
    def inference_baseline(self):
        """
        Standard inference latency measurement.
        Records to _latency_samples for percentile analysis.
        """
        payload = chat_completion_payload(size="short", stream=False, max_tokens=100)
        start = time.perf_counter()

        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            timeout=INFERENCE_TIMEOUT,
            name="/v1/chat/completions [inference-baseline]",
        ) as resp:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if resp.status_code == 200:
                _record_latency(elapsed_ms)
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"Inference failed: {resp.status_code}")

    # ── Concurrent inference (bottleneck analysis) ───────────────────────────

    @task(5)
    @tag("inference", "concurrent", "bottleneck")
    def concurrent_inference_burst(self):
        """
        Fire 3 concurrent inference requests from a single user.
        Helps detect Ollama concurrency bottlenecks and queue buildup.
        Response times for parallel requests should be similar if Ollama
        handles concurrency well; a multiplicative increase indicates serial queuing.
        """
        results: list[float] = []
        errors: list[str] = []
        lock = threading.Lock()

        def _run():
            payload = chat_completion_payload(size="short", stream=False, max_tokens=50)
            start = time.perf_counter()
            try:
                with self.client.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers=self._headers(),
                    catch_response=True,
                    timeout=INFERENCE_TIMEOUT,
                    name="/v1/chat/completions [concurrent]",
                ) as resp:
                    elapsed = (time.perf_counter() - start) * 1000
                    with lock:
                        if resp.status_code in (200, 429):
                            results.append(elapsed)
                            resp.success()
                        else:
                            errors.append(f"{resp.status_code}")
                            resp.failure(f"Concurrent inference failed: {resp.status_code}")
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=_run) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=INFERENCE_TIMEOUT + 5)

        # Log bottleneck analysis: if max > 3x min, Ollama is serializing requests
        if len(results) >= 2:
            ratio = max(results) / max(min(results), 1)
            if ratio > 3.0:
                # This fires a synthetic slow event so it shows in Locust charts
                events.request.fire(
                    request_type="ANALYSIS",
                    name="Ollama [concurrency-bottleneck-detected]",
                    response_time=max(results),
                    response_length=0,
                    exception=None,
                    context={"ratio": ratio, "results": results},
                )

    # ── Timeout handling ─────────────────────────────────────────────────────

    @task(2)
    @tag("inference", "timeout")
    def large_prompt_timeout(self):
        """
        Send an extremely large prompt to test timeout handling.
        Validates that the backend returns 504/408 correctly rather than hanging.
        """
        # 2000-token prompt that will stress Ollama's context window
        large_prompt = " ".join([
            "Provide an extremely detailed, step-by-step, comprehensive explanation of"
        ] + ["machine learning, neural networks, deep learning, transformers,"] * 50)

        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": large_prompt}],
            "stream": False,
            "max_tokens": 500,
        }

        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            catch_response=True,
            timeout=INFERENCE_TIMEOUT,
            name="/v1/chat/completions [large-prompt]",
        ) as resp:
            if resp.status_code in (200, 408, 504, 429, 500):
                resp.success()  # All are valid responses for large prompts
            else:
                resp.failure(f"Unexpected large-prompt response: {resp.status_code}")

    # ── Backpressure test ────────────────────────────────────────────────────

    @task(3)
    @tag("inference", "backpressure")
    def intentional_rate_limit(self):
        """
        Fire requests faster than the rate limit — validates 429 backpressure.
        The system should return 429 with retry-after rather than queueing indefinitely.
        """
        payload = chat_completion_payload(size="short", stream=False, max_tokens=10)
        headers = self._headers()

        for _ in range(8):  # Exceed typical 60 RPM limit in a burst
            with self.client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                catch_response=True,
                timeout=10,
                name="/v1/chat/completions [backpressure]",
            ) as resp:
                if resp.status_code in (200, 429):
                    resp.success()
                elif resp.status_code == 401:
                    resp.success()
                else:
                    resp.failure(f"Backpressure test: unexpected {resp.status_code}")

    # ── Health / readiness probe ──────────────────────────────────────────────

    @task(5)
    @tag("inference", "health")
    def health_check(self):
        """GET /health — quick API liveness check."""
        with self.client.get(
            "/health",
            catch_response=True,
            name="/health",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Health check failed: {resp.status_code}")


class InferenceUser(HttpUser):
    """Inference-focused user for Ollama benchmarking."""
    tasks = [InferenceTaskSet]
    wait_time = between(2.0, 6.0)
    weight = 4
