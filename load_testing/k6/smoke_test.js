/**
 * InferVoyage — k6 Smoke Test
 * Lightweight sanity check: verifies all critical endpoints respond correctly
 * before running full Locust load tests.
 *
 * Run: k6 run k6/smoke_test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

// ── Custom Metrics ────────────────────────────────────────────────────────────
const inferenceLatency = new Trend("inference_latency_ms");
const errorRate = new Rate("error_rate");

// ── Options ───────────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "30s", target: 5 },   // Ramp up
    { duration: "60s", target: 10 },  // Sustained load
    { duration: "15s", target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<3000", "p(99)<8000"],
    error_rate: ["rate<0.02"],
    inference_latency_ms: ["p(95)<3000"],
  },
};

const HOST = __ENV.HOST || "http://localhost:8000";
const EMAIL = __ENV.TEST_EMAIL || "loadtest@infervoyage.local";
const PASSWORD = __ENV.TEST_PASSWORD || "LoadTest@12345";
const MODEL = __ENV.MODEL || "llama3";

// ── Shared state ──────────────────────────────────────────────────────────────
let accessToken = null;

export function setup() {
  // Login once and share token across VUs
  const res = http.post(
    `${HOST}/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );

  if (res.status !== 200) {
    console.warn(`Login failed: ${res.status} — tests will run without auth`);
    return { token: null };
  }

  const body = JSON.parse(res.body);
  return { token: body.access_token };
}

export default function (data) {
  const token = data.token;
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  // ── 1. Health Check ────────────────────────────────────────────────────────
  {
    const res = http.get(`${HOST}/health`);
    check(res, {
      "health 200": (r) => r.status === 200,
    });
    errorRate.add(res.status !== 200);
  }

  sleep(0.2);

  // ── 2. Non-streaming Inference ─────────────────────────────────────────────
  if (token) {
    const start = Date.now();
    const res = http.post(
      `${HOST}/v1/chat/completions`,
      JSON.stringify({
        model: MODEL,
        messages: [{ role: "user", content: "What is 2+2?" }],
        stream: false,
        max_tokens: 50,
      }),
      { headers, timeout: "90s" }
    );
    const elapsed = Date.now() - start;

    const ok = res.status === 200 || res.status === 429;
    check(res, {
      "inference 200 or 429": () => ok,
      "inference has choices": (r) =>
        r.status !== 200 || JSON.parse(r.body).choices?.length > 0,
    });

    if (res.status === 200) {
      inferenceLatency.add(elapsed);
    }
    errorRate.add(!ok);
  }

  sleep(1);

  // ── 3. Auth Profile ────────────────────────────────────────────────────────
  if (token) {
    const res = http.get(`${HOST}/auth/me`, { headers });
    check(res, {
      "profile 200": (r) => r.status === 200,
      "profile has email": (r) =>
        r.status !== 200 || JSON.parse(r.body).email !== undefined,
    });
    errorRate.add(res.status !== 200);
  }

  sleep(0.5);

  // ── 4. Admin Usage (may 403 for non-admin) ────────────────────────────────
  if (token) {
    const res = http.get(`${HOST}/admin/usage/summary`, { headers });
    check(res, {
      "usage endpoint reachable": (r) => [200, 403].includes(r.status),
    });
  }

  sleep(1);
}

export function handleSummary(data) {
  return {
    "reports/k6_smoke_report.json": JSON.stringify(data, null, 2),
  };
}
