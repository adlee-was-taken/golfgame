"""
Authentication and user management for Golf game.

Features:
- User accounts stored in SQLite
- Admin accounts can manage other users
- Invite codes (room codes) allow new user registration
- Session-based authentication via tokens
"""

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from config import config


class UserRole(Enum):
    """User roles for access control."""
    USER = "user"
    ADMIN = "admin"


@dataclass
class User:
    """User account."""
    id: str
    username: str
    email: Optional[str]
    password_hash: str
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool
    invited_by: Optional[str]  # Username of who invited them

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active,
            "invited_by": self.invited_by,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data


@dataclass
class Session:
    """User session."""
    token: str
    user_id: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


@dataclass
class InviteCode:
    """Invite code for user registration."""
    code: str
    created_by: str  # User ID who created the invite
    created_at: datetime
    expires_at: Optional[datetime]
    max_uses: int
    use_count: int
    is_active: bool

    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        if self.max_uses > 0 and self.use_count >= self.max_uses:
            return False
        return True


class AuthManager:
    """Manages user authentication and authorization."""

    def __init__(self, db_path: str = "games.db"):
        self.db_path = Path(db_path)
        self._init_db()
        self._ensure_admin()

    def _init_db(self):
        """Initialize auth database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Users table
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    invited_by TEXT
                );

                -- Sessions table
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );

                -- Invite codes table
                CREATE TABLE IF NOT EXISTS invite_codes (
                    code TEXT PRIMARY KEY,
                    created_by TEXT REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    max_uses INTEGER DEFAULT 1,
                    use_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_invite_codes_active ON invite_codes(is_active);
            """)

    def _ensure_admin(self):
        """Ensure at least one admin account exists (without password - must be set on first login)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = ?",
                (UserRole.ADMIN.value,)
            )
            admin_count = cursor.fetchone()[0]

            if admin_count == 0:
                # Check if admin emails are configured
                if config.ADMIN_EMAILS:
                    # Create admin accounts for configured emails (no password yet)
                    for email in config.ADMIN_EMAILS:
                        username = email.split("@")[0]
                        self._create_user_without_password(
                            username=username,
                            email=email,
                            role=UserRole.ADMIN,
                        )
                        print(f"Created admin account: {username} - password must be set on first login")
                else:
                    # Create default admin if no admins exist (no password yet)
                    self._create_user_without_password(
                        username="admin",
                        role=UserRole.ADMIN,
                    )
                    print("Created default admin account - password must be set on first login")
                    print("Set ADMIN_EMAILS in .env to configure admin accounts.")

    def _create_user_without_password(
        self,
        username: str,
        email: Optional[str] = None,
        role: UserRole = UserRole.USER,
    ) -> Optional[str]:
        """Create a user without a password (for first-time setup)."""
        user_id = secrets.token_hex(16)
        # Empty password_hash indicates password needs to be set
        password_hash = ""

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, role)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, username, email, password_hash, role.value),
                )
            return user_id
        except sqlite3.IntegrityError:
            return None

    def needs_password_setup(self, username: str) -> bool:
        """Check if user needs to set up their password (first login)."""
        user = self.get_user_by_username(username)
        if not user:
            return False
        return user.password_hash == ""

    def setup_password(self, username: str, new_password: str) -> Optional[User]:
        """Set password for first-time setup. Only works if password is not yet set."""
        user = self.get_user_by_username(username)
        if not user:
            return None
        if user.password_hash != "":
            return None  # Password already set

        password_hash = self._hash_password(new_password)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, last_login = ? WHERE id = ?",
                (password_hash, datetime.now(), user.id)
            )

        return self.get_user_by_id(user.id)

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password using SHA-256 with salt."""
        salt = secrets.token_hex(16)
        hash_input = f"{salt}:{password}".encode()
        password_hash = hashlib.sha256(hash_input).hexdigest()
        return f"{salt}:{password_hash}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            salt, hash_value = stored_hash.split(":")
            hash_input = f"{salt}:{password}".encode()
            computed_hash = hashlib.sha256(hash_input).hexdigest()
            return secrets.compare_digest(computed_hash, hash_value)
        except ValueError:
            return False

    def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: UserRole = UserRole.USER,
        invited_by: Optional[str] = None,
    ) -> Optional[User]:
        """Create a new user account."""
        user_id = secrets.token_hex(16)
        password_hash = self._hash_password(password)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, role, invited_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, email, password_hash, role.value, invited_by),
                )
            return self.get_user_by_id(user_id)
        except sqlite3.IntegrityError:
            return None  # Username or email already exists

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_user(row)
        return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_user(row)
        return None

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Convert database row to User object."""
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=UserRole(row["role"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            last_login=datetime.fromisoformat(row["last_login"]) if row["last_login"] else None,
            is_active=bool(row["is_active"]),
            invited_by=row["invited_by"],
        )

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        user = self.get_user_by_username(username)
        if not user:
            return None
        if not user.is_active:
            return None
        if not self._verify_password(password, user.password_hash):
            return None

        # Update last login
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now(), user.id)
            )

        return user

    def create_session(self, user: User, duration_hours: int = 24) -> Session:
        """Create a new session for a user."""
        token = secrets.token_urlsafe(32)
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=duration_hours)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user.id, created_at, expires_at)
            )

        return Session(
            token=token,
            user_id=user.id,
            created_at=created_at,
            expires_at=expires_at,
        )

    def get_session(self, token: str) -> Optional[Session]:
        """Get session by token."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE token = ?",
                (token,)
            )
            row = cursor.fetchone()
            if row:
                session = Session(
                    token=row["token"],
                    user_id=row["user_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]),
                )
                if not session.is_expired():
                    return session
                # Clean up expired session
                self.invalidate_session(token)
        return None

    def get_user_from_session(self, token: str) -> Optional[User]:
        """Get user from session token."""
        session = self.get_session(token)
        if session:
            return self.get_user_by_id(session.user_id)
        return None

    def invalidate_session(self, token: str):
        """Invalidate a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def invalidate_user_sessions(self, user_id: str):
        """Invalidate all sessions for a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    # =========================================================================
    # Invite Codes
    # =========================================================================

    def create_invite_code(
        self,
        created_by: str,
        max_uses: int = 1,
        expires_in_days: Optional[int] = 7,
    ) -> InviteCode:
        """Create a new invite code."""
        code = secrets.token_urlsafe(8).upper()[:8]  # 8 character code
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=expires_in_days) if expires_in_days else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO invite_codes (code, created_by, created_at, expires_at, max_uses)
                VALUES (?, ?, ?, ?, ?)
                """,
                (code, created_by, created_at, expires_at, max_uses)
            )

        return InviteCode(
            code=code,
            created_by=created_by,
            created_at=created_at,
            expires_at=expires_at,
            max_uses=max_uses,
            use_count=0,
            is_active=True,
        )

    def get_invite_code(self, code: str) -> Optional[InviteCode]:
        """Get invite code by code string."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM invite_codes WHERE code = ?",
                (code.upper(),)
            )
            row = cursor.fetchone()
            if row:
                return InviteCode(
                    code=row["code"],
                    created_by=row["created_by"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                    max_uses=row["max_uses"],
                    use_count=row["use_count"],
                    is_active=bool(row["is_active"]),
                )
        return None

    def use_invite_code(self, code: str) -> bool:
        """Mark an invite code as used. Returns False if invalid."""
        invite = self.get_invite_code(code)
        if not invite or not invite.is_valid():
            return False

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE invite_codes SET use_count = use_count + 1 WHERE code = ?",
                (code.upper(),)
            )
        return True

    def validate_room_code_as_invite(self, room_code: str) -> bool:
        """
        Check if a room code is valid for registration.
        Room codes from active games act as invite codes.
        """
        # First check if it's an explicit invite code
        invite = self.get_invite_code(room_code)
        if invite and invite.is_valid():
            return True

        # Check if it's an active room code (from room manager)
        # This will be checked by the caller since we don't have room_manager here
        return False

    # =========================================================================
    # Admin Functions
    # =========================================================================

    def list_users(self, include_inactive: bool = False) -> list[User]:
        """List all users (admin function)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if include_inactive:
                cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")
            else:
                cursor = conn.execute(
                    "SELECT * FROM users WHERE is_active = 1 ORDER BY created_at DESC"
                )
            return [self._row_to_user(row) for row in cursor.fetchall()]

    def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[User]:
        """Update user details (admin function)."""
        updates = []
        params = []

        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if role is not None:
            updates.append("role = ?")
            params.append(role.value)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)

        if not updates:
            return self.get_user_by_id(user_id)

        params.append(user_id)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    params
                )
            return self.get_user_by_id(user_id)
        except sqlite3.IntegrityError:
            return None

    def change_password(self, user_id: str, new_password: str) -> bool:
        """Change user password."""
        password_hash = self._hash_password(new_password)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )
            return cursor.rowcount > 0

    def delete_user(self, user_id: str) -> bool:
        """Delete a user (admin function). Actually just deactivates."""
        # Invalidate all sessions first
        self.invalidate_user_sessions(user_id)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE users SET is_active = 0 WHERE id = ?",
                (user_id,)
            )
            return cursor.rowcount > 0

    def list_invite_codes(self, created_by: Optional[str] = None) -> list[InviteCode]:
        """List invite codes (admin function)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if created_by:
                cursor = conn.execute(
                    "SELECT * FROM invite_codes WHERE created_by = ? ORDER BY created_at DESC",
                    (created_by,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM invite_codes ORDER BY created_at DESC"
                )
            return [
                InviteCode(
                    code=row["code"],
                    created_by=row["created_by"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                    max_uses=row["max_uses"],
                    use_count=row["use_count"],
                    is_active=bool(row["is_active"]),
                )
                for row in cursor.fetchall()
            ]

    def deactivate_invite_code(self, code: str) -> bool:
        """Deactivate an invite code (admin function)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE invite_codes SET is_active = 0 WHERE code = ?",
                (code.upper(),)
            )
            return cursor.rowcount > 0

    def cleanup_expired_sessions(self):
        """Remove expired sessions from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (datetime.now(),)
            )


# Global auth manager instance (lazy initialization)
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get or create the global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
