"""
Email service for Golf game authentication.

Provides email sending via Resend for verification, password reset, and notifications.
"""

import logging
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service using Resend API.

    Handles all transactional emails for authentication:
    - Email verification
    - Password reset
    - Password changed notification
    """

    def __init__(self, api_key: str, from_address: str, base_url: str):
        """
        Initialize email service.

        Args:
            api_key: Resend API key.
            from_address: Sender email address.
            base_url: Base URL for verification/reset links.
        """
        self.api_key = api_key
        self.from_address = from_address
        self.base_url = base_url.rstrip("/")
        self._client = None

    @classmethod
    def create(cls) -> "EmailService":
        """Create EmailService from config."""
        return cls(
            api_key=config.RESEND_API_KEY,
            from_address=config.EMAIL_FROM,
            base_url=config.BASE_URL,
        )

    @property
    def client(self):
        """Lazy-load Resend client."""
        if self._client is None:
            try:
                import resend
                resend.api_key = self.api_key
                self._client = resend
            except ImportError:
                logger.warning("resend package not installed, emails will be logged only")
                self._client = None
        return self._client

    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return bool(self.api_key)

    async def send_verification_email(
        self,
        to: str,
        token: str,
        username: str,
    ) -> Optional[str]:
        """
        Send email verification email.

        Args:
            to: Recipient email address.
            token: Verification token.
            username: User's display name.

        Returns:
            Resend message ID if sent, None if not configured.
        """
        if not self.is_configured():
            logger.info(f"Email not configured. Would send verification to {to}")
            return None

        verify_url = f"{self.base_url}/verify-email?token={token}"

        subject = "Verify your Golf Game account"
        html = f"""
        <h2>Welcome to Golf Game, {username}!</h2>
        <p>Please verify your email address by clicking the link below:</p>
        <p><a href="{verify_url}">Verify Email Address</a></p>
        <p>Or copy and paste this URL into your browser:</p>
        <p>{verify_url}</p>
        <p>This link will expire in 24 hours.</p>
        <p>If you didn't create this account, you can safely ignore this email.</p>
        """

        return await self._send_email(to, subject, html)

    async def send_password_reset_email(
        self,
        to: str,
        token: str,
        username: str,
    ) -> Optional[str]:
        """
        Send password reset email.

        Args:
            to: Recipient email address.
            token: Reset token.
            username: User's display name.

        Returns:
            Resend message ID if sent, None if not configured.
        """
        if not self.is_configured():
            logger.info(f"Email not configured. Would send password reset to {to}")
            return None

        reset_url = f"{self.base_url}/reset-password?token={token}"

        subject = "Reset your Golf Game password"
        html = f"""
        <h2>Password Reset Request</h2>
        <p>Hi {username},</p>
        <p>We received a request to reset your password. Click the link below to set a new password:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>Or copy and paste this URL into your browser:</p>
        <p>{reset_url}</p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request this, you can safely ignore this email. Your password will remain unchanged.</p>
        """

        return await self._send_email(to, subject, html)

    async def send_password_changed_notification(
        self,
        to: str,
        username: str,
    ) -> Optional[str]:
        """
        Send password changed notification email.

        Args:
            to: Recipient email address.
            username: User's display name.

        Returns:
            Resend message ID if sent, None if not configured.
        """
        if not self.is_configured():
            logger.info(f"Email not configured. Would send password change notification to {to}")
            return None

        subject = "Your Golf Game password was changed"
        html = f"""
        <h2>Password Changed</h2>
        <p>Hi {username},</p>
        <p>Your password was successfully changed.</p>
        <p>If you did not make this change, please contact support immediately.</p>
        """

        return await self._send_email(to, subject, html)

    async def _send_email(
        self,
        to: str,
        subject: str,
        html: str,
    ) -> Optional[str]:
        """
        Send an email via Resend.

        Args:
            to: Recipient email address.
            subject: Email subject.
            html: HTML email body.

        Returns:
            Resend message ID if sent, None on error.
        """
        if not self.client:
            logger.warning(f"Resend not available. Email to {to}: {subject}")
            return None

        try:
            params = {
                "from": self.from_address,
                "to": [to],
                "subject": subject,
                "html": html,
            }

            response = self.client.Emails.send(params)
            message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
            logger.info(f"Email sent to {to}: {message_id}")
            return message_id

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return None


# Global email service instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create the global email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService.create()
    return _email_service
