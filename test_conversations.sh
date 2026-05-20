#!/bin/bash
set -e

echo "=== Health check ==="
curl -s http://localhost/health | python3 -m json.tool

echo ""
echo "=== Register fresh user ==="
REG=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice Test","email":"alice@test.com","password":"password123"}')
echo "$REG" | python3 -m json.tool
TOKEN=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "=== List conversations (should be empty) ==="
curl -s http://localhost/api/conversations \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Create a conversation ==="
CONV=$(curl -s -X POST http://localhost/api/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Test Chat"}')
echo "$CONV" | python3 -m json.tool
CONV_ID=$(echo "$CONV" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo ""
echo "=== Save a user message ==="
curl -s -X POST "http://localhost/api/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"role":"user","content":"Hello world"}' | python3 -m json.tool

echo ""
echo "=== Get conversation with messages ==="
curl -s "http://localhost/api/conversations/$CONV_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Verify with different user ==="
REG2=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Bob Test","email":"bob@test.com","password":"password123"}')
TOKEN2=$(echo "$REG2" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Bob's conversations (should be empty):"
curl -s http://localhost/api/conversations \
  -H "Authorization: Bearer $TOKEN2" | python3 -m json.tool
