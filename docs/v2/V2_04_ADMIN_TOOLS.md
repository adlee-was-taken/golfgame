# V2-04: Admin Tools & Moderation

## Overview

This document covers admin capabilities: user management, game moderation, system monitoring, and audit logging.

**Dependencies:** V2-03 (User Accounts)
**Dependents:** None (end feature)

---

## Goals

1. Admin dashboard with system overview
2. User management (search, view, ban, unban)
3. Force password reset capability
4. Game moderation (view any game, end stuck games)
5. System statistics and monitoring
6. Invite code management
7. Audit logging for admin actions

---

## Current State

Basic admin exists:
- Admin role in users table
- Some admin endpoints in `main.py`
- Invite code creation

**Missing:**
- Admin dashboard UI
- User search/management
- Game moderation
- System stats
- Audit logging

---

## Admin Capabilities Matrix

| Capability | Description | Risk Level |
|------------|-------------|------------|
| View users | List, search, view user details | Low |
| Ban user | Prevent login, kick from games | Medium |
| Unban user | Restore access | Low |
| Force password reset | Invalidate password, require reset | Medium |
| Impersonate user | View as user (read-only) | High |
| View any game | See any game state | Low |
| End stuck game | Force-end a game | Medium |
| View system stats | Metrics and monitoring | Low |
| Manage invite codes | Create, revoke codes | Low |
| View audit log | See admin actions | Low |

---

## Database Schema

```sql
-- migrations/versions/003_admin_tools.sql

-- Audit log for admin actions
CREATE TABLE admin_audit_log (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(50),  -- 'user', 'game', 'invite_code', etc.
    target_id VARCHAR(100),
    details JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User bans
CREATE TABLE user_bans (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    banned_by UUID NOT NULL REFERENCES users(id),
    reason TEXT,
    banned_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- NULL = permanent
    unbanned_at TIMESTAMPTZ,
    unbanned_by UUID REFERENCES users(id)
);

-- Extend users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS force_password_reset BOOLEAN DEFAULT false;

-- System metrics snapshots (for historical data)
CREATE TABLE system_metrics (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    active_users INT,
    active_games INT,
    events_last_hour INT,
    registrations_today INT,
    games_completed_today INT,
    metrics JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_audit_admin ON admin_audit_log(admin_user_id);
CREATE INDEX idx_audit_target ON admin_audit_log(target_type, target_id);
CREATE INDEX idx_audit_created ON admin_audit_log(created_at);
CREATE INDEX idx_bans_user ON user_bans(user_id);
CREATE INDEX idx_bans_active ON user_bans(user_id) WHERE unbanned_at IS NULL;
CREATE INDEX idx_metrics_time ON system_metrics(recorded_at);
```

---

## Admin Service

```python
# server/services/admin_service.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
import asyncpg

from services.auth_service import User


@dataclass
class UserDetails:
    id: str
    username: str
    email: Optional[str]
    role: str
    email_verified: bool
    is_banned: bool
    ban_reason: Optional[str]
    force_password_reset: bool
    created_at: datetime
    last_seen_at: Optional[datetime]
    games_played: int
    games_won: int


@dataclass
class AuditEntry:
    id: int
    admin_username: str
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    details: dict
    ip_address: str
    created_at: datetime


@dataclass
class SystemStats:
    active_users_now: int
    active_games_now: int
    total_users: int
    total_games_completed: int
    registrations_today: int
    registrations_week: int
    games_today: int
    events_last_hour: int
    top_players: List[dict]


class AdminService:
    """Admin operations and moderation."""

    def __init__(self, db_pool: asyncpg.Pool, state_cache):
        self.db = db_pool
        self.state_cache = state_cache

    # --- Audit Logging ---

    async def _audit(
        self,
        admin_id: str,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: dict = None,
        ip_address: str = None,
    ) -> None:
        """Log an admin action."""
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO admin_audit_log
                (admin_user_id, action, target_type, target_id, details, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, admin_id, action, target_type, target_id,
                details or {}, ip_address)

    async def get_audit_log(
        self,
        limit: int = 100,
        offset: int = 0,
        admin_id: Optional[str] = None,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
    ) -> List[AuditEntry]:
        """Get audit log entries with filtering."""
        async with self.db.acquire() as conn:
            query = """
                SELECT a.id, u.username as admin_username, a.action,
                       a.target_type, a.target_id, a.details,
                       a.ip_address, a.created_at
                FROM admin_audit_log a
                JOIN users u ON a.admin_user_id = u.id
                WHERE 1=1
            """
            params = []
            param_num = 1

            if admin_id:
                query += f" AND a.admin_user_id = ${param_num}"
                params.append(admin_id)
                param_num += 1

            if action:
                query += f" AND a.action = ${param_num}"
                params.append(action)
                param_num += 1

            if target_type:
                query += f" AND a.target_type = ${param_num}"
                params.append(target_type)
                param_num += 1

            query += f" ORDER BY a.created_at DESC LIMIT ${param_num} OFFSET ${param_num + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)

            return [
                AuditEntry(
                    id=row["id"],
                    admin_username=row["admin_username"],
                    action=row["action"],
                    target_type=row["target_type"],
                    target_id=row["target_id"],
                    details=row["details"] or {},
                    ip_address=str(row["ip_address"]) if row["ip_address"] else "",
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # --- User Management ---

    async def search_users(
        self,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
        include_banned: bool = True,
        include_deleted: bool = False,
    ) -> List[UserDetails]:
        """Search users by username or email."""
        async with self.db.acquire() as conn:
            sql = """
                SELECT u.id, u.username, u.email, u.role,
                       u.email_verified, u.is_banned, u.ban_reason,
                       u.force_password_reset, u.created_at, u.last_seen_at,
                       COALESCE(s.games_played, 0) as games_played,
                       COALESCE(s.games_won, 0) as games_won
                FROM users u
                LEFT JOIN player_stats s ON u.id = s.user_id
                WHERE 1=1
            """
            params = []
            param_num = 1

            if query:
                sql += f" AND (u.username ILIKE ${param_num} OR u.email ILIKE ${param_num})"
                params.append(f"%{query}%")
                param_num += 1

            if not include_banned:
                sql += " AND u.is_banned = false"

            if not include_deleted:
                sql += " AND u.deleted_at IS NULL"

            sql += f" ORDER BY u.created_at DESC LIMIT ${param_num} OFFSET ${param_num + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(sql, *params)

            return [
                UserDetails(
                    id=row["id"],
                    username=row["username"],
                    email=row["email"],
                    role=row["role"],
                    email_verified=row["email_verified"],
                    is_banned=row["is_banned"],
                    ban_reason=row["ban_reason"],
                    force_password_reset=row["force_password_reset"],
                    created_at=row["created_at"],
                    last_seen_at=row["last_seen_at"],
                    games_played=row["games_played"],
                    games_won=row["games_won"],
                )
                for row in rows
            ]

    async def get_user(self, user_id: str) -> Optional[UserDetails]:
        """Get detailed user info."""
        users = await self.search_users()  # Simplified; would filter by ID
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT u.id, u.username, u.email, u.role,
                       u.email_verified, u.is_banned, u.ban_reason,
                       u.force_password_reset, u.created_at, u.last_seen_at,
                       COALESCE(s.games_played, 0) as games_played,
                       COALESCE(s.games_won, 0) as games_won
                FROM users u
                LEFT JOIN player_stats s ON u.id = s.user_id
                WHERE u.id = $1
            """, user_id)

            if not row:
                return None

            return UserDetails(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                role=row["role"],
                email_verified=row["email_verified"],
                is_banned=row["is_banned"],
                ban_reason=row["ban_reason"],
                force_password_reset=row["force_password_reset"],
                created_at=row["created_at"],
                last_seen_at=row["last_seen_at"],
                games_played=row["games_played"],
                games_won=row["games_won"],
            )

    async def ban_user(
        self,
        admin_id: str,
        user_id: str,
        reason: str,
        duration_days: Optional[int] = None,
        ip_address: str = None,
    ) -> bool:
        """Ban a user."""
        expires_at = None
        if duration_days:
            expires_at = datetime.utcnow() + timedelta(days=duration_days)

        async with self.db.acquire() as conn:
            # Check user exists and isn't admin
            user = await conn.fetchrow("""
                SELECT role FROM users WHERE id = $1
            """, user_id)

            if not user:
                return False

            if user["role"] == "admin":
                return False  # Can't ban admins

            # Create ban record
            await conn.execute("""
                INSERT INTO user_bans (user_id, banned_by, reason, expires_at)
                VALUES ($1, $2, $3, $4)
            """, user_id, admin_id, reason, expires_at)

            # Update user
            await conn.execute("""
                UPDATE users
                SET is_banned = true, ban_reason = $1
                WHERE id = $2
            """, reason, user_id)

            # Revoke all sessions
            await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1
            """, user_id)

        # Kick from any active games
        await self._kick_from_games(user_id)

        # Audit
        await self._audit(
            admin_id, "ban_user", "user", user_id,
            {"reason": reason, "duration_days": duration_days},
            ip_address,
        )

        return True

    async def unban_user(
        self,
        admin_id: str,
        user_id: str,
        ip_address: str = None,
    ) -> bool:
        """Unban a user."""
        async with self.db.acquire() as conn:
            # Update ban record
            await conn.execute("""
                UPDATE user_bans
                SET unbanned_at = NOW(), unbanned_by = $1
                WHERE user_id = $2
                AND unbanned_at IS NULL
            """, admin_id, user_id)

            # Update user
            result = await conn.execute("""
                UPDATE users
                SET is_banned = false, ban_reason = NULL
                WHERE id = $1
            """, user_id)

            if result == "UPDATE 0":
                return False

        await self._audit(
            admin_id, "unban_user", "user", user_id,
            ip_address=ip_address,
        )

        return True

    async def force_password_reset(
        self,
        admin_id: str,
        user_id: str,
        ip_address: str = None,
    ) -> bool:
        """Force user to reset password on next login."""
        async with self.db.acquire() as conn:
            result = await conn.execute("""
                UPDATE users
                SET force_password_reset = true,
                    password_hash = ''
                WHERE id = $1
            """, user_id)

            if result == "UPDATE 0":
                return False

            # Revoke all sessions
            await conn.execute("""
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1
            """, user_id)

        await self._audit(
            admin_id, "force_password_reset", "user", user_id,
            ip_address=ip_address,
        )

        return True

    async def change_user_role(
        self,
        admin_id: str,
        user_id: str,
        new_role: str,
        ip_address: str = None,
    ) -> bool:
        """Change user role (user/admin)."""
        if new_role not in ("user", "admin"):
            return False

        async with self.db.acquire() as conn:
            # Get old role for audit
            old = await conn.fetchrow("""
                SELECT role FROM users WHERE id = $1
            """, user_id)

            if not old:
                return False

            await conn.execute("""
                UPDATE users SET role = $1 WHERE id = $2
            """, new_role, user_id)

        await self._audit(
            admin_id, "change_role", "user", user_id,
            {"old_role": old["role"], "new_role": new_role},
            ip_address,
        )

        return True

    # --- Game Moderation ---

    async def get_active_games(self) -> List[dict]:
        """Get all active games."""
        rooms = await self.state_cache.get_active_rooms()
        games = []

        for room_code in rooms:
            room = await self.state_cache.get_room(room_code)
            if room:
                game_id = room.get("game_id")
                state = None
                if game_id:
                    state = await self.state_cache.get_game_state(game_id)

                games.append({
                    "room_code": room_code,
                    "game_id": game_id,
                    "status": room.get("status"),
                    "created_at": room.get("created_at"),
                    "player_count": len(await self.state_cache.get_room_players(room_code)),
                    "phase": state.get("phase") if state else None,
                    "current_round": state.get("current_round") if state else None,
                })

        return games

    async def get_game_details(
        self,
        admin_id: str,
        game_id: str,
        ip_address: str = None,
    ) -> Optional[dict]:
        """Get full game state (admin view)."""
        state = await self.state_cache.get_game_state(game_id)

        if state:
            await self._audit(
                admin_id, "view_game", "game", game_id,
                ip_address=ip_address,
            )

        return state

    async def end_game(
        self,
        admin_id: str,
        game_id: str,
        reason: str,
        ip_address: str = None,
    ) -> bool:
        """Force-end a stuck game."""
        state = await self.state_cache.get_game_state(game_id)
        if not state:
            return False

        room_code = state.get("room_code")

        # Mark game as ended
        state["phase"] = "game_over"
        state["admin_ended"] = True
        state["admin_end_reason"] = reason
        await self.state_cache.save_game_state(game_id, state)

        # Update games table
        async with self.db.acquire() as conn:
            await conn.execute("""
                UPDATE games_v2
                SET status = 'abandoned',
                    completed_at = NOW()
                WHERE id = $1
            """, game_id)

        # Notify players via pub/sub
        # (Implementation depends on pub/sub setup)

        await self._audit(
            admin_id, "end_game", "game", game_id,
            {"reason": reason, "room_code": room_code},
            ip_address,
        )

        return True

    async def _kick_from_games(self, user_id: str) -> None:
        """Kick user from any active games."""
        player_room = await self.state_cache.get_player_room(user_id)
        if player_room:
            await self.state_cache.remove_player_from_room(player_room, user_id)
            # Additional game-specific kick logic

    # --- System Stats ---

    async def get_system_stats(self) -> SystemStats:
        """Get current system statistics."""
        # Active counts from Redis
        active_rooms = await self.state_cache.get_active_rooms()
        active_games = len([r for r in active_rooms])  # Could filter by status

        async with self.db.acquire() as conn:
            # Total users
            total_users = await conn.fetchval("""
                SELECT COUNT(*) FROM users WHERE deleted_at IS NULL
            """)

            # Total completed games
            total_games = await conn.fetchval("""
                SELECT COUNT(*) FROM games_v2 WHERE status = 'completed'
            """)

            # Registrations today
            reg_today = await conn.fetchval("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= CURRENT_DATE
                AND deleted_at IS NULL
            """)

            # Registrations this week
            reg_week = await conn.fetchval("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                AND deleted_at IS NULL
            """)

            # Games today
            games_today = await conn.fetchval("""
                SELECT COUNT(*) FROM games_v2
                WHERE created_at >= CURRENT_DATE
            """)

            # Events last hour
            events_hour = await conn.fetchval("""
                SELECT COUNT(*) FROM events
                WHERE created_at >= NOW() - INTERVAL '1 hour'
            """)

            # Top players (by wins)
            top_players = await conn.fetch("""
                SELECT u.username, s.games_won, s.games_played
                FROM player_stats s
                JOIN users u ON s.user_id = u.id
                WHERE s.games_played >= 5
                ORDER BY s.games_won DESC
                LIMIT 10
            """)

            # Active users (sessions used in last hour)
            active_users = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM user_sessions
                WHERE last_used_at >= NOW() - INTERVAL '1 hour'
                AND revoked_at IS NULL
            """)

        return SystemStats(
            active_users_now=active_users or 0,
            active_games_now=active_games,
            total_users=total_users or 0,
            total_games_completed=total_games or 0,
            registrations_today=reg_today or 0,
            registrations_week=reg_week or 0,
            games_today=games_today or 0,
            events_last_hour=events_hour or 0,
            top_players=[
                {
                    "username": p["username"],
                    "games_won": p["games_won"],
                    "games_played": p["games_played"],
                }
                for p in top_players
            ],
        )

    # --- Invite Codes ---

    async def create_invite_code(
        self,
        admin_id: str,
        max_uses: int = 1,
        expires_days: int = 7,
        ip_address: str = None,
    ) -> str:
        """Create a new invite code."""
        import secrets
        code = secrets.token_urlsafe(8).upper()[:8]
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO invite_codes
                (code, created_by, expires_at, max_uses)
                VALUES ($1, $2, $3, $4)
            """, code, admin_id, expires_at, max_uses)

        await self._audit(
            admin_id, "create_invite", "invite_code", code,
            {"max_uses": max_uses, "expires_days": expires_days},
            ip_address,
        )

        return code

    async def get_invite_codes(self, include_expired: bool = False) -> List[dict]:
        """Get all invite codes."""
        async with self.db.acquire() as conn:
            query = """
                SELECT c.code, c.created_at, c.expires_at,
                       c.max_uses, c.use_count, c.is_active,
                       u.username as created_by
                FROM invite_codes c
                JOIN users u ON c.created_by = u.id
            """
            if not include_expired:
                query += " WHERE c.expires_at > NOW() AND c.is_active = true"

            query += " ORDER BY c.created_at DESC"

            rows = await conn.fetch(query)

            return [
                {
                    "code": row["code"],
                    "created_at": row["created_at"].isoformat(),
                    "expires_at": row["expires_at"].isoformat(),
                    "max_uses": row["max_uses"],
                    "use_count": row["use_count"],
                    "is_active": row["is_active"],
                    "created_by": row["created_by"],
                }
                for row in rows
            ]

    async def revoke_invite_code(
        self,
        admin_id: str,
        code: str,
        ip_address: str = None,
    ) -> bool:
        """Revoke an invite code."""
        async with self.db.acquire() as conn:
            result = await conn.execute("""
                UPDATE invite_codes
                SET is_active = false
                WHERE code = $1
            """, code)

            if result == "UPDATE 0":
                return False

        await self._audit(
            admin_id, "revoke_invite", "invite_code", code,
            ip_address=ip_address,
        )

        return True
```

---

## API Endpoints

```python
# server/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# --- User Management ---

@router.get("/users")
async def list_users(
    query: str = "",
    limit: int = 50,
    offset: int = 0,
    include_banned: bool = True,
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    users = await service.search_users(query, limit, offset, include_banned)
    return {"users": [u.__dict__ for u in users]}


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.__dict__


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    reason: str,
    duration_days: Optional[int] = None,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.ban_user(
        admin.id, user_id, reason, duration_days, request.client.host
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot ban user")
    return {"message": "User banned"}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.unban_user(admin.id, user_id, request.client.host)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot unban user")
    return {"message": "User unbanned"}


@router.post("/users/{user_id}/force-password-reset")
async def force_password_reset(
    user_id: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.force_password_reset(
        admin.id, user_id, request.client.host
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot force password reset")
    return {"message": "Password reset required for user"}


@router.put("/users/{user_id}/role")
async def change_role(
    user_id: str,
    role: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.change_user_role(
        admin.id, user_id, role, request.client.host
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot change role")
    return {"message": f"Role changed to {role}"}


# --- Game Moderation ---

@router.get("/games")
async def list_games(
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    games = await service.get_active_games()
    return {"games": games}


@router.get("/games/{game_id}")
async def get_game(
    game_id: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    game = await service.get_game_details(
        admin.id, game_id, request.client.host
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/games/{game_id}/end")
async def end_game(
    game_id: str,
    reason: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.end_game(
        admin.id, game_id, reason, request.client.host
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot end game")
    return {"message": "Game ended"}


# --- System Stats ---

@router.get("/stats")
async def get_stats(
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    stats = await service.get_system_stats()
    return stats.__dict__


# --- Audit Log ---

@router.get("/audit")
async def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    entries = await service.get_audit_log(limit, offset, action=action, target_type=target_type)
    return {"entries": [e.__dict__ for e in entries]}


# --- Invite Codes ---

@router.post("/invites")
async def create_invite(
    max_uses: int = 1,
    expires_days: int = 7,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    code = await service.create_invite_code(
        admin.id, max_uses, expires_days, request.client.host
    )
    return {"code": code}


@router.get("/invites")
async def list_invites(
    include_expired: bool = False,
    admin: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    codes = await service.get_invite_codes(include_expired)
    return {"codes": codes}


@router.delete("/invites/{code}")
async def revoke_invite(
    code: str,
    admin: User = Depends(require_admin),
    request: Request = None,
    service: AdminService = Depends(get_admin_service),
):
    success = await service.revoke_invite_code(admin.id, code, request.client.host)
    if not success:
        raise HTTPException(status_code=404, detail="Invite code not found")
    return {"message": "Invite revoked"}
```

---

## Admin Dashboard UI

```html
<!-- client/admin.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Golf Admin</title>
    <link rel="stylesheet" href="admin.css">
</head>
<body>
    <nav class="admin-nav">
        <h1>Golf Admin</h1>
        <div class="nav-links">
            <a href="#dashboard" class="active">Dashboard</a>
            <a href="#users">Users</a>
            <a href="#games">Games</a>
            <a href="#invites">Invites</a>
            <a href="#audit">Audit Log</a>
        </div>
        <button id="logout-btn">Logout</button>
    </nav>

    <main class="admin-content">
        <!-- Dashboard -->
        <section id="dashboard" class="panel">
            <h2>System Overview</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <span class="stat-value" id="active-users">-</span>
                    <span class="stat-label">Active Users</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value" id="active-games">-</span>
                    <span class="stat-label">Active Games</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value" id="total-users">-</span>
                    <span class="stat-label">Total Users</span>
                </div>
                <div class="stat-card">
                    <span class="stat-value" id="games-today">-</span>
                    <span class="stat-label">Games Today</span>
                </div>
            </div>

            <h3>Top Players</h3>
            <table id="top-players">
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Wins</th>
                        <th>Games</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </section>

        <!-- Users -->
        <section id="users" class="panel hidden">
            <h2>User Management</h2>
            <div class="search-bar">
                <input type="text" id="user-search" placeholder="Search by username or email...">
                <button id="search-btn">Search</button>
            </div>
            <table id="users-table">
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </section>

        <!-- Games -->
        <section id="games" class="panel hidden">
            <h2>Active Games</h2>
            <table id="games-table">
                <thead>
                    <tr>
                        <th>Room</th>
                        <th>Players</th>
                        <th>Phase</th>
                        <th>Round</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </section>

        <!-- Invites -->
        <section id="invites" class="panel hidden">
            <h2>Invite Codes</h2>
            <div class="create-invite">
                <input type="number" id="invite-uses" value="1" min="1">
                <input type="number" id="invite-days" value="7" min="1">
                <button id="create-invite-btn">Create Invite</button>
            </div>
            <table id="invites-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Uses</th>
                        <th>Expires</th>
                        <th>Created By</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </section>

        <!-- Audit Log -->
        <section id="audit" class="panel hidden">
            <h2>Audit Log</h2>
            <table id="audit-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Admin</th>
                        <th>Action</th>
                        <th>Target</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </section>
    </main>

    <script src="admin.js"></script>
</body>
</html>
```

---

## Acceptance Criteria

1. **User Management**
   - [ ] Can search users by username/email
   - [ ] Can view user details
   - [ ] Can ban users (with reason, optional duration)
   - [ ] Can unban users
   - [ ] Can force password reset
   - [ ] Can change user roles
   - [ ] Cannot ban other admins

2. **Game Moderation**
   - [ ] Can list active games
   - [ ] Can view any game state
   - [ ] Can end stuck games
   - [ ] Players notified when game ended
   - [ ] Ended games marked as abandoned

3. **System Stats**
   - [ ] Shows active users count
   - [ ] Shows active games count
   - [ ] Shows total users
   - [ ] Shows registrations today/week
   - [ ] Shows games today
   - [ ] Shows top players

4. **Invite Codes**
   - [ ] Can create invite codes
   - [ ] Can set max uses and expiry
   - [ ] Can list all codes
   - [ ] Can revoke codes

5. **Audit Logging**
   - [ ] All admin actions logged
   - [ ] Log shows admin, action, target, timestamp
   - [ ] Can filter audit log
   - [ ] IP address captured

6. **Admin Dashboard UI**
   - [ ] Dashboard shows overview stats
   - [ ] Can navigate between sections
   - [ ] Actions work correctly
   - [ ] Responsive design

---

## Implementation Order

1. Create database migrations
2. Implement AdminService (audit logging first)
3. Add user management methods
4. Add game moderation methods
5. Add system stats
6. Create API endpoints
7. Build admin dashboard UI
8. Test all flows
9. Security review

---

## Security Notes

- All admin actions are audited
- Cannot ban other admins
- Cannot delete your own admin account
- IP addresses logged for forensics
- Admin dashboard requires separate auth check
- Consider 2FA for admin accounts (future)
