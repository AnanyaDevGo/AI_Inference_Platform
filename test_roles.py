import requests
import json
import base64

def get_role(token):
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))['role']
    except Exception as e:
        return str(e)

base_url = "http://localhost/auth/register"

r1 = requests.post(base_url, json={"name":"Admin","email":"admin1@test.com","password":"password123"})
print("1st User:", get_role(r1.json().get('access_token', '')))

r2 = requests.post(base_url, json={"name":"CEO","email":"ceo@stark.com","password":"password123","org_name":"Stark Ind"})
print("2nd User (New Org):", get_role(r2.json().get('access_token', '')))

r3 = requests.post(base_url, json={"name":"Emp","email":"emp@stark.com","password":"password123","org_name":"Stark Ind"})
print("3rd User (Existing Org):", get_role(r3.json().get('access_token', '')))
