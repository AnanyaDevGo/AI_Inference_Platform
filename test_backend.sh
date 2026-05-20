#!/bin/bash
set -e
echo "=== Container status ==="
docker-compose ps
echo ""
echo "=== Health check via Nginx ==="
curl -s http://localhost/health | python3 -m json.tool
echo ""
echo "=== Register test user ==="
curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@example.com","password":"password123"}' | python3 -m json.tool
