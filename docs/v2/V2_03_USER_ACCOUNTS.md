# V2-03: User Accounts & Authentication

## Overview

This document covers the complete user account lifecycle: registration, email verification, login, password reset, session management, and account settings.

**Dependencies:** V2-02 (Persistence - PostgreSQL setup)
**Dependents:** V2-04 (Admin Tools), V2-05 (Stats/Leaderboards)

---

## Goals

1. Email service integration (Resend)
2. User registration with email verification
3. Password reset via email
4. Session management (view/revoke)
5. Account settings and preferences
6. Guest-to-user conversion flow
7. Account deletion (GDPR-friendly)

---

## Current State

Basic auth exists in `auth.py`:
- Username/password authentication
- Session tokens stored in SQLite
- Admin role support
- Invite codes for registration

**Missing:**
- Email integration
- Email verification
- Password reset flow
- Session management UI
- Account deletion
- Guest accounts

---

## User Flow Diagrams

### Registration Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Enter   │     │  Create  │     │  Send    │     │  Click   │
│  Email + │────►│  Pending │────►│  Verify  │────►│  Verify  │
│  Password│     │  Account │     │  Email   │     │  Link    │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                         │
                                                         ▼
                                                   ┌──────────┐
                                                   │  Account │
                                                   │  Active  │
                                                   └──────────┘
```

### Password Reset Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Enter   │     │  Generate│     │  Send    │     │  Click   │
│  Email   │────►│  Reset   │────►│  Reset   │────►│  Reset   │
│          │     │  Token   │     │  Email   │     │  Link    │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                         │
                                                         ▼
                                                   ┌──────────┐
                                                   │  Enter   │
                                                   │  New     │
                                                   │  Password│
                                                   └──────────┘
```

### Guest Conversion Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Play as │     │  Prompt  │     │  Enter   │     │  Link    │
│  Guest   │────►│  "Save   │────►│  Email + │────►│  Guest   │
│          │     │  Stats?" │     │  Password│     │  to User │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

---

## Database Schema

```sql
-- migrations/versions/002_user_accounts.sql

-- Extend existing users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_expires TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS guest_id VARCHAR(50);  -- Links to guest session
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;  -- Soft delete
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';

-- Sessions table (replace or extend existing)
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    device_info JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,

    -- Index for token lookups
    CONSTRAINT idx_sessions_token UNIQUE (token_hash)
);

-- Guest sessions (for guest-to-user conversion)
CREATE TABLE IF NOT EXISTS guest_sessions (
    id VARCHAR(50) PRIMARY KEY,  -- UUID stored as string
    display_name VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    games_played INT DEFAULT 0,
    converted_to_user_id UUID REFERENCES users(id),

    -- Expire after 30 days of inactivity
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 days'
);

-- Email log (for debugging/audit)
CREATE TABLE IF NOT EXISTS email_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    email_type VARCHAR(50) NOT NULL,  -- verification, password_reset, etc.
    recipient VARCHAR(255) NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    resend_id VARCHAR(100),  -- ID from email provider
    status VARCHAR(20) DEFAULT 'sent'
);

-- Indexes
CREATE INDEX idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE INDEX idx_users_guest ON users(guest_id) WHERE guest_id IS NOT NULL;
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at) WHERE revoked_at IS NULL;
CREATE INDEX idx_guests_expires ON guest_sessions(expires_at);
```

---

## Email Service

```python
# server/services/email_service.py
import resend
from typing import Optional
from datetime import datetime
import os

from config import config


class EmailService:
    """Email sending via Resend."""

    def __init__(self):
        resend.api_key = config.RESEND_API_KEY
        self.from_email = config.EMAIL_FROM  # e.g., "Golf Game <noreply@yourdomain.com>"
        self.base_url = config.BASE_URL  # e.g., "https://golf.yourdomain.com"

    async def send_verification_email(
        self,
        to_email: str,
        username: str,
        verification_token: str,
    ) -> Optional[str]:
        """Send email verification link."""
        verify_url = f"{self.base_url}/verify?token={verification_token}"

        try:
            response = resend.Emails.send({
                "from": self.from_email,
                "to": to_email,
                "subject": "Verify your Golf Game account",
                "html": f"""
                <h2>Welcome to Golf Game, {username}!</h2>
                <p>Please verify your email address by clicking the link below:</p>
                <p><a href="{verify_url}" style="
                    background-color: #4CAF50;
                    color: white;
                    padding: 14px 20px;
                    text-decoration: none;
                    display: inline-block;
                    border-radius: 4px;
                ">Verify Email</a></p>
                <p>Or copy this link: {verify_url}</p>
                <p>This link expires in 24 hours.</p>
                <p>If you didn't create this account, you can ignore this email.</p>
                """,
                "text": f"""
                Welcome to Golf Game, {username}!

                Please verify your email address by visiting:
                {verify_url}

                This link expires in 24 hours.

                If you didn't create this account, you can ignore this email.
                """,
            })
            return response.get("id")
        except Exception as e:
            print(f"Failed to send verification email: {e}")
            return None

    async def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_token: str,
    ) -> Optional[str]:
        """Send password reset link."""
        reset_url = f"{self.base_url}/reset-password?token={reset_token}"

        try:
            response = resend.Emails.send({
                "from": self.from_email,
                "to": to_email,
                "subject": "Reset your Golf Game password",
                "html": f"""
                <h2>Password Reset Request</h2>
                <p>Hi {username},</p>
                <p>We received a request to reset your password. Click the link below to choose a new password:</p>
                <p><a href="{reset_url}" style="
                    background-color: #2196F3;
                    color: white;
                    padding: 14px 20px;
                    text-decoration: none;
                    display: inline-block;
                    border-radius: 4px;
                ">Reset Password</a></p>
                <p>Or copy this link: {reset_url}</p>
                <p>This link expires in 1 hour.</p>
                <p>If you didn't request this, you can ignore this email. Your password won't be changed.</p>
                """,
                "text": f"""
                Password Reset Request

                Hi {username},

                We received a request to reset your password. Visit this link to choose a new password:
                {reset_url}

                This link expires in 1 hour.

                If you didn't request this, you can ignore this email. Your password won't be changed.
                """,
            })
            return response.get("id")
        except Exception as e:
            print(f"Failed to send password reset email: {e}")
            return None

    async def send_password_changed_notification(
        self,
        to_email: str,
        username: str,
    ) -> Optional[str]:
        """Notify user their password was changed."""
        try:
            response = resend.Emails.send({
                "from": self.from_email,
                "to": to_email,
                "subject": "Your Golf Game password was changed",
                "html": f"""
                <h2>Password Changed</h2>
                <p>Hi {username},</p>
                <p>Your Golf Game password was recently changed.</p>
                <p>If you made this change, you can ignore this email.</p>
                <p>If you didn't change your password, please <a href="{self.base_url}/reset-password">reset it immediately</a> and contact support.</p>
                """,
                "text": f"""
                Password Changed

                Hi {username},

                Your Golf Game password was recently changed.

                If you made this change, you can ignore this email.

                If you didn't change your password, please reset it immediately at:
                {self.base_url}/reset-password
                """,
            })
            return response.get("id")
        except Exception as e:
            print(f"Failed to send password changed notification: {e}")
            return None
```

---

## Auth Service

```python
# server/services/auth_service.py
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass
import asyncpg
from passlib.hash import bcrypt

from services.email_service import EmailService


@dataclass
class User:
    id: str
    username: str
    email: Optional[str]
    role: str
    email_verified: bool
    created_at: datetime
    preferences: dict


@dataclass
class Session:
    id: str
    user_id: str
    device_info: dict
    ip_address: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime


class AuthService:
    """User authentication and account management."""

    TOKEN_EXPIRY_HOURS = 24 * 7  # 1 week
    VERIFICATION_EXPIRY_HOURS = 24
    RESET_EXPIRY_HOURS = 1

    def __init__(self, db_pool: asyncpg.Pool, email_service: EmailService):
        self.db = db_pool
        self.email = email_service

    # --- Registration ---

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        guest_id: Optional[str] = None,
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        Register a new user.
        Returns (user, error_message).
        """
        # Validate input
        if len(username) < 3 or len(username) > 30:
            return None, "Username must be 3-30 characters"

        if not self._is_valid_email(email):
            return None, "Invalid email address"

        if len(password) < 8:
            return None, "Password must be at least 8 characters"

        async with self.db.acquire() as conn:
            # Check if username or email exists
            existing = await conn.fetchrow("""
                SELECT id FROM users
                WHERE username = $1 OR email = $2
            """, username, email)

            if existing:
                return None, "Username or email already registered"

            # Generate verification token
            verification_token = secrets.token_urlsafe(32)
            verification_expires = datetime.utcnow() + timedelta(
                hours=self.VERIFICATION_EXPIRY_HOURS
            )

            # Hash password
            password_hash = bcrypt.hash(password)

            # Create user
            user_id = secrets.token_urlsafe(16)

            await conn.execute("""
                INSERT INTO users (
                    id, username, email, password_hash, role,
                    email_verified, verification_token, verification_expires,
                    guest_id, created_at
                ) VALUES ($1, $2, $3, $4, 'user', false, $5, $6, $7, NOW())
            """, user_id, username, email, password_hash,
                verification_token, verification_expires, guest_id)

            # If converting from guest, link stats
            if guest_id:
                await self._convert_guest_stats(conn, guest_id, user_id)

        # Send verification email
        await self.email.send_verification_email(
            email, username, verification_token
        )

        return User(
            id=user_id,
            username=username,
            email=email,
            role="user",
            email_verified=False,
            created_at=datetime.utcnow(),
            preferences={},
        ), None

    async def verify_email(self, token: str) -> Tuple[bool, str]:
        """
        Verify email with token.
        Returns (success, message).
        """
        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, verification_expires
                FROM users
                WHERE verification_token = $1
                AND deleted_at IS NULL
            """, token)

            if not user:
                return False, "Invalid verification link"

            if user["verification_expires"] < datetime.utcnow():
                return False, "Verification link has expired"

            await conn.execute("""
                UPDATE users
                SET email_verified = true,
                    verification_token = NULL,
                    verification_expires = NULL
                WHERE id = $1
            """, user["id"])

            return True, "Email verified successfully"

    async def resend_verification(self, email: str) -> Tuple[bool, str]:
        """Resend verification email."""
        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, email_verified
                FROM users
                WHERE email = $1
                AND deleted_at IS NULL
            """, email)

            if not user:
                # Don't reveal if email exists
                return True, "If that email is registered, a verification link has been sent"

            if user["email_verified"]:
                return False, "Email is already verified"

            # Generate new token
            verification_token = secrets.token_urlsafe(32)
            verification_expires = datetime.utcnow() + timedelta(
                hours=self.VERIFICATION_EXPIRY_HOURS
            )

            await conn.execute("""
                UPDATE users
                SET verification_token = $1, verification_expires = $2
                WHERE id = $3
            """, verification_token, verification_expires, user["id"])

        await self.email.send_verification_email(
            email, user["username"], verification_token
        )

        return True, "Verification email sent"

    # --- Login ---

    async def login(
        self,
        username_or_email: str,
        password: str,
        device_info: dict,
        ip_address: str,
    ) -> Tuple[Optional[str], Optional[User], Optional[str]]:
        """
        Login user.
        Returns (session_token, user, error_message).
        """
        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, email, password_hash, role,
                       email_verified, preferences, created_at
                FROM users
                WHERE (username = $1 OR email = $1)
                AND deleted_at IS NULL
            """, username_or_email)

            if not user:
                return None, None, "Invalid username or password"

            if not bcrypt.verify(password, user["password_hash"]):
                return None, None, "Invalid username or password"

            # Check email verification (optional - can allow login without)
            # if not user["email_verified"]:
            #     return None, None, "Please verify your email first"

            # Create session
            session_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()
            expires_at = datetime.utcnow() + timedelta(hours=self.TOKEN_EXPIRY_HOURS)

            await conn.execute("""
                INSERT INTO user_sessions (
                    user_id, token_hash, device_info, ip_address, expires_at
                ) VALUES ($1, $2, $3, $4, $5)
            """, user["id"], token_hash, device_info, ip_address, expires_at)

            # Update last login
            await conn.execute("""
                UPDATE users SET last_seen_at = NOW() WHERE id = $1
            """, user["id"])

            return session_token, User(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                role=user["role"],
                email_verified=user["email_verified"],
                created_at=user["created_at"],
                preferences=user["preferences"] or {},
            ), None

    async def logout(self, session_token: str) -> bool:
        """Logout (revoke session)."""
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()

        async with self.db.acquire() as conn:
            result = await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE token_hash = $1
                AND revoked_at IS NULL
            """, token_hash)

            return result != "UPDATE 0"

    async def logout_all(self, user_id: str, except_token: Optional[str] = None) -> int:
        """Logout all sessions for a user."""
        async with self.db.acquire() as conn:
            if except_token:
                except_hash = hashlib.sha256(except_token.encode()).hexdigest()
                result = await conn.execute("""
                    UPDATE user_sessions
                    SET revoked_at = NOW()
                    WHERE user_id = $1
                    AND revoked_at IS NULL
                    AND token_hash != $2
                """, user_id, except_hash)
            else:
                result = await conn.execute("""
                    UPDATE user_sessions
                    SET revoked_at = NOW()
                    WHERE user_id = $1
                    AND revoked_at IS NULL
                """, user_id)

            # Parse "UPDATE N" to get count
            return int(result.split()[1])

    async def validate_session(self, session_token: str) -> Optional[User]:
        """Validate session token, return user if valid."""
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()

        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT u.id, u.username, u.email, u.role,
                       u.email_verified, u.preferences, u.created_at,
                       s.id as session_id
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token_hash = $1
                AND s.revoked_at IS NULL
                AND s.expires_at > NOW()
                AND u.deleted_at IS NULL
            """, token_hash)

            if not row:
                return None

            # Update last used
            await conn.execute("""
                UPDATE user_sessions SET last_used_at = NOW() WHERE id = $1
            """, row["session_id"])

            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                role=row["role"],
                email_verified=row["email_verified"],
                created_at=row["created_at"],
                preferences=row["preferences"] or {},
            )

    # --- Password Reset ---

    async def request_password_reset(self, email: str) -> Tuple[bool, str]:
        """Request password reset email."""
        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, email
                FROM users
                WHERE email = $1
                AND deleted_at IS NULL
            """, email)

            if not user:
                # Don't reveal if email exists
                return True, "If that email is registered, a reset link has been sent"

            # Generate reset token
            reset_token = secrets.token_urlsafe(32)
            reset_expires = datetime.utcnow() + timedelta(
                hours=self.RESET_EXPIRY_HOURS
            )

            await conn.execute("""
                UPDATE users
                SET reset_token = $1, reset_expires = $2
                WHERE id = $3
            """, reset_token, reset_expires, user["id"])

        await self.email.send_password_reset_email(
            email, user["username"], reset_token
        )

        return True, "Reset link sent"

    async def reset_password(
        self,
        token: str,
        new_password: str,
    ) -> Tuple[bool, str]:
        """Reset password with token."""
        if len(new_password) < 8:
            return False, "Password must be at least 8 characters"

        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, email, reset_expires
                FROM users
                WHERE reset_token = $1
                AND deleted_at IS NULL
            """, token)

            if not user:
                return False, "Invalid reset link"

            if user["reset_expires"] < datetime.utcnow():
                return False, "Reset link has expired"

            # Update password
            password_hash = bcrypt.hash(new_password)

            await conn.execute("""
                UPDATE users
                SET password_hash = $1,
                    reset_token = NULL,
                    reset_expires = NULL
                WHERE id = $2
            """, password_hash, user["id"])

            # Revoke all sessions (security)
            await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1
            """, user["id"])

        # Notify user
        await self.email.send_password_changed_notification(
            user["email"], user["username"]
        )

        return True, "Password updated successfully"

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> Tuple[bool, str]:
        """Change password (when logged in)."""
        if len(new_password) < 8:
            return False, "Password must be at least 8 characters"

        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, username, email, password_hash
                FROM users
                WHERE id = $1
                AND deleted_at IS NULL
            """, user_id)

            if not user:
                return False, "User not found"

            if not bcrypt.verify(current_password, user["password_hash"]):
                return False, "Current password is incorrect"

            # Update password
            password_hash = bcrypt.hash(new_password)

            await conn.execute("""
                UPDATE users SET password_hash = $1 WHERE id = $2
            """, password_hash, user["id"])

        # Notify user
        if user["email"]:
            await self.email.send_password_changed_notification(
                user["email"], user["username"]
            )

        return True, "Password updated successfully"

    # --- Session Management ---

    async def get_sessions(self, user_id: str) -> list[Session]:
        """Get all active sessions for a user."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, device_info, ip_address,
                       created_at, expires_at, last_used_at
                FROM user_sessions
                WHERE user_id = $1
                AND revoked_at IS NULL
                AND expires_at > NOW()
                ORDER BY last_used_at DESC
            """, user_id)

            return [
                Session(
                    id=row["id"],
                    user_id=row["user_id"],
                    device_info=row["device_info"] or {},
                    ip_address=str(row["ip_address"]) if row["ip_address"] else "",
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    last_used_at=row["last_used_at"],
                )
                for row in rows
            ]

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        """Revoke a specific session."""
        async with self.db.acquire() as conn:
            result = await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE id = $1
                AND user_id = $2
                AND revoked_at IS NULL
            """, session_id, user_id)

            return result != "UPDATE 0"

    # --- Account Management ---

    async def update_preferences(
        self,
        user_id: str,
        preferences: dict,
    ) -> bool:
        """Update user preferences."""
        async with self.db.acquire() as conn:
            await conn.execute("""
                UPDATE users
                SET preferences = preferences || $1
                WHERE id = $2
            """, preferences, user_id)

            return True

    async def delete_account(
        self,
        user_id: str,
        password: str,
    ) -> Tuple[bool, str]:
        """
        Soft-delete account.
        Anonymizes data but preserves game history.
        """
        async with self.db.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT id, password_hash
                FROM users
                WHERE id = $1
                AND deleted_at IS NULL
            """, user_id)

            if not user:
                return False, "User not found"

            if not bcrypt.verify(password, user["password_hash"]):
                return False, "Incorrect password"

            # Soft delete - anonymize PII but keep ID for game history
            deleted_username = f"deleted_{user_id[:8]}"

            await conn.execute("""
                UPDATE users
                SET username = $1,
                    email = NULL,
                    password_hash = '',
                    deleted_at = NOW(),
                    preferences = '{}'
                WHERE id = $2
            """, deleted_username, user_id)

            # Revoke all sessions
            await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1
            """, user_id)

            return True, "Account deleted"

    # --- Guest Conversion ---

    async def _convert_guest_stats(
        self,
        conn: asyncpg.Connection,
        guest_id: str,
        user_id: str,
    ) -> None:
        """Transfer guest stats to user account."""
        # Mark guest as converted
        await conn.execute("""
            UPDATE guest_sessions
            SET converted_to_user_id = $1
            WHERE id = $2
        """, user_id, guest_id)

        # Update game records to link to user
        await conn.execute("""
            UPDATE games_v2
            SET player_ids = array_replace(player_ids, $1, $2)
            WHERE $1 = ANY(player_ids)
        """, guest_id, user_id)

    # --- Helpers ---

    def _is_valid_email(self, email: str) -> bool:
        """Basic email validation."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
```

---

## API Endpoints

```python
# server/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    guest_id: Optional[str] = None


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/register")
async def register(
    request: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
):
    user, error = await auth.register(
        request.username,
        request.email,
        request.password,
        request.guest_id,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    return {
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": user.id,
    }


@router.post("/verify-email")
async def verify_email(
    token: str,
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.verify_email(token)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}


@router.post("/resend-verification")
async def resend_verification(
    email: EmailStr,
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.resend_verification(email)
    return {"message": message}


@router.post("/login")
async def login(
    request: LoginRequest,
    req: Request,
    auth: AuthService = Depends(get_auth_service),
):
    device_info = {
        "user_agent": req.headers.get("user-agent", ""),
    }
    ip_address = req.client.host

    token, user, error = await auth.login(
        request.username_or_email,
        request.password,
        device_info,
        ip_address,
    )

    if error:
        raise HTTPException(status_code=401, detail=error)

    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "email_verified": user.email_verified,
        },
    }


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),
    token: str = Depends(get_token),
    auth: AuthService = Depends(get_auth_service),
):
    await auth.logout(token)
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(
    user: User = Depends(get_current_user),
    token: str = Depends(get_token),
    auth: AuthService = Depends(get_auth_service),
):
    count = await auth.logout_all(user.id, except_token=token)
    return {"message": f"Logged out {count} other sessions"}


@router.post("/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.request_password_reset(request.email)
    return {"message": message}


@router.post("/reset-password")
async def reset_password(
    request: PasswordResetConfirm,
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.reset_password(request.token, request.new_password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}


@router.put("/password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.change_password(
        user.id,
        request.current_password,
        request.new_password,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}


@router.get("/sessions")
async def get_sessions(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    sessions = await auth.get_sessions(user.id)
    return {
        "sessions": [
            {
                "id": s.id,
                "device_info": s.device_info,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat(),
                "last_used_at": s.last_used_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    success = await auth.revoke_session(user.id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session revoked"}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "email_verified": user.email_verified,
        "preferences": user.preferences,
    }


@router.put("/preferences")
async def update_preferences(
    preferences: dict,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    await auth.update_preferences(user.id, preferences)
    return {"message": "Preferences updated"}


@router.delete("/account")
async def delete_account(
    password: str,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    success, message = await auth.delete_account(user.id, password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}
```

---

## Frontend Integration

### Login/Register UI

Add to `client/index.html`:

```html
<!-- Auth Modal -->
<div id="auth-modal" class="modal hidden">
    <div class="modal-content">
        <div class="auth-tabs">
            <button id="login-tab" class="tab active">Login</button>
            <button id="register-tab" class="tab">Register</button>
        </div>

        <!-- Login Form -->
        <form id="login-form" class="auth-form">
            <input type="text" id="login-username" placeholder="Username or Email" required>
            <input type="password" id="login-password" placeholder="Password" required>
            <a href="#" id="forgot-password-link">Forgot password?</a>
            <button type="submit" class="btn btn-primary">Login</button>
        </form>

        <!-- Register Form -->
        <form id="register-form" class="auth-form hidden">
            <input type="text" id="register-username" placeholder="Username" required>
            <input type="email" id="register-email" placeholder="Email" required>
            <input type="password" id="register-password" placeholder="Password (8+ characters)" required>
            <button type="submit" class="btn btn-primary">Register</button>
        </form>

        <!-- Guest Option -->
        <div class="guest-option">
            <p>or</p>
            <button id="play-as-guest" class="btn btn-secondary">Play as Guest</button>
        </div>

        <p id="auth-error" class="error hidden"></p>
    </div>
</div>
```

---

## Config Additions

```python
# server/config.py additions

class Config:
    # Email
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "Golf Game <noreply@example.com>")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # Auth
    SESSION_EXPIRY_HOURS: int = int(os.getenv("SESSION_EXPIRY_HOURS", "168"))  # 1 week
    REQUIRE_EMAIL_VERIFICATION: bool = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
```

---

## Acceptance Criteria

1. **Email Service**
   - [ ] Resend integration working
   - [ ] Verification emails send correctly
   - [ ] Password reset emails send correctly
   - [ ] Password changed notifications work
   - [ ] Email delivery logged

2. **Registration**
   - [ ] Can register with username/email/password
   - [ ] Validation enforced (username length, email format, password strength)
   - [ ] Duplicate detection works
   - [ ] Verification email sent
   - [ ] Guest ID can be linked

3. **Email Verification**
   - [ ] Verification link works
   - [ ] Expired links rejected
   - [ ] Can resend verification
   - [ ] Verified flag set correctly

4. **Login/Logout**
   - [ ] Can login with username or email
   - [ ] Wrong credentials rejected
   - [ ] Session token returned
   - [ ] Logout revokes session
   - [ ] Logout all works

5. **Password Reset**
   - [ ] Reset request sends email
   - [ ] Reset link works
   - [ ] Expired links rejected
   - [ ] Password updated correctly
   - [ ] All sessions revoked after reset
   - [ ] Notification email sent

6. **Session Management**
   - [ ] Can list active sessions
   - [ ] Can revoke individual sessions
   - [ ] Session shows device info
   - [ ] Expired sessions cleaned up

7. **Account Management**
   - [ ] Can update preferences
   - [ ] Can change password (with current password)
   - [ ] Can delete account (with password)
   - [ ] Deleted accounts anonymized
   - [ ] Game history preserved

8. **Guest Conversion**
   - [ ] Can play as guest
   - [ ] Guest prompted to register
   - [ ] Stats transfer on conversion
   - [ ] Guest ID linked to user

---

## Implementation Order

1. Set up Resend account and get API key
2. Add email service config
3. Create database migrations
4. Implement EmailService
5. Implement AuthService (registration first)
6. Add API endpoints
7. Implement login/session management
8. Implement password reset flow
9. Add frontend UI
10. Test full flows

---

## Security Notes

- Store only token hashes, not tokens
- Use bcrypt for passwords (work factor 12+)
- Rate limit auth endpoints (see V2-07)
- Verification/reset tokens expire
- Notify on password change
- Soft-delete preserves audit trail
- Don't reveal if email exists (timing attacks)
