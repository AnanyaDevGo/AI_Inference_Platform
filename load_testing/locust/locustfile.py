"""
InferVoyage Load Testing — Main Locust Entry Point

Usage:
  # Interactive UI
  locust -f locustfile.py --host http://localhost:8000

  # Headless CI mode
  locust -f locustfile.py --host http://localhost:8000 \
    --headless --users 50 --spawn-rate 5 \
    --run-time 5m --html reports/report.html \
    --csv reports/stats

  # Distributed (master)
  locust -f locustfile.py --master --host http://localhost:8000

  # Distributed (worker — run on separate nodes)
  locust -f locustfile.py --worker --master-host <master-ip>

  # Run only tagged scenarios
  locust -f locustfile.py --tags streaming ttft

User Weight Distribution (out of 16 total weight):
  ChatUser          6 / 16 = 37.5%   Primary AI inference load
  InferenceUser     4 / 16 = 25.0%   Ollama-specific benchmarking
  MultiTenantUser   3 / 16 = 18.75%  Tenant isolation validation
  AuthUser          2 / 16 = 12.5%   Auth endpoint load
  AdminUser         1 / 16 = 6.25%   Admin API read load
"""
from __future__ import annotations

import time
import statistics
from locust import events

# Import all user classes — Locust discovers them automatically
from scenarios.auth_tasks import AuthUser
from scenarios.chat_tasks import ChatUser
from scenarios.inference_tasks import InferenceUser, get_latency_percentiles
from scenarios.multi_tenant_tasks import MultiTenantUser
from scenarios.admin_tasks import AdminUser

__all__ = ["AuthUser", "ChatUser", "InferenceUser", "MultiTenantUser", "AdminUser"]


# ── Custom Event Hooks ────────────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  InferVoyage Load Test Starting")
    print(f"  Target: {environment.host}")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print percentile summary and autoscaling recommendations on test end."""
    print("\n" + "=" * 60)
    print("  LOAD TEST COMPLETE — PERFORMANCE SUMMARY")
    print("=" * 60)

    stats = environment.stats
    total = stats.total

    if total.num_requests > 0:
        print(f"\n  Total Requests  : {total.num_requests:,}")
        print(f"  Failures        : {total.num_failures:,} ({total.fail_ratio * 100:.2f}%)")
        print(f"  RPS (avg)       : {total.total_rps:.2f}")
        print(f"  Median RT       : {total.median_response_time:.0f} ms")
        print(f"  P95 RT          : {total.get_response_time_percentile(0.95):.0f} ms")
        print(f"  P99 RT          : {total.get_response_time_percentile(0.99):.0f} ms")
        print(f"  Max RT          : {total.max_response_time:.0f} ms")

    # Inference-specific percentiles from our custom tracker
    percs = get_latency_percentiles()
    if percs:
        print(f"\n  --- Inference Latency (custom tracker) ---")
        print(f"  P50 : {percs.get('p50', 0):.0f} ms")
        print(f"  P90 : {percs.get('p90', 0):.0f} ms")
        print(f"  P95 : {percs.get('p95', 0):.0f} ms")
        print(f"  P99 : {percs.get('p99', 0):.0f} ms")
        print(f"  N   : {percs.get('count', 0)} samples")

    # ── Autoscaling Recommendations ──────────────────────────────────────────
    print("\n  --- AUTOSCALING RECOMMENDATIONS ---")

    p95 = total.get_response_time_percentile(0.95) if total.num_requests > 0 else 0
    fail_rate = total.fail_ratio if total.num_requests > 0 else 0
    rps = total.total_rps if total.num_requests > 0 else 0

    if p95 > 5000:
        print("  ⚠  P95 > 5s: Ollama is severely overloaded.")
        print("     → Reduce concurrent users OR add a second Ollama instance")
        print("     → Consider request queuing with a task queue (Celery/ARQ)")
    elif p95 > 3000:
        print("  ⚠  P95 > 3s: Inference latency is elevated.")
        print("     → Reduce max_tokens per request, or use a smaller model")
        print("     → Consider llama3:8b quantized (Q4) for faster inference")
    else:
        print("  ✓  P95 latency is within acceptable range")

    if fail_rate > 0.05:
        print(f"  ✗  Error rate {fail_rate*100:.1f}% exceeds 5% threshold.")
        print("     → Check rate limit configuration (current org RPM)")
        print("     → Check PostgreSQL connection pool exhaustion")
        print("     → Check Redis memory limit")
    elif fail_rate > 0.02:
        print(f"  ⚠  Error rate {fail_rate*100:.1f}% is above 2% warning threshold")
    else:
        print(f"  ✓  Error rate {fail_rate*100:.2f}% is acceptable")

    if rps > 0:
        if rps < 5:
            print(f"  ⚠  RPS {rps:.1f} is low — consider increasing workers or reducing think time")
        else:
            print(f"  ✓  Achieved {rps:.1f} RPS sustained throughput")

    print("\n  Full HTML report: reports/report.html")
    print("=" * 60 + "\n")
