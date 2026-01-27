"""
PostgreSQL-backed user store for Golf game authentication.

Manages user accounts, sessions, and guest tracking.
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg

from models.user import User, UserRole, UserSession, GuestSession

logger = logging.getLogger(__name__)


# SQL schema for user store
SCHEMA_SQL = """
-- Users table (V2 auth)
CREATE TABLE IF NOT EXISTS users_v2 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255),
    verification_expires TIMESTAMPTZ,
    reset_token VARCHAR(255),
    reset_expires TIMESTAMPTZ,
    guest_id VARCHAR(50),
    deleted_at TIMESTAMPTZ,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users_v2(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    device_info JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

-- Guest sessions table
CREATE TABLE IF NOT EXISTS guest_sessions (
    id VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    games_played INT DEFAULT 0,
    converted_to_user_id UUID REFERENCES users_v2(id),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 days'
);

-- Email log table
CREATE TABLE IF NOT EXISTS email_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users_v2(id),
    email_type VARCHAR(50) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    resend_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'sent'
);

-- Add admin columns to users_v2 if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'users_v2' AND column_name = 'is_banned') THEN
        ALTER TABLE users_v2 ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'users_v2' AND column_name = 'ban_reason') THEN
        ALTER TABLE users_v2 ADD COLUMN ban_reason TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'users_v2' AND column_name = 'force_password_reset') THEN
        ALTER TABLE users_v2 ADD COLUMN force_password_reset BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'users_v2' AND column_name = 'last_seen_at') THEN
        ALTER TABLE users_v2 ADD COLUMN last_seen_at TIMESTAMPTZ;
    END IF;
END $$;

-- Admin audit log table
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id UUID NOT NULL REFERENCES users_v2(id),
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(100),
    details JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User bans table
CREATE TABLE IF NOT EXISTS user_bans (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users_v2(id),
    banned_by UUID NOT NULL REFERENCES users_v2(id),
    reason TEXT,
    banned_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    unbanned_at TIMESTAMPTZ,
    unbanned_by UUID REFERENCES users_v2(id)
);

-- Invite codes table
CREATE TABLE IF NOT EXISTS invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    created_by UUID NOT NULL REFERENCES users_v2(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    max_uses INT DEFAULT 1,
    use_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

-- Player stats table (extended for V2 leaderboards)
CREATE TABLE IF NOT EXISTS player_stats (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL REFERENCES users_v2(id),
    games_played INT DEFAULT 0,
    games_won INT DEFAULT 0,
    best_score INT,
    worst_score INT,
    total_rounds INT DEFAULT 0,
    avg_score DECIMAL(5,2),
    -- Extended stats
    rounds_won INT DEFAULT 0,
    total_points INT DEFAULT 0,
    knockouts INT DEFAULT 0,
    perfect_rounds INT DEFAULT 0,
    wolfpacks INT DEFAULT 0,
    current_win_streak INT DEFAULT 0,
    best_win_streak INT DEFAULT 0,
    first_game_at TIMESTAMPTZ,
    last_game_at TIMESTAMPTZ,
    games_vs_humans INT DEFAULT 0,
    games_won_vs_humans INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add new columns to existing player_stats if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'rounds_won') THEN
        ALTER TABLE player_stats ADD COLUMN rounds_won INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'total_points') THEN
        ALTER TABLE player_stats ADD COLUMN total_points INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'knockouts') THEN
        ALTER TABLE player_stats ADD COLUMN knockouts INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'perfect_rounds') THEN
        ALTER TABLE player_stats ADD COLUMN perfect_rounds INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'wolfpacks') THEN
        ALTER TABLE player_stats ADD COLUMN wolfpacks INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'current_win_streak') THEN
        ALTER TABLE player_stats ADD COLUMN current_win_streak INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'best_win_streak') THEN
        ALTER TABLE player_stats ADD COLUMN best_win_streak INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'first_game_at') THEN
        ALTER TABLE player_stats ADD COLUMN first_game_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'last_game_at') THEN
        ALTER TABLE player_stats ADD COLUMN last_game_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'games_vs_humans') THEN
        ALTER TABLE player_stats ADD COLUMN games_vs_humans INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'player_stats' AND column_name = 'games_won_vs_humans') THEN
        ALTER TABLE player_stats ADD COLUMN games_won_vs_humans INT DEFAULT 0;
    END IF;
END $$;

-- Stats processing queue (for async stats processing)
CREATE TABLE IF NOT EXISTS stats_queue (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    error_message TEXT
);

-- Achievements definitions
CREATE TABLE IF NOT EXISTS achievements (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    category VARCHAR(50),
    threshold INT,
    sort_order INT DEFAULT 0
);

-- User achievements (earned achievements)
CREATE TABLE IF NOT EXISTS user_achievements (
    user_id UUID REFERENCES users_v2(id),
    achievement_id VARCHAR(50) REFERENCES achievements(id),
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    game_id UUID,
    PRIMARY KEY (user_id, achievement_id)
);

-- Seed achievements if empty
INSERT INTO achievements (id, name, description, icon, category, threshold, sort_order)
SELECT * FROM (VALUES
    ('first_win', 'First Victory', 'Win your first game', '🏆', 'games', 1, 1),
    ('win_10', 'Rising Star', 'Win 10 games', '⭐', 'games', 10, 2),
    ('win_50', 'Veteran', 'Win 50 games', '🎖️', 'games', 50, 3),
    ('win_100', 'Champion', 'Win 100 games', '👑', 'games', 100, 4),
    ('perfect_round', 'Perfect', 'Score 0 or less in a round', '💎', 'rounds', 1, 10),
    ('negative_round', 'Below Zero', 'Score negative in a round', '❄️', 'rounds', 1, 11),
    ('knockout_10', 'Closer', 'Go out first 10 times', '🚪', 'special', 10, 20),
    ('wolfpack', 'Wolfpack', 'Get all 4 Jacks', '🐺', 'special', 1, 21),
    ('streak_5', 'Hot Streak', 'Win 5 games in a row', '🔥', 'special', 5, 30),
    ('streak_10', 'Unstoppable', 'Win 10 games in a row', '⚡', 'special', 10, 31)
) AS v(id, name, description, icon, category, threshold, sort_order)
WHERE NOT EXISTS (SELECT 1 FROM achievements LIMIT 1);

-- System metrics table
CREATE TABLE IF NOT EXISTS system_metrics (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    active_users INT,
    active_games INT,
    events_last_hour INT,
    registrations_today INT,
    games_completed_today INT,
    metrics JSONB DEFAULT '{}'
);

-- Leaderboard materialized view (refreshed periodically)
-- Note: Using DO block to handle case where view already exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'leaderboard_overall') THEN
        EXECUTE '
            CREATE MATERIALIZED VIEW leaderboard_overall AS
            SELECT
                u.id as user_id,
                u.username,
                s.games_played,
                s.games_won,
                ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
                s.rounds_won,
                ROUND(s.total_points::numeric / NULLIF(s.total_rounds, 0), 1) as avg_score,
                s.best_score as best_round_score,
                s.knockouts,
                s.best_win_streak,
                s.last_game_at
            FROM player_stats s
            JOIN users_v2 u ON s.user_id = u.id
            WHERE s.games_played >= 5
            AND u.deleted_at IS NULL
            AND (u.is_banned = false OR u.is_banned IS NULL)
        ';
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users_v2(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_username ON users_v2(username);
CREATE INDEX IF NOT EXISTS idx_users_verification ON users_v2(verification_token) WHERE verification_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_reset ON users_v2(reset_token) WHERE reset_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_guest ON users_v2(guest_id) WHERE guest_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_active ON users_v2(is_active) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_banned ON users_v2(is_banned) WHERE is_banned = TRUE;

CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_last_used ON user_sessions(last_used_at) WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_guests_expires ON guest_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_guests_converted ON guest_sessions(converted_to_user_id) WHERE converted_to_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_email_user ON email_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_type ON email_log(email_type);

CREATE INDEX IF NOT EXISTS idx_audit_admin ON admin_audit_log(admin_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_target ON admin_audit_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_log(created_at);

CREATE INDEX IF NOT EXISTS idx_bans_user ON user_bans(user_id);
CREATE INDEX IF NOT EXISTS idx_bans_active ON user_bans(user_id) WHERE unbanned_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_invites_code ON invite_codes(code);
CREATE INDEX IF NOT EXISTS idx_invites_active ON invite_codes(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_stats_user ON player_stats(user_id);

CREATE INDEX IF NOT EXISTS idx_metrics_time ON system_metrics(recorded_at);

-- Stats queue indexes
CREATE INDEX IF NOT EXISTS idx_stats_queue_pending ON stats_queue(status, created_at)
    WHERE status = 'pending';

-- User achievements indexes
CREATE INDEX IF NOT EXISTS idx_user_achievements_user ON user_achievements(user_id);

-- Leaderboard materialized view indexes (created separately)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'leaderboard_overall') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_leaderboard_overall_user') THEN
            CREATE UNIQUE INDEX idx_leaderboard_overall_user ON leaderboard_overall(user_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_leaderboard_overall_wins') THEN
            CREATE INDEX idx_leaderboard_overall_wins ON leaderboard_overall(games_won DESC);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_leaderboard_overall_rate') THEN
            CREATE INDEX idx_leaderboard_overall_rate ON leaderboard_overall(win_rate DESC);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_leaderboard_overall_score') THEN
            CREATE INDEX idx_leaderboard_overall_score ON leaderboard_overall(avg_score ASC);
        END IF;
    END IF;
END $$;
"""


def hash_token(token: str) -> str:
    """Hash a token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


class UserStore:
    """
    PostgreSQL-backed store for users and sessions.

    Provides CRUD operations for user accounts, sessions, and guests.
    Uses asyncpg for async database access.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize user store with connection pool.

        Args:
            pool: asyncpg connection pool.
        """
        self.pool = pool

    @classmethod
    async def create(cls, postgres_url: str) -> "UserStore":
        """
        Create a UserStore with a new connection pool.

        Args:
            postgres_url: PostgreSQL connection URL.

        Returns:
            Configured UserStore instance.
        """
        pool = await asyncpg.create_pool(postgres_url, min_size=2, max_size=10)
        store = cls(pool)
        await store.initialize_schema()
        return store

    async def initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("User store schema initialized")

    async def close(self) -> None:
        """Close the connection pool."""
        await self.pool.close()

    # -------------------------------------------------------------------------
    # User CRUD
    # -------------------------------------------------------------------------

    async def create_user(
        self,
        username: str,
        password_hash: str,
        email: Optional[str] = None,
        role: UserRole = UserRole.USER,
        guest_id: Optional[str] = None,
        verification_token: Optional[str] = None,
        verification_expires: Optional[datetime] = None,
    ) -> Optional[User]:
        """
        Create a new user account.

        Args:
            username: Unique username.
            password_hash: bcrypt hash of password.
            email: Optional email address.
            role: User role.
            guest_id: Guest session ID if converting.
            verification_token: Email verification token.
            verification_expires: Token expiration time.

        Returns:
            Created User, or None if username/email already exists.
        """
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users_v2 (username, password_hash, email, role, guest_id,
                                          verification_token, verification_expires)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id, username, email, password_hash, role, email_verified,
                              verification_token, verification_expires, reset_token, reset_expires,
                              guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                              is_active, is_banned, ban_reason, force_password_reset
                    """,
                    username,
                    password_hash,
                    email,
                    role.value,
                    guest_id,
                    verification_token,
                    verification_expires,
                )
                return self._row_to_user(row)
            except asyncpg.UniqueViolationError:
                return None

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, role, email_verified,
                       verification_token, verification_expires, reset_token, reset_expires,
                       guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                       is_active, is_banned, ban_reason, force_password_reset
                FROM users_v2
                WHERE id = $1
                """,
                user_id,
            )
            return self._row_to_user(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, role, email_verified,
                       verification_token, verification_expires, reset_token, reset_expires,
                       guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                       is_active, is_banned, ban_reason, force_password_reset
                FROM users_v2
                WHERE LOWER(username) = LOWER($1)
                """,
                username,
            )
            return self._row_to_user(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, role, email_verified,
                       verification_token, verification_expires, reset_token, reset_expires,
                       guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                       is_active, is_banned, ban_reason, force_password_reset
                FROM users_v2
                WHERE LOWER(email) = LOWER($1)
                """,
                email,
            )
            return self._row_to_user(row) if row else None

    async def get_user_by_verification_token(self, token: str) -> Optional[User]:
        """Get user by verification token."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, role, email_verified,
                       verification_token, verification_expires, reset_token, reset_expires,
                       guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                       is_active, is_banned, ban_reason, force_password_reset
                FROM users_v2
                WHERE verification_token = $1
                """,
                token,
            )
            return self._row_to_user(row) if row else None

    async def get_user_by_reset_token(self, token: str) -> Optional[User]:
        """Get user by password reset token."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, role, email_verified,
                       verification_token, verification_expires, reset_token, reset_expires,
                       guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                       is_active, is_banned, ban_reason, force_password_reset
                FROM users_v2
                WHERE reset_token = $1
                """,
                token,
            )
            return self._row_to_user(row) if row else None

    async def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        password_hash: Optional[str] = None,
        role: Optional[UserRole] = None,
        email_verified: Optional[bool] = None,
        verification_token: Optional[str] = None,
        verification_expires: Optional[datetime] = None,
        reset_token: Optional[str] = None,
        reset_expires: Optional[datetime] = None,
        preferences: Optional[dict] = None,
        last_login: Optional[datetime] = None,
        last_seen_at: Optional[datetime] = None,
        is_active: Optional[bool] = None,
        deleted_at: Optional[datetime] = None,
        is_banned: Optional[bool] = None,
        ban_reason: Optional[str] = None,
        force_password_reset: Optional[bool] = None,
        clear_ban_reason: bool = False,
    ) -> Optional[User]:
        """
        Update user fields.

        Only non-None values are updated.
        Use clear_ban_reason=True to explicitly set ban_reason to NULL.

        Returns:
            Updated User, or None if user not found or unique constraint violated.
        """
        updates = []
        params = []
        param_idx = 1

        def add_param(value):
            nonlocal param_idx
            params.append(value)
            idx = param_idx
            param_idx += 1
            return idx

        if username is not None:
            updates.append(f"username = ${add_param(username)}")
        if email is not None:
            updates.append(f"email = ${add_param(email)}")
        if password_hash is not None:
            updates.append(f"password_hash = ${add_param(password_hash)}")
        if role is not None:
            updates.append(f"role = ${add_param(role.value)}")
        if email_verified is not None:
            updates.append(f"email_verified = ${add_param(email_verified)}")
        if verification_token is not None:
            updates.append(f"verification_token = ${add_param(verification_token)}")
        if verification_expires is not None:
            updates.append(f"verification_expires = ${add_param(verification_expires)}")
        if reset_token is not None:
            updates.append(f"reset_token = ${add_param(reset_token)}")
        if reset_expires is not None:
            updates.append(f"reset_expires = ${add_param(reset_expires)}")
        if preferences is not None:
            updates.append(f"preferences = ${add_param(json.dumps(preferences))}")
        if last_login is not None:
            updates.append(f"last_login = ${add_param(last_login)}")
        if last_seen_at is not None:
            updates.append(f"last_seen_at = ${add_param(last_seen_at)}")
        if is_active is not None:
            updates.append(f"is_active = ${add_param(is_active)}")
        if deleted_at is not None:
            updates.append(f"deleted_at = ${add_param(deleted_at)}")
        if is_banned is not None:
            updates.append(f"is_banned = ${add_param(is_banned)}")
        if ban_reason is not None:
            updates.append(f"ban_reason = ${add_param(ban_reason)}")
        elif clear_ban_reason:
            updates.append("ban_reason = NULL")
        if force_password_reset is not None:
            updates.append(f"force_password_reset = ${add_param(force_password_reset)}")

        if not updates:
            return await self.get_user_by_id(user_id)

        params.append(user_id)
        query = f"""
            UPDATE users_v2
            SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, username, email, password_hash, role, email_verified,
                      verification_token, verification_expires, reset_token, reset_expires,
                      guest_id, deleted_at, preferences, created_at, last_login, last_seen_at,
                      is_active, is_banned, ban_reason, force_password_reset
        """

        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(query, *params)
                return self._row_to_user(row) if row else None
            except asyncpg.UniqueViolationError:
                return None

    async def clear_verification_token(self, user_id: str) -> bool:
        """Clear verification token after successful verification."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE users_v2
                SET verification_token = NULL, verification_expires = NULL, email_verified = TRUE
                WHERE id = $1
                """,
                user_id,
            )
            return result == "UPDATE 1"

    async def clear_reset_token(self, user_id: str) -> bool:
        """Clear reset token after successful password reset."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE users_v2
                SET reset_token = NULL, reset_expires = NULL
                WHERE id = $1
                """,
                user_id,
            )
            return result == "UPDATE 1"

    async def list_users(self, include_inactive: bool = False) -> list[User]:
        """List all users."""
        async with self.pool.acquire() as conn:
            if include_inactive:
                rows = await conn.fetch(
                    """
                    SELECT id, username, email, password_hash, role, email_verified,
                           verification_token, verification_expires, reset_token, reset_expires,
                           guest_id, deleted_at, preferences, created_at, last_login, is_active
                    FROM users_v2
                    ORDER BY created_at DESC
                    """
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, username, email, password_hash, role, email_verified,
                           verification_token, verification_expires, reset_token, reset_expires,
                           guest_id, deleted_at, preferences, created_at, last_login, is_active
                    FROM users_v2
                    WHERE is_active = TRUE AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """
                )
            return [self._row_to_user(row) for row in rows]

    # -------------------------------------------------------------------------
    # Session CRUD
    # -------------------------------------------------------------------------

    async def create_session(
        self,
        user_id: str,
        token: str,
        expires_at: datetime,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> UserSession:
        """
        Create a new user session.

        Args:
            user_id: User ID.
            token: Raw session token (will be hashed).
            expires_at: Session expiration time.
            device_info: Device/browser info.
            ip_address: Client IP address.

        Returns:
            Created UserSession.
        """
        token_hash = hash_token(token)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_sessions (user_id, token_hash, expires_at, device_info, ip_address)
                VALUES ($1, $2, $3, $4, $5::inet)
                RETURNING id, user_id, token_hash, device_info, ip_address,
                          created_at, expires_at, last_used_at, revoked_at
                """,
                user_id,
                token_hash,
                expires_at,
                json.dumps(device_info or {}),
                ip_address,
            )
            return self._row_to_session(row)

    async def get_session_by_token(self, token: str) -> Optional[UserSession]:
        """Get session by raw token (will be hashed for lookup)."""
        token_hash = hash_token(token)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, token_hash, device_info, ip_address,
                       created_at, expires_at, last_used_at, revoked_at
                FROM user_sessions
                WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > NOW()
                """,
                token_hash,
            )
            return self._row_to_session(row) if row else None

    async def get_sessions_for_user(self, user_id: str) -> list[UserSession]:
        """Get all active sessions for a user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, token_hash, device_info, ip_address,
                       created_at, expires_at, last_used_at, revoked_at
                FROM user_sessions
                WHERE user_id = $1 AND revoked_at IS NULL AND expires_at > NOW()
                ORDER BY last_used_at DESC
                """,
                user_id,
            )
            return [self._row_to_session(row) for row in rows]

    async def update_session_last_used(self, session_id: str) -> bool:
        """Update session last_used_at timestamp."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_sessions SET last_used_at = NOW() WHERE id = $1",
                session_id,
            )
            return result == "UPDATE 1"

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke a session by ID."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE id = $1",
                session_id,
            )
            return result == "UPDATE 1"

    async def revoke_session_by_token(self, token: str) -> bool:
        """Revoke a session by raw token."""
        token_hash = hash_token(token)
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE token_hash = $1",
                token_hash,
            )
            return result == "UPDATE 1"

    async def revoke_all_sessions(self, user_id: str, except_token: Optional[str] = None) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User ID.
            except_token: Optional token to exclude from revocation.

        Returns:
            Number of sessions revoked.
        """
        async with self.pool.acquire() as conn:
            if except_token:
                except_hash = hash_token(except_token)
                result = await conn.execute(
                    """
                    UPDATE user_sessions
                    SET revoked_at = NOW()
                    WHERE user_id = $1 AND revoked_at IS NULL AND token_hash != $2
                    """,
                    user_id,
                    except_hash,
                )
            else:
                result = await conn.execute(
                    "UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
                    user_id,
                )
            # Parse "UPDATE N" result
            return int(result.split()[1])

    async def cleanup_expired_sessions(self) -> int:
        """Delete expired sessions. Returns number deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_sessions WHERE expires_at < NOW()"
            )
            return int(result.split()[1])

    # -------------------------------------------------------------------------
    # Guest Session CRUD
    # -------------------------------------------------------------------------

    async def create_guest_session(
        self,
        guest_id: str,
        display_name: Optional[str] = None,
        expires_in_days: int = 30,
    ) -> GuestSession:
        """Create a new guest session."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO guest_sessions (id, display_name, expires_at)
                VALUES ($1, $2, $3)
                RETURNING id, display_name, created_at, last_seen_at, games_played,
                          converted_to_user_id, expires_at
                """,
                guest_id,
                display_name,
                expires_at,
            )
            return self._row_to_guest(row)

    async def get_guest_session(self, guest_id: str) -> Optional[GuestSession]:
        """Get guest session by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, display_name, created_at, last_seen_at, games_played,
                       converted_to_user_id, expires_at
                FROM guest_sessions
                WHERE id = $1
                """,
                guest_id,
            )
            return self._row_to_guest(row) if row else None

    async def update_guest_last_seen(self, guest_id: str) -> bool:
        """Update guest last_seen_at timestamp."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE guest_sessions SET last_seen_at = NOW() WHERE id = $1",
                guest_id,
            )
            return result == "UPDATE 1"

    async def increment_guest_games(self, guest_id: str) -> bool:
        """Increment guest games_played counter."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE guest_sessions SET games_played = games_played + 1 WHERE id = $1",
                guest_id,
            )
            return result == "UPDATE 1"

    async def mark_guest_converted(self, guest_id: str, user_id: str) -> bool:
        """Mark guest session as converted to user account."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE guest_sessions SET converted_to_user_id = $2 WHERE id = $1",
                guest_id,
                user_id,
            )
            return result == "UPDATE 1"

    async def cleanup_expired_guests(self) -> int:
        """Delete expired guest sessions. Returns number deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM guest_sessions WHERE expires_at < NOW() AND converted_to_user_id IS NULL"
            )
            return int(result.split()[1])

    # -------------------------------------------------------------------------
    # Email Log
    # -------------------------------------------------------------------------

    async def log_email(
        self,
        user_id: Optional[str],
        email_type: str,
        recipient: str,
        resend_id: Optional[str] = None,
        status: str = "sent",
    ) -> int:
        """
        Log an email send.

        Returns:
            Log entry ID.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO email_log (user_id, email_type, recipient, resend_id, status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                user_id,
                email_type,
                recipient,
                resend_id,
                status,
            )
            return row["id"]

    async def update_email_status(self, log_id: int, status: str) -> bool:
        """Update email log status."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE email_log SET status = $2 WHERE id = $1",
                log_id,
                status,
            )
            return result == "UPDATE 1"

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _row_to_user(self, row: asyncpg.Record) -> User:
        """Convert database row to User."""
        return User(
            id=str(row["id"]),
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=UserRole(row["role"]),
            email_verified=row["email_verified"],
            verification_token=row["verification_token"],
            verification_expires=row["verification_expires"].replace(tzinfo=timezone.utc) if row["verification_expires"] else None,
            reset_token=row["reset_token"],
            reset_expires=row["reset_expires"].replace(tzinfo=timezone.utc) if row["reset_expires"] else None,
            guest_id=row["guest_id"],
            deleted_at=row["deleted_at"].replace(tzinfo=timezone.utc) if row["deleted_at"] else None,
            preferences=json.loads(row["preferences"]) if row["preferences"] else {},
            created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else datetime.now(timezone.utc),
            last_login=row["last_login"].replace(tzinfo=timezone.utc) if row["last_login"] else None,
            last_seen_at=row["last_seen_at"].replace(tzinfo=timezone.utc) if row.get("last_seen_at") else None,
            is_active=row["is_active"],
            is_banned=row.get("is_banned", False) or False,
            ban_reason=row.get("ban_reason"),
            force_password_reset=row.get("force_password_reset", False) or False,
        )

    def _row_to_session(self, row: asyncpg.Record) -> UserSession:
        """Convert database row to UserSession."""
        return UserSession(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            token_hash=row["token_hash"],
            device_info=json.loads(row["device_info"]) if row["device_info"] else {},
            ip_address=str(row["ip_address"]) if row["ip_address"] else None,
            created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else datetime.now(timezone.utc),
            expires_at=row["expires_at"].replace(tzinfo=timezone.utc) if row["expires_at"] else datetime.now(timezone.utc),
            last_used_at=row["last_used_at"].replace(tzinfo=timezone.utc) if row["last_used_at"] else datetime.now(timezone.utc),
            revoked_at=row["revoked_at"].replace(tzinfo=timezone.utc) if row["revoked_at"] else None,
        )

    def _row_to_guest(self, row: asyncpg.Record) -> GuestSession:
        """Convert database row to GuestSession."""
        return GuestSession(
            id=row["id"],
            display_name=row["display_name"],
            created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else datetime.now(timezone.utc),
            last_seen_at=row["last_seen_at"].replace(tzinfo=timezone.utc) if row["last_seen_at"] else datetime.now(timezone.utc),
            games_played=row["games_played"],
            converted_to_user_id=str(row["converted_to_user_id"]) if row["converted_to_user_id"] else None,
            expires_at=row["expires_at"].replace(tzinfo=timezone.utc) if row["expires_at"] else datetime.now(timezone.utc),
        )


# Global user store instance
_user_store: Optional[UserStore] = None


async def get_user_store(postgres_url: str) -> UserStore:
    """
    Get or create the global user store instance.

    Args:
        postgres_url: PostgreSQL connection URL.

    Returns:
        UserStore instance.
    """
    global _user_store
    if _user_store is None:
        _user_store = await UserStore.create(postgres_url)
    return _user_store


async def close_user_store() -> None:
    """Close the global user store connection pool."""
    global _user_store
    if _user_store is not None:
        await _user_store.close()
        _user_store = None
