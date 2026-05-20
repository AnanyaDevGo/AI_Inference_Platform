#!/bin/bash
set -e
echo "=== Container status ==="
docker-compose ps
echo ""
echo "=== Health via Nginx (port 80) ==="
curl -s http://localhost/health | python3 -m json.tool
echo ""
echo "=== Register user ==="
REG=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo User","email":"demo@example.com","password":"password123"}')
echo "$REG" | python3 -m json.tool
echo ""
echo "=== Login ==="
LOGIN=$(curl -s -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"password123"}')
echo "$LOGIN" | python3 -m json.tool
echo ""
echo "=== Frontend HTML check ==="
curl -s http://localhost/ | head -5
