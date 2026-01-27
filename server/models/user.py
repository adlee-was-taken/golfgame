"""
User-related models for Golf game authentication.

Defines user accounts, sessions, and guest tracking for the V2 auth system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
import json


class UserRole(str, Enum):
    """User role levels."""
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


@dataclass
class User:
    """
    A registered user account.

    Attributes:
        id: UUID primary key.
        username: Unique display name.
        email: Optional email address.
        password_hash: bcrypt hash of password.
        role: User role (guest, user, admin).
        email_verified: Whether email has been verified.
        verification_token: Token for email verification.
        verification_expires: When verification token expires.
        reset_token: Token for password reset.
        reset_expires: When reset token expires.
        guest_id: Guest session ID if converted from guest.
        deleted_at: Soft delete timestamp.
        preferences: User preferences as JSON.
        created_at: When account was created.
        last_login: Last login timestamp.
        last_seen_at: Last activity timestamp.
        is_active: Whether account is active.
        is_banned: Whether user is banned.
        ban_reason: Reason for ban (if banned).
        force_password_reset: Whether user must reset password on next login.
    """
    id: str
    username: str
    password_hash: str
    email: Optional[str] = None
    role: UserRole = UserRole.USER
    email_verified: bool = False
    verification_token: Optional[str] = None
    verification_expires: Optional[datetime] = None
    reset_token: Optional[str] = None
    reset_expires: Optional[datetime] = None
    guest_id: Optional[str] = None
    deleted_at: Optional[datetime] = None
    preferences: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    is_active: bool = True
    is_banned: bool = False
    ban_reason: Optional[str] = None
    force_password_reset: bool = False

    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN

    def is_guest(self) -> bool:
        """Check if user has guest role."""
        return self.role == UserRole.GUEST

    def can_login(self) -> bool:
        """Check if user can log in."""
        return self.is_active and self.deleted_at is None and not self.is_banned

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """
        Serialize user to dictionary.

        Args:
            include_sensitive: Include password hash and tokens.
        """
        d = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "email_verified": self.email_verified,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "is_active": self.is_active,
            "is_banned": self.is_banned,
            "ban_reason": self.ban_reason,
            "force_password_reset": self.force_password_reset,
        }
        if include_sensitive:
            d["password_hash"] = self.password_hash
            d["verification_token"] = self.verification_token
            d["verification_expires"] = (
                self.verification_expires.isoformat() if self.verification_expires else None
            )
            d["reset_token"] = self.reset_token
            d["reset_expires"] = (
                self.reset_expires.isoformat() if self.reset_expires else None
            )
            d["guest_id"] = self.guest_id
            d["deleted_at"] = self.deleted_at.isoformat() if self.deleted_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "User":
        """Deserialize user from dictionary."""
        def parse_dt(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=d["id"],
            username=d["username"],
            password_hash=d.get("password_hash", ""),
            email=d.get("email"),
            role=UserRole(d.get("role", "user")),
            email_verified=d.get("email_verified", False),
            verification_token=d.get("verification_token"),
            verification_expires=parse_dt(d.get("verification_expires")),
            reset_token=d.get("reset_token"),
            reset_expires=parse_dt(d.get("reset_expires")),
            guest_id=d.get("guest_id"),
            deleted_at=parse_dt(d.get("deleted_at")),
            preferences=d.get("preferences", {}),
            created_at=parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            last_login=parse_dt(d.get("last_login")),
            last_seen_at=parse_dt(d.get("last_seen_at")),
            is_active=d.get("is_active", True),
            is_banned=d.get("is_banned", False),
            ban_reason=d.get("ban_reason"),
            force_password_reset=d.get("force_password_reset", False),
        )


@dataclass
class UserSession:
    """
    An active user session.

    Session tokens are hashed before storage for security.

    Attributes:
        id: UUID primary key.
        user_id: Reference to user.
        token_hash: SHA256 hash of session token.
        device_info: Device/browser information.
        ip_address: Client IP address.
        created_at: When session was created.
        expires_at: When session expires.
        last_used_at: Last activity timestamp.
        revoked_at: When session was revoked (if any).
    """
    id: str
    user_id: str
    token_hash: str
    device_info: dict = field(default_factory=dict)
    ip_address: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None

    def is_valid(self) -> bool:
        """Check if session is still valid."""
        now = datetime.now(timezone.utc)
        return (
            self.revoked_at is None
            and self.expires_at > now
        )

    def to_dict(self) -> dict:
        """Serialize session to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token_hash": self.token_hash,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserSession":
        """Deserialize session from dictionary."""
        def parse_dt(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=d["id"],
            user_id=d["user_id"],
            token_hash=d["token_hash"],
            device_info=d.get("device_info", {}),
            ip_address=d.get("ip_address"),
            created_at=parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            expires_at=parse_dt(d.get("expires_at")) or datetime.now(timezone.utc),
            last_used_at=parse_dt(d.get("last_used_at")) or datetime.now(timezone.utc),
            revoked_at=parse_dt(d.get("revoked_at")),
        )


@dataclass
class GuestSession:
    """
    A guest session for tracking anonymous users.

    Guests can play games without registering. Their session
    can later be converted to a full user account.

    Attributes:
        id: Guest session ID (stored in client).
        display_name: Display name for the guest.
        created_at: When session was created.
        last_seen_at: Last activity timestamp.
        games_played: Number of games played as guest.
        converted_to_user_id: User ID if converted to account.
        expires_at: When guest session expires.
    """
    id: str
    display_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    games_played: int = 0
    converted_to_user_id: Optional[str] = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_converted(self) -> bool:
        """Check if guest has been converted to user."""
        return self.converted_to_user_id is not None

    def is_expired(self) -> bool:
        """Check if guest session has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        """Serialize guest session to dictionary."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "games_played": self.games_played,
            "converted_to_user_id": self.converted_to_user_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GuestSession":
        """Deserialize guest session from dictionary."""
        def parse_dt(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=d["id"],
            display_name=d.get("display_name"),
            created_at=parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            last_seen_at=parse_dt(d.get("last_seen_at")) or datetime.now(timezone.utc),
            games_played=d.get("games_played", 0),
            converted_to_user_id=d.get("converted_to_user_id"),
            expires_at=parse_dt(d.get("expires_at")) or datetime.now(timezone.utc),
        )
