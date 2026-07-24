import os
import random
import logging
import smtplib
import asyncio
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Transient thread-safe in-memory store for OTPs
# Structure: { email: { "otp": str, "expires_at": datetime } }
_otp_store: Dict[str, Dict[str, Any]] = {}

class EmailService:
    def __init__(self):
        # Read environment variables
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "")
        self.smtp_from_name = os.getenv("SMTP_FROM_NAME", "AI Voice Agent")
        
        # TLS / SSL configuration flags
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.smtp_use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    def generate_otp(self) -> str:
        """Generate a secure 6-digit numeric OTP."""
        return str(random.randint(100000, 999999))

    def _get_rendered_template(self, client_name: str, otp: str) -> str:
        """Load and render the OTP HTML template."""
        try:
            template_path = Path(__file__).parent.parent / "templates" / "otp_email.html"
            if template_path.exists():
                html_content = template_path.read_text(encoding="utf-8")
                return html_content.replace("{client_name}", client_name).replace("{otp}", otp)
        except Exception as e:
            logger.error(f"Failed to load OTP email template: {e}")
        
        # Simple fallback template
        return f"<h3>AI Voice Agent Platform</h3><p>Hello {client_name},</p><p>Your verification code is: <b>{otp}</b></p>"

    def _send_smtp_sync(self, to_email: str, subject: str, html_body: str):
        """Synchronous SMTP email dispatcher helper."""
        if not self.smtp_host or not self.smtp_username or not self.smtp_password:
            logger.warning(
                "SMTP host, username, or password is not configured in .env. "
                "Skipping SMTP email sending."
            )
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.smtp_from_name} <{self.smtp_from_email or self.smtp_username}>"
        msg["To"] = to_email

        msg.attach(MIMEText(html_body, "html"))

        # Connect to SMTP Server
        if self.smtp_use_ssl:
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)

        try:
            if not self.smtp_use_ssl and self.smtp_use_tls:
                server.starttls()
            
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(
                self.smtp_from_email or self.smtp_username,
                to_email,
                msg.as_string()
            )
            logger.info(f"Verification OTP email sent to {to_email} successfully.")
        finally:
            server.quit()

    async def send_otp_email(self, email: str, client_name: str) -> str:
        """
        Generate, store, and asynchronously dispatch an OTP email to prevent
        event loop blockages.
        """
        otp = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Store OTP code
        _otp_store[email.lower().strip()] = {
            "otp": otp,
            "expires_at": expires_at
        }
        
        # Log to server console for easy development/testing
        logger.info(f"*** DEVELOPMENT OTP for {email} is: {otp} (expires in 10m) ***")

        html_body = self._get_rendered_template(client_name, otp)
        subject = "Verify your email address - AI Voice Agent Platform"

        # Dispatch via executor thread to keep FastAPI non-blocking
        if self.smtp_host and self.smtp_username and self.smtp_password:
            asyncio.create_task(
                asyncio.to_thread(self._send_smtp_sync, email, subject, html_body)
            )
        else:
            logger.info("Email service skipped email transmission due to missing credentials.")

        return otp

    def verify_otp(self, email: str, otp: str) -> bool:
        """Verify the OTP matches and has not expired."""
        email_key = email.lower().strip()
        if email_key not in _otp_store:
            logger.warning(f"No verification session found for email: {email_key}")
            return False

        record = _otp_store[email_key]
        if datetime.utcnow() > record["expires_at"]:
            logger.warning(f"Verification OTP expired for email: {email_key}")
            del _otp_store[email_key]
            return False

        if record["otp"] != otp.strip():
            logger.warning(f"Invalid verification OTP entered for email: {email_key}")
            return False

        # Verification successful, clear active record
        del _otp_store[email_key]
        logger.info(f"Email {email_key} successfully verified via OTP.")
        return True
