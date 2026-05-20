import requests
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://localhost"

def test_auth_flow():
    print("\n=== STARTING NEW AUTH FLOW TESTS ===")
    
    # 1. Test Google Signup creates unverified user
    email = f"google_flow_{int(time.time())}@example.com"
    print(f"1. Initiating Google Sign-In registration for {email}...")
    r = requests.post(f"{API_URL}/auth/google", json={
        "id_token": f"google-id-{email}"
    }, verify=False)
    assert r.status_code == 200
    res = r.json()
    assert res["requires_otp"] is True
    verification_token = res["verification_token"]
    print("Google sign-in successfully returned requires_otp=True and verification_token.")

    # 2. Test verify-otp sets is_verified=True and returns active tokens
    print("2. Verifying OTP via JWT verification token...")
    r = requests.post(f"{API_URL}/auth/verify-otp", json={
        "email": email,
        "verification_token": verification_token
    }, verify=False)
    assert r.status_code == 200
    res = r.json()
    access_token = res["access_token"]
    assert access_token is not None
    print("OTP successfully verified. Tokens issued.")

    # 3. Test setup-password endpoint allows setting password for Google user
    print("3. Setting password via /auth/setup-password...")
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(f"{API_URL}/auth/setup-password", json={
        "password": "mysecretpassword123"
    }, headers=headers, verify=False)
    assert r.status_code == 200
    print("Password successfully setup for Google user account.")

    # 4. Test login using newly setup password (standard email + password login)
    print("4. Testing email + password login with the set password...")
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": email,
        "password": "mysecretpassword123"
    }, verify=False)
    assert r.status_code == 200
    res = r.json()
    assert res["access_token"] is not None
    print("Successfully logged in with email + password!")

    # 5. Test forgot-password secure response (doesn't leak account existence)
    print("5. Testing forgot-password secure response for non-existent email...")
    fake_email = "non_existent_user_12345@example.com"
    r = requests.post(f"{API_URL}/auth/forgot-password", json={
        "email": fake_email
    }, verify=False)
    assert r.status_code == 200
    res = r.json()
    assert res["success"] is True
    assert "If an account exists" in res["message"]
    print("Forgot password for fake email returned generic success message.")

    print("5b. Testing forgot-password secure response for existing email...")
    r = requests.post(f"{API_URL}/auth/forgot-password", json={
        "email": email
    }, verify=False)
    assert r.status_code == 200
    res = r.json()
    assert res["success"] is True
    assert "If an account exists" in res["message"]
    print("Forgot password for real email also returned identical generic success message.")

    print("\n=== ALL NEW AUTH FLOW TESTS PASSED! ===")

if __name__ == "__main__":
    test_auth_flow()
