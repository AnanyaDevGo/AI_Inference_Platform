import requests

base_url = "http://localhost"
r = requests.post(f"{base_url}/auth/register", json={
    "name": "Super Admin 3",
    "email": "super3@test.com",
    "password": "password123"
})
print("Register:", r.status_code, r.text)

if r.status_code == 201 or r.status_code == 200:
    token = r.json().get("access_token")
    r2 = requests.post(f"{base_url}/admin/api-keys", json={
        "name": "Test Key"
    }, headers={"Authorization": f"Bearer {token}"})
    print("Create API Key:", r2.status_code, r2.text)
