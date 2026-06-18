import requests
import time
import urllib3
import re
import subprocess

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://localhost:8443"

def run_cmd(cmd):
    # Try running directly first (for WSL/Linux environments)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        return res.stdout
    # Try with WSL wrapper (for Windows host environments)
    wsl_cmd = f'wsl -u root bash -c "{cmd.replace(chr(34), chr(92)+chr(34))}"'
    res = subprocess.run(wsl_cmd, shell=True, capture_output=True, text=True)
    return res.stdout

def get_otp_from_logs(email):
    # Try fetching from Mailpit REST API first (for local SMTP verification)
    try:
        r = requests.get("http://localhost:8025/api/v1/messages", timeout=2)
        if r.status_code == 200:
            data = r.json()
            for msg in data.get("messages", []):
                to_addresses = [t.get("Address") for t in msg.get("To", []) if t.get("Address")]
                if any(email.lower() == addr.lower() for addr in to_addresses):
                    msg_id = msg.get("ID")
                    msg_detail = requests.get(f"http://localhost:8025/api/v1/message/{msg_id}").json()
                    body = msg_detail.get("Text", "") + msg_detail.get("HTML", "")
                    match = re.search(r'\b\d{6}\b', body)
                    if match:
                        return match.group(0)
    except Exception:
        pass

    # Fallback to kubectl logs (for Console provider verification in K8s)
    cmd = "kubectl logs -n infervoyage-dev -l component=api --tail=1000"
    logs = run_cmd(cmd)
    blocks = logs.split("========================================================================")
    for block in reversed(blocks):
        if f"To: {email}" in block or f"to: {email}" in block.lower():
            match = re.search(r'\b\d{6}\b', block)
            if match:
                return match.group(0)
    return None

def run_postgres_sql(sql):
    cmd = f'kubectl exec -i -n infervoyage-dev infervoyage-dev-postgres-0 -- psql -U appuser -d inference_platform -c "{sql}"'
    return run_cmd(cmd)

def promote_user_to_role(email, role):
    sql = f"UPDATE users SET role = '{role}' WHERE email = '{email}';"
    res = run_postgres_sql(sql)
    print(f"Promote response: {res.strip()}")

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

    # 2. Test verify-email-otp sets is_verified=True and returns active tokens
    print("2. Fetching Google registration OTP from logs...")
    otp_code = get_otp_from_logs(email)
    print(f"Retrieved Google registration OTP code: {otp_code}")
    assert otp_code is not None

    print("2b. Verifying Google registration OTP via JWT verification token...")
    r = requests.post(f"{API_URL}/auth/verify-email-otp", json={
        "email": email,
        "verification_token": verification_token,
        "code": otp_code
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
    reset_token = res.get("reset_token")
    assert reset_token is not None
    print("Forgot password for real email also returned identical generic success message with reset_token.")

    # 5c. Test rate-limiting (Max 3 OTP requests / resends within 15 minutes)
    print("\n--- 5c. Testing OTP Resend Rate Limiting (Max 3 in 15 mins) ---")
    rate_email = f"rate_limit_{int(time.time())}@example.com"
    # Register rate_email (active immediately)
    r = requests.post(f"{API_URL}/auth/register", json={
        "name": "Rate User",
        "email": rate_email,
        "password": "ratepassword123"
    }, verify=False)
    assert r.status_code == 201

    # Request 1 (triggered by registration/forgot-password)
    r = requests.post(f"{API_URL}/auth/forgot-password", json={"email": rate_email}, verify=False)
    assert r.status_code == 200
    # Request 2
    r = requests.post(f"{API_URL}/auth/forgot-password", json={"email": rate_email}, verify=False)
    assert r.status_code == 200
    # Request 3
    r = requests.post(f"{API_URL}/auth/forgot-password", json={"email": rate_email}, verify=False)
    assert r.status_code == 200
    # Request 4 (should be rate-limited)
    r = requests.post(f"{API_URL}/auth/forgot-password", json={"email": rate_email}, verify=False)
    assert r.status_code == 400
    assert "Too many requests" in r.text
    print("Rate limit check passed: 4th request was blocked with 400.")

    # 5d. Test verification lockout (Max 5 attempts)
    print("\n--- 5d. Testing OTP Lockout (Max 5 failed attempts) ---")
    # Get latest OTP for rate_email
    rate_otp = get_otp_from_logs(rate_email)
    assert rate_otp is not None
    print(f"Retrieved rate user reset OTP code: {rate_otp}")

    # Reset token from 3rd request response
    rate_reset_token = r.json().get("reset_token") # Wait, 4th request returned 400, let's request token from the 3rd request:
    # Actually we don't even need the reset token if we verify wrong codes
    # Try 5 failed attempts
    for attempt in range(1, 6):
        r = requests.post(f"{API_URL}/auth/verify-reset-otp", json={
            "email": rate_email,
            "code": "000000" # wrong code
        }, verify=False)
        assert r.status_code == 400
        print(f"Failed attempt {attempt} response: {r.text.strip()}")
        if attempt == 5:
            assert "Maximum verification attempts exceeded" in r.text

    # 6th attempt (even with correct code, it should be locked out)
    r = requests.post(f"{API_URL}/auth/verify-reset-otp", json={
        "email": rate_email,
        "code": rate_otp
    }, verify=False)
    assert r.status_code == 400
    assert "Maximum verification attempts exceeded" in r.text
    print("Lockout check passed: 6th attempt with correct code was blocked due to lockout.")

    # 6. Test OTP verification requirement on password reset
    print("\n--- 6. Testing password reset flow using separate verification endpoint ---")
    otp_code = get_otp_from_logs(email)
    print(f"Retrieved reset OTP code: {otp_code}")
    assert otp_code is not None

    # Call verify-reset-otp first
    print("6a. Verifying reset OTP via /auth/verify-reset-otp...")
    r = requests.post(f"{API_URL}/auth/verify-reset-otp", json={
        "email": email,
        "code": otp_code,
        "verification_token": reset_token
    }, verify=False)
    assert r.status_code == 200
    print("Reset OTP successfully verified.")

    # Reset password passing reset_token (no code needed or can be passed)
    print("6b. Executing password reset via /auth/reset-password...")
    r = requests.post(f"{API_URL}/auth/reset-password", json={
        "email": email,
        "reset_token": reset_token,
        "new_password": "brandnewpassword999"
    }, verify=False)
    assert r.status_code == 200
    print("Password reset successfully completed.")

    # Test login with the brand new password
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": email,
        "password": "brandnewpassword999"
    }, verify=False)
    assert r.status_code == 200
    print("Successfully logged in with the new password.")

    # 7. Test Admin User & Organization Cascading Deletion
    print("\n=== STARTING CASCADING DELETION TESTS ===")
    
    # 7a. Register admin user
    admin_email = f"platform_admin_{int(time.time())}@example.com"
    print(f"Registering admin: {admin_email}...")
    r = requests.post(f"{API_URL}/auth/register", json={
        "name": "Super Admin Test",
        "email": admin_email,
        "password": "adminpassword123"
    }, verify=False)
    assert r.status_code == 201
    
    promote_user_to_role(admin_email, 'platform_admin')
    
    # Login admin to get auth headers
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": admin_email,
        "password": "adminpassword123"
    }, verify=False)
    assert r.status_code == 200
    admin_token = r.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 7b. Create a new organization and target user to delete
    target_org_slug = f"target-org-{int(time.time())}"
    print(f"Creating organization {target_org_slug}...")
    r = requests.post(f"{API_URL}/admin/orgs", json={
        "name": f"Target Org {int(time.time())}",
        "slug": target_org_slug
    }, headers=admin_headers, verify=False)
    assert r.status_code == 201
    org_id = r.json()["id"]
    
    # Register target user inside the new organization
    target_user_email = f"target_user_{int(time.time())}@example.com"
    print(f"Registering target user {target_user_email} inside organization...")
    r = requests.post(f"{API_URL}/auth/register", json={
        "name": "Target User",
        "email": target_user_email,
        "password": "targetpassword123",
        "org_name": f"Target Org {int(time.time())}" # This matches name and links to org
    }, verify=False)
    assert r.status_code == 201
    
    promote_user_to_role(target_user_email, 'org_admin')

    # Login target user to get the elevated access token (with org_admin claim)
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": target_user_email,
        "password": "targetpassword123"
    }, verify=False)
    assert r.status_code == 200
    target_token = r.json()["access_token"]
    
    # Fetch target user ID
    r = requests.get(f"{API_URL}/auth/me", headers={"Authorization": f"Bearer {target_token}"}, verify=False)
    assert r.status_code == 200
    target_user_id = r.json()["id"]
    
    # Target user creates an API key (creating ApiKey dependency)
    print("Target user creating an API key...")
    r = requests.post(f"{API_URL}/admin/api-keys", json={
        "name": "Target Key"
    }, headers={"Authorization": f"Bearer {target_token}"}, verify=False)
    assert r.status_code == 201
    
    # Target user creates a conversation (creating Conversation dependency)
    print("Target user creating a conversation...")
    r = requests.post(f"{API_URL}/api/conversations", json={
        "title": "Target Chat"
    }, headers={"Authorization": f"Bearer {target_token}"}, verify=False)
    assert r.status_code == 201
    
    # 7c. Test Deleting User (cascading deletes key, nullifies usage log, deletes conversation)
    print(f"Deleting user {target_user_email} as platform admin...")
    r = requests.delete(f"{API_URL}/admin/users/{target_user_id}", headers=admin_headers, verify=False)
    assert r.status_code == 204
    print("User successfully deleted without foreign key violations!")
    
    # 7d. Test Deleting Org (cascading deletes org, users, keys, and logs)
    print(f"Deleting organization {target_org_slug} as platform admin...")
    r = requests.delete(f"{API_URL}/admin/orgs/{org_id}", headers=admin_headers, verify=False)
    assert r.status_code == 204
    print("Organization successfully deleted without foreign key violations!")
    
    print("\n=== ALL NEW AUTH & DELETION FLOW TESTS PASSED! ===")

if __name__ == "__main__":
    test_auth_flow()
