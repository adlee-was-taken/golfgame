"""
Authentication service for Golf game.

Provides business logic for user registration, login, password management,
and session handling.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt

from config import config
from models.user import User, UserRole, UserSession, GuestSession
from stores.user_store import UserStore
from services.email_service import EmailService

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result of an authentication operation."""
    success: bool
    user: Optional[User] = None
    token: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class RegistrationResult:
    """Result of a registration operation."""
    success: bool
    user: Optional[User] = None
    requires_verification: bool = False
    error: Optional[str] = None


class AuthService:
    """
    Authentication service.

    Handles all authentication business logic:
    - User registration with optional email verification
    - Login/logout with session management
    - Password reset flow
    - Guest-to-user conversion
    - Account deletion (soft delete)
    """

    def __init__(
        self,
        user_store: UserStore,
        email_service: EmailService,
        session_expiry_hours: int = 168,
        require_email_verification: bool = False,
    ):
        """
        Initialize auth service.

        Args:
            user_store: User persistence store.
            email_service: Email sending service.
            session_expiry_hours: Session lifetime in hours.
            require_email_verification: Whether to require email verification.
        """
        self.user_store = user_store
        self.email_service = email_service
        self.session_expiry_hours = session_expiry_hours
        self.require_email_verification = require_email_verification

    @classmethod
    async def create(cls, user_store: UserStore) -> "AuthService":
        """
        Create AuthService from config.

        Args:
            user_store: User persistence store.
        """
        from services.email_service import get_email_service

        return cls(
            user_store=user_store,
            email_service=get_email_service(),
            session_expiry_hours=config.SESSION_EXPIRY_HOURS,
            require_email_verification=config.REQUIRE_EMAIL_VERIFICATION,
        )

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    async def register(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        guest_id: Optional[str] = None,
    ) -> RegistrationResult:
        """
        Register a new user account.

        Args:
            username: Desired username.
            password: Plain text password.
            email: Optional email address.
            guest_id: Guest session ID if converting.

        Returns:
            RegistrationResult with user or error.
        """
        # Validate inputs
        if len(username) < 2 or len(username) > 50:
            return RegistrationResult(success=False, error="Username must be 2-50 characters")

        if len(password) < 8:
            return RegistrationResult(success=False, error="Password must be at least 8 characters")

        # Check for existing username
        existing = await self.user_store.get_user_by_username(username)
        if existing:
            return RegistrationResult(success=False, error="Username already taken")

        # Check for existing email
        if email:
            existing = await self.user_store.get_user_by_email(email)
            if existing:
                return RegistrationResult(success=False, error="Email already registered")

        # Hash password
        password_hash = self._hash_password(password)

        # Generate verification token if needed
        verification_token = None
        verification_expires = None
        if email and self.require_email_verification:
            verification_token = secrets.token_urlsafe(32)
            verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

        # Create user
        user = await self.user_store.create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            role=UserRole.USER,
            guest_id=guest_id,
            verification_token=verification_token,
            verification_expires=verification_expires,
        )

        if not user:
            return RegistrationResult(success=False, error="Failed to create account")

        # Mark guest as converted if applicable
        if guest_id:
            await self.user_store.mark_guest_converted(guest_id, user.id)

        # Send verification email if needed
        requires_verification = False
        if email and self.require_email_verification and verification_token:
            await self.email_service.send_verification_email(
                to=email,
                token=verification_token,
                username=username,
            )
            await self.user_store.log_email(user.id, "verification", email)
            requires_verification = True

        return RegistrationResult(
            success=True,
            user=user,
            requires_verification=requires_verification,
        )

    async def verify_email(self, token: str) -> AuthResult:
        """
        Verify email with token.

        Args:
            token: Verification token from email.

        Returns:
            AuthResult with success status.
        """
        user = await self.user_store.get_user_by_verification_token(token)
        if not user:
            return AuthResult(success=False, error="Invalid verification token")

        # Check expiration
        if user.verification_expires and user.verification_expires < datetime.now(timezone.utc):
            return AuthResult(success=False, error="Verification token expired")

        # Mark as verified
        await self.user_store.clear_verification_token(user.id)

        # Refresh user
        user = await self.user_store.get_user_by_id(user.id)

        return AuthResult(success=True, user=user)

    async def resend_verification(self, email: str) -> bool:
        """
        Resend verification email.

        Args:
            email: Email address to send to.

        Returns:
            True if email was sent.
        """
        user = await self.user_store.get_user_by_email(email)
        if not user or user.email_verified:
            return False

        # Generate new token
        verification_token = secrets.token_urlsafe(32)
        verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

        await self.user_store.update_user(
            user.id,
            verification_token=verification_token,
            verification_expires=verification_expires,
        )

        await self.email_service.send_verification_email(
            to=email,
            token=verification_token,
            username=user.username,
        )
        await self.user_store.log_email(user.id, "verification", email)

        return True

    # -------------------------------------------------------------------------
    # Login/Logout
    # -------------------------------------------------------------------------

    async def login(
        self,
        username: str,
        password: str,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuthResult:
        """
        Authenticate user and create session.

        Args:
            username: Username or email.
            password: Plain text password.
            device_info: Client device information.
            ip_address: Client IP address.

        Returns:
            AuthResult with session token or error.
        """
        # Try username first, then email
        user = await self.user_store.get_user_by_username(username)
        if not user:
            user = await self.user_store.get_user_by_email(username)

        if not user:
            return AuthResult(success=False, error="Invalid credentials")

        if not user.can_login():
            return AuthResult(success=False, error="Account is disabled")

        # Check email verification if required
        if self.require_email_verification and user.email and not user.email_verified:
            return AuthResult(success=False, error="Please verify your email first")

        # Verify password
        if not self._verify_password(password, user.password_hash):
            return AuthResult(success=False, error="Invalid credentials")

        # Create session
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.session_expiry_hours)

        await self.user_store.create_session(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address,
        )

        # Update last login
        await self.user_store.update_user(user.id, last_login=datetime.now(timezone.utc))

        return AuthResult(
            success=True,
            user=user,
            token=token,
            expires_at=expires_at,
        )

    async def logout(self, token: str) -> bool:
        """
        Invalidate a session.

        Args:
            token: Session token to invalidate.

        Returns:
            True if session was revoked.
        """
        return await self.user_store.revoke_session_by_token(token)

    async def logout_all(self, user_id: str, except_token: Optional[str] = None) -> int:
        """
        Invalidate all sessions for a user.

        Args:
            user_id: User ID.
            except_token: Optional token to keep active.

        Returns:
            Number of sessions revoked.
        """
        return await self.user_store.revoke_all_sessions(user_id, except_token)

    async def get_user_from_token(self, token: str) -> Optional[User]:
        """
        Get user from session token.

        Args:
            token: Session token.

        Returns:
            User if valid session, None otherwise.
        """
        session = await self.user_store.get_session_by_token(token)
        if not session or not session.is_valid():
            return None

        # Update last used
        await self.user_store.update_session_last_used(session.id)

        user = await self.user_store.get_user_by_id(session.user_id)
        if not user or not user.can_login():
            return None

        return user

    # -------------------------------------------------------------------------
    # Password Management
    # -------------------------------------------------------------------------

    async def forgot_password(self, email: str) -> bool:
        """
        Initiate password reset flow.

        Args:
            email: Email address.

        Returns:
            True if reset email was sent (always returns True to prevent enumeration).
        """
        user = await self.user_store.get_user_by_email(email)
        if not user:
            # Don't reveal if email exists
            return True

        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)

        await self.user_store.update_user(
            user.id,
            reset_token=reset_token,
            reset_expires=reset_expires,
        )

        await self.email_service.send_password_reset_email(
            to=email,
            token=reset_token,
            username=user.username,
        )
        await self.user_store.log_email(user.id, "password_reset", email)

        return True

    async def reset_password(self, token: str, new_password: str) -> AuthResult:
        """
        Reset password using token.

        Args:
            token: Reset token from email.
            new_password: New password.

        Returns:
            AuthResult with success status.
        """
        if len(new_password) < 8:
            return AuthResult(success=False, error="Password must be at least 8 characters")

        user = await self.user_store.get_user_by_reset_token(token)
        if not user:
            return AuthResult(success=False, error="Invalid reset token")

        # Check expiration
        if user.reset_expires and user.reset_expires < datetime.now(timezone.utc):
            return AuthResult(success=False, error="Reset token expired")

        # Update password
        password_hash = self._hash_password(new_password)
        await self.user_store.update_user(user.id, password_hash=password_hash)
        await self.user_store.clear_reset_token(user.id)

        # Revoke all sessions
        await self.user_store.revoke_all_sessions(user.id)

        # Send notification
        if user.email:
            await self.email_service.send_password_changed_notification(
                to=user.email,
                username=user.username,
            )
            await self.user_store.log_email(user.id, "password_changed", user.email)

        return AuthResult(success=True, user=user)

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        current_token: Optional[str] = None,
    ) -> AuthResult:
        """
        Change password for authenticated user.

        Args:
            user_id: User ID.
            current_password: Current password for verification.
            new_password: New password.
            current_token: Current session token to keep active.

        Returns:
            AuthResult with success status.
        """
        if len(new_password) < 8:
            return AuthResult(success=False, error="Password must be at least 8 characters")

        user = await self.user_store.get_user_by_id(user_id)
        if not user:
            return AuthResult(success=False, error="User not found")

        # Verify current password
        if not self._verify_password(current_password, user.password_hash):
            return AuthResult(success=False, error="Current password is incorrect")

        # Update password
        password_hash = self._hash_password(new_password)
        await self.user_store.update_user(user.id, password_hash=password_hash)

        # Revoke all sessions except current
        await self.user_store.revoke_all_sessions(user.id, except_token=current_token)

        # Send notification
        if user.email:
            await self.email_service.send_password_changed_notification(
                to=user.email,
                username=user.username,
            )
            await self.user_store.log_email(user.id, "password_changed", user.email)

        return AuthResult(success=True, user=user)

    # -------------------------------------------------------------------------
    # User Profile
    # -------------------------------------------------------------------------

    async def update_preferences(self, user_id: str, preferences: dict) -> Optional[User]:
        """
        Update user preferences.

        Args:
            user_id: User ID.
            preferences: New preferences dict.

        Returns:
            Updated user or None.
        """
        return await self.user_store.update_user(user_id, preferences=preferences)

    async def get_sessions(self, user_id: str) -> list[UserSession]:
        """
        Get all active sessions for a user.

        Args:
            user_id: User ID.

        Returns:
            List of active sessions.
        """
        return await self.user_store.get_sessions_for_user(user_id)

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        """
        Revoke a specific session.

        Args:
            user_id: User ID (for authorization).
            session_id: Session ID to revoke.

        Returns:
            True if session was revoked.
        """
        # Verify session belongs to user
        sessions = await self.user_store.get_sessions_for_user(user_id)
        if not any(s.id == session_id for s in sessions):
            return False

        return await self.user_store.revoke_session(session_id)

    # -------------------------------------------------------------------------
    # Guest Conversion
    # -------------------------------------------------------------------------

    async def convert_guest(
        self,
        guest_id: str,
        username: str,
        password: str,
        email: Optional[str] = None,
    ) -> RegistrationResult:
        """
        Convert guest session to full user account.

        Args:
            guest_id: Guest session ID.
            username: Desired username.
            password: Password.
            email: Optional email.

        Returns:
            RegistrationResult with user or error.
        """
        # Verify guest exists and not already converted
        guest = await self.user_store.get_guest_session(guest_id)
        if not guest:
            return RegistrationResult(success=False, error="Guest session not found")

        if guest.is_converted():
            return RegistrationResult(success=False, error="Guest already converted")

        # Register with guest ID
        return await self.register(
            username=username,
            password=password,
            email=email,
            guest_id=guest_id,
        )

    # -------------------------------------------------------------------------
    # Account Deletion
    # -------------------------------------------------------------------------

    async def delete_account(self, user_id: str) -> bool:
        """
        Soft delete user account.

        Args:
            user_id: User ID to delete.

        Returns:
            True if account was deleted.
        """
        # Revoke all sessions
        await self.user_store.revoke_all_sessions(user_id)

        # Soft delete
        user = await self.user_store.update_user(
            user_id,
            is_active=False,
            deleted_at=datetime.now(timezone.utc),
        )

        return user is not None

    # -------------------------------------------------------------------------
    # Guest Sessions
    # -------------------------------------------------------------------------

    async def create_guest_session(
        self,
        guest_id: str,
        display_name: Optional[str] = None,
    ) -> GuestSession:
        """
        Create or get guest session.

        Args:
            guest_id: Guest session ID.
            display_name: Display name for guest.

        Returns:
            GuestSession.
        """
        existing = await self.user_store.get_guest_session(guest_id)
        if existing:
            await self.user_store.update_guest_last_seen(guest_id)
            return existing

        return await self.user_store.create_guest_session(guest_id, display_name)

    # -------------------------------------------------------------------------
    # Password Hashing
    # -------------------------------------------------------------------------

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False


# Global auth service instance
_auth_service: Optional[AuthService] = None


async def get_auth_service(user_store: UserStore) -> AuthService:
    """
    Get or create the global auth service instance.

    Args:
        user_store: User persistence store.

    Returns:
        AuthService instance.
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = await AuthService.create(user_store)
    return _auth_service


async def close_auth_service() -> None:
    """Close the global auth service."""
    global _auth_service
    _auth_service = None
