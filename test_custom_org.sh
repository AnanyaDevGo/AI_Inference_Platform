#!/bin/bash
set -e

REG=$(curl -s -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Custom Org User","email":"custom@test.com","password":"password123","org_name":"ACME Corp"}')

echo "$REG" | python3 -m json.tool
TOKEN=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

echo "Decode JWT:"
python3 -c "
import json, base64
token='$TOKEN'
if not token:
    print('No token')
    exit()
payload=token.split('.')[1]
payload+='='*(-len(payload)%4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(payload)),indent=2))
"
