#!/bin/bash
set -e

echo "════════════════════════════════════════════════════"
echo "  Phase 2 Verification Tests"
echo "════════════════════════════════════════════════════"

echo ""
echo "=== 1. Health check ==="
curl -s http://localhost/health | python3 -m json.tool

echo ""
echo "=== 2. Unauthenticated inference → should be 401 ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma2:2b-instruct-q4_K_M","messages":[{"role":"user","content":"hi"}]}')
echo "HTTP Status: $STATUS (expected: 401)"

echo ""
echo "=== 3. Register first user (becomes platform_admin) ==="
REG1=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin User","email":"admin@platform.com","password":"password123"}')
echo "$REG1" | python3 -m json.tool
TOKEN1=$(echo "$REG1" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "=== 4. Decode JWT to verify org_id and role ==="
echo "$TOKEN1" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (-len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print(json.dumps(data, indent=2))
"

echo ""
echo "=== 5. Authenticated inference → should work ==="
STATUS2=$(curl -s -o /dev/null -w "%{http_code}" -N -X POST http://localhost/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN1" \
  -d '{"model":"gemma2:2b-instruct-q4_K_M","messages":[{"role":"user","content":"say hi"}],"stream":false,"max_tokens":5}')
echo "HTTP Status: $STATUS2 (expected: 200)"

echo ""
echo "=== 6. List orgs (admin only) ==="
curl -s http://localhost/admin/orgs -H "Authorization: Bearer $TOKEN1" | python3 -m json.tool

echo ""
echo "=== 7. Register second user (becomes org_admin) ==="
REG2=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Regular User","email":"user@platform.com","password":"password123"}')
TOKEN2=$(echo "$REG2" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Decode token 2:"
echo "$TOKEN2" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (-len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print(json.dumps(data, indent=2))
"

echo ""
echo "=== 8. Regular user tries to list orgs → should be 403 ==="
STATUS3=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/admin/orgs \
  -H "Authorization: Bearer $TOKEN2")
echo "HTTP Status: $STATUS3 (expected: 403)"

echo ""
echo "=== 9. Create API key (admin) ==="
APIKEY=$(curl -s -X POST http://localhost/admin/api-keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN1" \
  -d '{"name":"Test Key"}')
echo "$APIKEY" | python3 -m json.tool
PLAINTEXT=$(echo "$APIKEY" | python3 -c "import sys,json; print(json.load(sys.stdin)['plaintext_key'])")

echo ""
echo "=== 10. Use API key for inference ==="
STATUS4=$(curl -s -o /dev/null -w "%{http_code}" -N -X POST http://localhost/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PLAINTEXT" \
  -d '{"model":"gemma2:2b-instruct-q4_K_M","messages":[{"role":"user","content":"say hello"}],"stream":false,"max_tokens":5}')
echo "HTTP Status: $STATUS4 (expected: 200)"

echo ""
echo "=== 11. Cross-user conversation isolation ==="
echo "User 1 conversations:"
curl -s http://localhost/api/conversations -H "Authorization: Bearer $TOKEN1" | python3 -m json.tool
echo "User 2 conversations:"
curl -s http://localhost/api/conversations -H "Authorization: Bearer $TOKEN2" | python3 -m json.tool

echo ""
echo "════════════════════════════════════════════════════"
echo "  All tests completed!"
echo "════════════════════════════════════════════════════"
