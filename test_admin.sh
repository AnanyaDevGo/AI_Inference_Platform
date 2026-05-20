#!/bin/bash
set -e

echo "=== Health check ==="
curl -s http://localhost/health | python3 -m json.tool

echo ""
echo "=== Register admin user ==="
REG=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Admin Test","email":"admin3@test.com","password":"password123"}')
echo "$REG" | python3 -m json.tool
TOKEN=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "=== Decode JWT ==="
python3 -c "
import json, base64
token='$TOKEN'
payload=token.split('.')[1]
payload+='='*(-len(payload)%4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(payload)),indent=2))
"

echo ""
echo "=== Admin: List orgs ==="
curl -s http://localhost/admin/orgs -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Admin: List users ==="
curl -s http://localhost/admin/users -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Admin: Create API key ==="
KEY=$(curl -s -X POST http://localhost/admin/api-keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Production Key"}')
echo "$KEY" | python3 -m json.tool

echo ""
echo "=== Admin: List API keys ==="
curl -s http://localhost/admin/api-keys -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Frontend serves SPA HTML ==="
curl -s http://localhost/ | head -3

echo ""
echo "=== ALL ADMIN API WORKING ==="
