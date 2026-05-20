#!/bin/bash
set -e

BASE_URL="http://localhost:8000"
MODEL="gemma2:2b-instruct-q4_K_M"

echo "=== Health Check ==="
curl -s "$BASE_URL/health" | python3 -m json.tool

echo ""
echo "=== Non-Streaming Inference (gemma2) ==="
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL"'",
    "messages": [{"role": "user", "content": "Say hello in exactly one sentence."}],
    "stream": false,
    "max_tokens": 64
  }' | python3 -m json.tool

echo ""
echo "=== Streaming Inference (gemma2) ==="
curl -s -N -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$MODEL"'",
    "messages": [{"role": "user", "content": "Count from 1 to 5."}],
    "stream": true,
    "max_tokens": 64
  }'

echo ""
echo ""
echo "=== Metrics (sample) ==="
curl -s "$BASE_URL/metrics" | grep "inference_" | head -10
