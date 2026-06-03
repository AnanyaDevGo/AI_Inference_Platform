import requests
import json
import subprocess
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://localhost:8443" # Target Nginx HTTPS directly

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
                    import re
                    match = re.search(r'\b\d{6}\b', body)
                    if match:
                        return match.group(0)
    except Exception:
        pass

    # Fallback to kubectl logs (for Console provider verification in K8s)
    cmd = "kubectl logs -n infervoyage-dev -l component=api --tail=150"
    logs = run_cmd(cmd)
    import re
    blocks = logs.split("========================================================================")
    for block in reversed(blocks):
        if f"To: {email}" in block or f"to: {email}" in block.lower():
            match = re.search(r'\b\d{6}\b', block)
            if match:
                return match.group(0)
    return None

def test_forgot_password():
    print("\n--- Testing Forgot Password Flow (JWT Token) ---")
    email = f"forgot_test_{int(time.time())}@example.com"
    password = "password123"
    new_password = "newpassword456"

    # Register
    print("Registering user...")
    r = requests.post(f"{API_URL}/auth/register", json={
        "name": "Forgot User",
        "email": email,
        "password": password
    }, verify=False)
    print("Register response:", r.status_code, r.text)
    assert r.status_code in [201, 400]

    # Forgot password request
    print("Sending forgot password request...")
    r = requests.post(f"{API_URL}/auth/forgot-password", json={"email": email}, verify=False)
    print("Forgot Password response:", r.status_code, r.text)
    assert r.status_code == 200
    res_data = r.json()
    reset_token = res_data.get("reset_token")
    print("Retrieved reset token from response:", reset_token)
    assert reset_token is not None, "Failed to retrieve reset token from response"

    # Get OTP code
    otp_code = get_otp_from_logs(email)
    print("Retrieved reset OTP code:", otp_code)
    assert otp_code is not None, "Failed to retrieve reset OTP code"

    # Verify OTP first
    print("Verifying reset OTP via /auth/verify-reset-otp...")
    r = requests.post(f"{API_URL}/auth/verify-reset-otp", json={
        "email": email,
        "code": otp_code,
        "verification_token": reset_token
    }, verify=False)
    print("Verify reset response:", r.status_code, r.text)
    assert r.status_code == 200

    # Reset password
    print("Resetting password...")
    r = requests.post(f"{API_URL}/auth/reset-password", json={
        "email": email,
        "reset_token": reset_token,
        "new_password": new_password
    }, verify=False)
    print("Reset response:", r.status_code, r.text)
    assert r.status_code == 200

    # Try login with new password
    print("Logging in with new password...")
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": email,
        "password": new_password
    }, verify=False)
    print("Login response:", r.status_code, r.text)
    assert r.status_code == 200
    token = r.json()["access_token"]
    print("Successfully logged in with new password!")
    return token


def test_google_registration_verification():
    print("\n--- Testing Google Registration Verification Flow (JWT Token) ---")
    email = f"google_test_{int(time.time())}@example.com"
    org_name = "Google Org"

    # 1. Start Google Register
    print("Initiating Google Sign-In registration...")
    r = requests.post(f"{API_URL}/auth/google", json={
        "id_token": f"google-id-{email}",
        "org_name": org_name
    }, verify=False)
    print("Google sign-in response:", r.status_code, r.text)
    assert r.status_code == 200
    res_data = r.json()
    assert res_data.get("requires_otp") is True
    verification_token = res_data.get("verification_token")
    print("Retrieved verification token from response:", verification_token)
    assert verification_token is not None, "Failed to retrieve verification token from response"

    # 2. Complete verification via token and code
    otp_code = get_otp_from_logs(email)
    print("Retrieved Google registration OTP code:", otp_code)
    assert otp_code is not None

    print("Completing verification via verification_token and code...")
    r = requests.post(f"{API_URL}/auth/verify-email-otp", json={
        "email": email,
        "verification_token": verification_token,
        "code": otp_code
    }, verify=False)
    print("Verify OTP response:", r.status_code, r.text)
    assert r.status_code == 200
    login_data = r.json()
    assert login_data.get("access_token") is not None
    print("Successfully registered and logged in Google user via JWT token and OTP!")

def test_message_truncation(token):
    print("\n--- Testing Message Truncation Endpoint ---")
    # 1. Create a conversation
    r = requests.post(f"{API_URL}/api/conversations", json={"title": "Truncate Chat"}, headers={
        "Authorization": f"Bearer {token}"
    }, verify=False)
    conv_id = r.json()["id"]
    print(f"Created conversation {conv_id}")

    # 2. Add messages
    msgs = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Response 2"},
    ]
    saved_msgs = []
    for m in msgs:
        r = requests.post(f"{API_URL}/api/conversations/{conv_id}/messages", json=m, headers={
            "Authorization": f"Bearer {token}"
        }, verify=False)
        saved_msgs.append(r.json())
        print(f"Saved message: {r.json()['role']} - {r.json()['id']} - position {r.json()['position']}")

    # 3. Get conversation and verify count is 4
    r = requests.get(f"{API_URL}/api/conversations/{conv_id}", headers={
        "Authorization": f"Bearer {token}"
    }, verify=False)
    print("Initial message count:", len(r.json()["messages"]))
    assert len(r.json()["messages"]) == 4

    # 4. Truncate from the second user message (position 2, ID is saved_msgs[2]['id'])
    target_msg_id = saved_msgs[2]["id"]
    print(f"Truncating from message {target_msg_id} (position 2)")
    r = requests.delete(f"{API_URL}/api/conversations/{conv_id}/messages/{target_msg_id}", headers={
        "Authorization": f"Bearer {token}"
    }, verify=False)
    print("Delete response status:", r.status_code)
    assert r.status_code == 204

    # 5. Get conversation and verify count is 2 (only first user and assistant messages remain)
    r = requests.get(f"{API_URL}/api/conversations/{conv_id}", headers={
        "Authorization": f"Bearer {token}"
    }, verify=False)
    remaining = r.json()["messages"]
    print("Remaining message count:", len(remaining))
    assert len(remaining) == 2
    for m in remaining:
        print(f"Remaining: {m['role']} - position {m['position']} - {m['content']}")
    
    print("Message truncation verified successfully!")

if __name__ == "__main__":
    try:
        test_google_registration_verification()
        token = test_forgot_password()
        test_message_truncation(token)
        print("\nAll integration tests passed successfully!")
    except AssertionError as e:
        print("\nTest failed:", e)
