from __future__ import annotations

import abc
import asyncio
import os
import smtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx

logger = structlog.get_logger(__name__)


class BaseEmailProvider(abc.ABC):
    """Abstract Base Class for all Email Providers."""

    @abc.abstractmethod
    async def send_email(self, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        """Asynchronously send an email with optional HTML body and retry logic."""
        pass


class ConsoleEmailProvider(BaseEmailProvider):
    """Fallback Developer Provider: Logs emails to the Docker console."""

    async def send_email(self, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        logger.info("email_console_dispatch_triggered", to=to_email, subject=subject)
        email_block = f"""
========================================================================
                      🔒 AI PLATFORM SECURITY OTP (CONSOLE)
========================================================================
To: {to_email}
Subject: {subject}

{body_text}
========================================================================
"""
        print(email_block)


class SmtpEmailProvider(BaseEmailProvider):
    """Standard Production Provider: Connects to secure SMTP servers (supports SSL/TLS)."""

    def __init__(self, host: str, port: int, user: str | None = None, password: str | None = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    async def send_email(self, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        from email.utils import make_msgid, formatdate
        msg = MIMEMultipart("alternative")
        msg["From"] = self.user or "noreply@platform.com"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.user.split('@')[-1] if (self.user and '@' in self.user) else "infervoyage.com")
        msg["Date"] = formatdate(localtime=True)

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        def _send():
            # Port 465 requires SMTP_SSL right away
            if self.port == 465:
                server_class = smtplib.SMTP_SSL
            else:
                server_class = smtplib.SMTP

            with server_class(self.host, self.port, timeout=10) as server:
                if self.port != 465 and self.user and self.password:
                    server.starttls()
                
                if self.user and self.password:
                    server.login(self.user, self.password)
                
                server.send_message(msg)

        # Retry with exponential backoff (up to 3 times)
        max_retries = 3
        backoff = 2
        for attempt in range(max_retries):
            try:
                await asyncio.to_thread(_send)
                logger.info("smtp_email_dispatched_successfully", to=to_email)
                return
            except Exception as e:
                logger.warning(
                    "smtp_email_dispatch_attempt_failed",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt == max_retries - 1:
                    logger.error("smtp_email_dispatch_failed_permanently", to=to_email)
                    raise e
                await asyncio.sleep(backoff ** attempt)


class ResendEmailProvider(BaseEmailProvider):
    """Preferred Premium Provider: Dispatches emails using the Resend HTTP REST API."""

    def __init__(self, api_key: str, sender: str = "onboarding@resend.dev"):
        self.api_key = api_key
        self.sender = sender
        self.api_url = "https://api.resend.com/emails"

    async def send_email(self, to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        payload = {
            "from": self.sender,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            payload["html"] = body_html

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Retry with exponential backoff (up to 3 times)
        max_retries = 3
        backoff = 2
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(max_retries):
                try:
                    res = await client.post(self.api_url, json=payload, headers=headers)
                    if res.status_code in (200, 201):
                        logger.info("resend_email_dispatched_successfully", to=to_email)
                        return
                    else:
                        logger.warning(
                            "resend_api_responded_with_error",
                            status_code=res.status_code,
                            response=res.text,
                        )
                except Exception as e:
                    logger.warning(
                        "resend_email_dispatch_attempt_failed",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                
                if attempt == max_retries - 1:
                    logger.error("resend_email_dispatch_failed_permanently", to=to_email)
                    raise RuntimeError("Resend email dispatch failed after all retries")
                await asyncio.sleep(backoff ** attempt)


# ── Provider Registry and Factory ──────────────────────────────────────────
def get_email_provider() -> BaseEmailProvider:
    """Factory to retrieve the active email provider based on current environment variables."""
    from app.config import get_settings
    settings = get_settings()

    # 1. Check for Resend API Config
    if settings.RESEND_API_KEY:
        logger.info("email_service_provider_selected", type="resend", sender=settings.RESEND_SENDER)
        return ResendEmailProvider(api_key=settings.RESEND_API_KEY, sender=settings.RESEND_SENDER)

    # 2. Check for standard SMTP Config
    if settings.SMTP_HOST and settings.SMTP_PORT:
        logger.info("email_service_provider_selected", type="smtp", host=settings.SMTP_HOST, port=settings.SMTP_PORT)
        return SmtpEmailProvider(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            user=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )

    # 3. Default fallback: Console logger
    logger.info("email_service_provider_selected", type="console_fallback")
    return ConsoleEmailProvider()


async def _resolve_mx_host(domain: str) -> str | None:
    """Resolve the primary MX host for a domain using Cloudflare DNS-over-HTTPS API."""
    url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=MX"
    headers = {"Accept": "application/dns-json"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("Answer", [])
                if not answers:
                    return None
                mx_records = []
                for ans in answers:
                    if ans.get("type") == 15:  # MX record type
                        record_data = ans.get("data", "")
                        parts = record_data.split()
                        if len(parts) == 2:
                            try:
                                pref = int(parts[0])
                                host = parts[1].rstrip(".")
                                mx_records.append((pref, host))
                            except ValueError:
                                pass
                if mx_records:
                    mx_records.sort(key=lambda x: x[0])
                    return mx_records[0][1]
    except Exception:
        logger.exception("mx_resolution_failed", domain=domain)
    return None


async def send_otp_verification_email(email: str, code: str) -> None:
    """Send the 6-digit verification code using configured provider or direct MX delivery fallback."""
    from app.config import get_settings
    settings = get_settings()
    domain = email.split("@")[-1].lower() if "@" in email else ""
    provider = None

    # 1. If a real provider is explicitly configured (Resend or external SMTP), use it directly
    use_real_provider = False
    if settings.RESEND_API_KEY:
        use_real_provider = True
    elif settings.SMTP_HOST and settings.SMTP_HOST != "mailpit":
        use_real_provider = True

    if use_real_provider:
        provider = get_email_provider()
    else:
        # Fallback logic for local development
        mock_domains = {"example.com", "test.com", "infervoyage.local", "localhost"}
        if domain and domain not in mock_domains:
            # Resolve real MX host to bypass local mailpit and send real email
            mx_host = await _resolve_mx_host(domain)
            if mx_host:
                logger.info("mx_direct_delivery_selected", domain=domain, mx_host=mx_host)
                provider = SmtpEmailProvider(host=mx_host, port=25, user="noreply@infervoyage.com")

        if not provider:
            provider = get_email_provider()
    
    subject = "Verify your InferVoyage Account"
    body_text = f"Your 6-digit verification code is: {code}\n\nThis code expires in 5 minutes."
    
    body_html = f"""
    <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4f46e5; text-align: center;">InferVoyage</h2>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p>Hello,</p>
        <p>Thank you for signing up. Please enter the following 6-digit verification code to complete your registration:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 2.2rem; font-weight: 700; letter-spacing: 8px; background-color: #f3f4f6; padding: 12px 24px; border-radius: 6px; color: #1f2937; border: 1px solid #e5e7eb;">
                {code}
            </span>
        </div>
        <p style="color: #6b7280; font-size: 0.875rem;">This code is valid for <strong>5 minutes</strong>. If you did not request this, please ignore this email.</p>
    </div>
    """

    if settings.DEBUG or settings.SMTP_HOST == "mailpit":
        email_block = f"""
========================================================================
                      🔒 AI PLATFORM SECURITY OTP (DEBUG LOG)
========================================================================
To: {email}
Subject: {subject}

{body_text}
========================================================================
"""
        print(email_block)
    
    try:
        await provider.send_email(
            to_email=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        from app.observability.metrics import EMAILS_SENT_TOTAL
        EMAILS_SENT_TOTAL.labels(status="success", purpose="otp_verification").inc()
    except Exception as e:
        from app.observability.metrics import EMAILS_SENT_TOTAL
        EMAILS_SENT_TOTAL.labels(status="failure", purpose="otp_verification").inc()
        logger.error("email_delivery_failed_falling_back_to_console", error=str(e), email=email, code=code)
        fallback_provider = ConsoleEmailProvider()
        await fallback_provider.send_email(
            to_email=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )


async def send_password_reset_email(email: str, code: str) -> None:
    """Send the 6-digit password reset verification code using configured provider or direct MX delivery fallback."""
    from app.config import get_settings
    settings = get_settings()
    domain = email.split("@")[-1].lower() if "@" in email else ""
    provider = None

    # 1. If a real provider is explicitly configured (Resend or external SMTP), use it directly
    use_real_provider = False
    if settings.RESEND_API_KEY:
        use_real_provider = True
    elif settings.SMTP_HOST and settings.SMTP_HOST != "mailpit":
        use_real_provider = True

    if use_real_provider:
        provider = get_email_provider()
    else:
        # Fallback logic for local development
        mock_domains = {"example.com", "test.com", "infervoyage.local", "localhost"}
        if domain and domain not in mock_domains:
            # Resolve real MX host to bypass local mailpit and send real email
            mx_host = await _resolve_mx_host(domain)
            if mx_host:
                logger.info("mx_direct_delivery_selected", domain=domain, mx_host=mx_host)
                provider = SmtpEmailProvider(host=mx_host, port=25, user="noreply@infervoyage.com")

        if not provider:
            provider = get_email_provider()
    
    subject = "Reset your InferVoyage Password"
    body_text = f"Your 6-digit password reset verification code is: {code}\n\nThis code expires in 5 minutes."
    
    body_html = f"""
    <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4f46e5; text-align: center;">InferVoyage</h2>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p>Hello,</p>
        <p>We received a request to reset your password. Please enter the following 6-digit verification code to proceed:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 2.2rem; font-weight: 700; letter-spacing: 8px; background-color: #f3f4f6; padding: 12px 24px; border-radius: 6px; color: #1f2937; border: 1px solid #e5e7eb;">
                {code}
            </span>
        </div>
        <p style="color: #6b7280; font-size: 0.875rem;">This code is valid for <strong>5 minutes</strong>. If you did not request a password reset, you can safely ignore this email.</p>
    </div>
    """

    if settings.DEBUG or settings.SMTP_HOST == "mailpit":
        email_block = f"""
========================================================================
                      🔒 AI PLATFORM SECURITY OTP (DEBUG LOG)
========================================================================
To: {email}
Subject: {subject}

{body_text}
========================================================================
"""
        print(email_block)
    
    try:
        await provider.send_email(
            to_email=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        from app.observability.metrics import EMAILS_SENT_TOTAL
        EMAILS_SENT_TOTAL.labels(status="success", purpose="password_reset").inc()
    except Exception as e:
        from app.observability.metrics import EMAILS_SENT_TOTAL
        EMAILS_SENT_TOTAL.labels(status="failure", purpose="password_reset").inc()
        logger.error("password_reset_email_delivery_failed_falling_back_to_console", error=str(e), email=email, code=code)
        fallback_provider = ConsoleEmailProvider()
        await fallback_provider.send_email(
            to_email=email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
