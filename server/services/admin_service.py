"""
Admin service for Golf game.

Provides admin capabilities: user management, game moderation,
system monitoring, audit logging, and invite code management.
"""

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import asyncpg

from models.user import User, UserRole
from stores.user_store import UserStore

logger = logging.getLogger(__name__)


@dataclass
class UserDetails:
    """Extended user info for admin view."""
    id: str
    username: str
    email: Optional[str]
    role: str
    email_verified: bool
    is_banned: bool
    ban_reason: Optional[str]
    force_password_reset: bool
    created_at: datetime
    last_login: Optional[datetime]
    last_seen_at: Optional[datetime]
    is_active: bool
    games_played: int
    games_won: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "email_verified": self.email_verified,
            "is_banned": self.is_banned,
            "ban_reason": self.ban_reason,
            "force_password_reset": self.force_password_reset,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "is_active": self.is_active,
            "games_played": self.games_played,
            "games_won": self.games_won,
        }


@dataclass
class AuditEntry:
    """Admin audit log entry."""
    id: int
    admin_username: str
    admin_user_id: str
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    details: dict
    ip_address: Optional[str]
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "admin_username": self.admin_username,
            "admin_user_id": self.admin_user_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class SystemStats:
    """System statistics snapshot."""
    active_users_now: int
    active_games_now: int
    total_users: int
    total_games_completed: int
    registrations_today: int
    registrations_week: int
    games_today: int
    events_last_hour: int
    top_players: List[dict]

    def to_dict(self) -> dict:
        return {
            "active_users_now": self.active_users_now,
            "active_games_now": self.active_games_now,
            "total_users": self.total_users,
            "total_games_completed": self.total_games_completed,
            "registrations_today": self.registrations_today,
            "registrations_week": self.registrations_week,
            "games_today": self.games_today,
            "events_last_hour": self.events_last_hour,
            "top_players": self.top_players,
        }


@dataclass
class InviteCode:
    """Invite code details."""
    code: str
    created_by: str
    created_by_username: str
    created_at: datetime
    expires_at: datetime
    max_uses: int
    use_count: int
    is_active: bool

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "created_by": self.created_by,
            "created_by_username": self.created_by_username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "max_uses": self.max_uses,
            "use_count": self.use_count,
            "is_active": self.is_active,
            "remaining_uses": max(0, self.max_uses - self.use_count),
        }


class AdminService:
    """
    Admin operations and moderation service.

    Provides methods for:
    - Audit logging
    - User management (search, ban, unban, force password reset)
    - Game moderation (view active games, end stuck games)
    - System statistics
    - Invite code management
    - User impersonation (read-only)
    """

    def __init__(self, pool: asyncpg.Pool, user_store: UserStore, state_cache=None):
        """
        Initialize admin service.

        Args:
            pool: asyncpg connection pool.
            user_store: User persistence store.
            state_cache: Optional Redis state cache for game operations.
        """
        self.pool = pool
        self.user_store = user_store
        self.state_cache = state_cache

    # -------------------------------------------------------------------------
    # Audit Logging
    # -------------------------------------------------------------------------

    async def audit(
        self,
        admin_id: str,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        """
        Log an admin action.

        Args:
            admin_id: Admin user ID.
            action: Action name (e.g., "ban_user", "end_game").
            target_type: Type of target (e.g., "user", "game", "invite_code").
            target_id: ID of the target.
            details: Additional details as JSON.
            ip_address: Admin's IP address.

        Returns:
            Audit log entry ID.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO admin_audit_log
                (admin_user_id, action, target_type, target_id, details, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6::inet)
                RETURNING id
                """,
                admin_id,
                action,
                target_type,
                target_id,
                json.dumps(details or {}),
                ip_address,
            )
            return row["id"]

    async def get_audit_log(
        self,
        limit: int = 100,
        offset: int = 0,
        admin_id: Optional[str] = None,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
    ) -> List[AuditEntry]:
        """
        Get audit log entries with optional filtering.

        Args:
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.
            admin_id: Filter by admin user ID.
            action: Filter by action name.
            target_type: Filter by target type.

        Returns:
            List of audit entries.
        """
        async with self.pool.acquire() as conn:
            query = """
                SELECT a.id, u.username as admin_username, a.admin_user_id,
                       a.action, a.target_type, a.target_id, a.details,
                       a.ip_address, a.created_at
                FROM admin_audit_log a
                JOIN users_v2 u ON a.admin_user_id = u.id
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
                    admin_user_id=str(row["admin_user_id"]),
                    action=row["action"],
                    target_type=row["target_type"],
                    target_id=row["target_id"],
                    details=json.loads(row["details"]) if row["details"] else {},
                    ip_address=str(row["ip_address"]) if row["ip_address"] else None,
                    created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else None,
                )
                for row in rows
            ]

    # -------------------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------------------

    async def search_users(
        self,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
        include_banned: bool = True,
        include_deleted: bool = False,
    ) -> List[UserDetails]:
        """
        Search users by username or email.

        Args:
            query: Search query (matches username or email).
            limit: Maximum number of results.
            offset: Number of results to skip.
            include_banned: Include banned users.
            include_deleted: Include soft-deleted users.

        Returns:
            List of user details.
        """
        async with self.pool.acquire() as conn:
            sql = """
                SELECT u.id, u.username, u.email, u.role,
                       u.email_verified, u.is_banned, u.ban_reason,
                       u.force_password_reset, u.created_at, u.last_login,
                       u.last_seen_at, u.is_active,
                       COALESCE(s.games_played, 0) as games_played,
                       COALESCE(s.games_won, 0) as games_won
                FROM users_v2 u
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
                sql += " AND (u.is_banned = false OR u.is_banned IS NULL)"

            if not include_deleted:
                sql += " AND u.deleted_at IS NULL"

            sql += f" ORDER BY u.created_at DESC LIMIT ${param_num} OFFSET ${param_num + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(sql, *params)

            return [
                UserDetails(
                    id=str(row["id"]),
                    username=row["username"],
                    email=row["email"],
                    role=row["role"],
                    email_verified=row["email_verified"],
                    is_banned=row["is_banned"] or False,
                    ban_reason=row["ban_reason"],
                    force_password_reset=row["force_password_reset"] or False,
                    created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else None,
                    last_login=row["last_login"].replace(tzinfo=timezone.utc) if row["last_login"] else None,
                    last_seen_at=row["last_seen_at"].replace(tzinfo=timezone.utc) if row["last_seen_at"] else None,
                    is_active=row["is_active"],
                    games_played=row["games_played"] or 0,
                    games_won=row["games_won"] or 0,
                )
                for row in rows
            ]

    async def get_user(self, user_id: str) -> Optional[UserDetails]:
        """
        Get detailed user info by ID.

        Args:
            user_id: User UUID.

        Returns:
            User details, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.id, u.username, u.email, u.role,
                       u.email_verified, u.is_banned, u.ban_reason,
                       u.force_password_reset, u.created_at, u.last_login,
                       u.last_seen_at, u.is_active,
                       COALESCE(s.games_played, 0) as games_played,
                       COALESCE(s.games_won, 0) as games_won
                FROM users_v2 u
                LEFT JOIN player_stats s ON u.id = s.user_id
                WHERE u.id = $1
                """,
                user_id,
            )

            if not row:
                return None

            return UserDetails(
                id=str(row["id"]),
                username=row["username"],
                email=row["email"],
                role=row["role"],
                email_verified=row["email_verified"],
                is_banned=row["is_banned"] or False,
                ban_reason=row["ban_reason"],
                force_password_reset=row["force_password_reset"] or False,
                created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else None,
                last_login=row["last_login"].replace(tzinfo=timezone.utc) if row["last_login"] else None,
                last_seen_at=row["last_seen_at"].replace(tzinfo=timezone.utc) if row["last_seen_at"] else None,
                is_active=row["is_active"],
                games_played=row["games_played"] or 0,
                games_won=row["games_won"] or 0,
            )

    async def ban_user(
        self,
        admin_id: str,
        user_id: str,
        reason: str,
        duration_days: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Ban a user.

        Args:
            admin_id: Admin performing the ban.
            user_id: User to ban.
            reason: Reason for ban.
            duration_days: Optional ban duration (None = permanent).
            ip_address: Admin's IP address for audit.

        Returns:
            True if ban was successful.
        """
        expires_at = None
        if duration_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

        async with self.pool.acquire() as conn:
            # Check user exists and isn't admin
            user = await conn.fetchrow(
                "SELECT role FROM users_v2 WHERE id = $1",
                user_id,
            )

            if not user:
                return False

            if user["role"] == "admin":
                logger.warning(f"Admin {admin_id} attempted to ban admin {user_id}")
                return False  # Can't ban admins

            # Create ban record
            await conn.execute(
                """
                INSERT INTO user_bans (user_id, banned_by, reason, expires_at)
                VALUES ($1, $2, $3, $4)
                """,
                user_id,
                admin_id,
                reason,
                expires_at,
            )

            # Update user
            await conn.execute(
                """
                UPDATE users_v2
                SET is_banned = true, ban_reason = $1
                WHERE id = $2
                """,
                reason,
                user_id,
            )

            # Revoke all sessions
            await conn.execute(
                """
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1 AND revoked_at IS NULL
                """,
                user_id,
            )

        # Kick from any active games (if state cache available)
        if self.state_cache:
            await self._kick_from_games(user_id)

        # Audit log
        await self.audit(
            admin_id,
            "ban_user",
            "user",
            user_id,
            {"reason": reason, "duration_days": duration_days},
            ip_address,
        )

        logger.info(f"Admin {admin_id} banned user {user_id}: {reason}")
        return True

    async def unban_user(
        self,
        admin_id: str,
        user_id: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Unban a user.

        Args:
            admin_id: Admin performing the unban.
            user_id: User to unban.
            ip_address: Admin's IP address for audit.

        Returns:
            True if unban was successful.
        """
        async with self.pool.acquire() as conn:
            # Update ban record
            await conn.execute(
                """
                UPDATE user_bans
                SET unbanned_at = NOW(), unbanned_by = $1
                WHERE user_id = $2 AND unbanned_at IS NULL
                """,
                admin_id,
                user_id,
            )

            # Update user
            result = await conn.execute(
                """
                UPDATE users_v2
                SET is_banned = false, ban_reason = NULL
                WHERE id = $1
                """,
                user_id,
            )

            if result == "UPDATE 0":
                return False

        await self.audit(
            admin_id,
            "unban_user",
            "user",
            user_id,
            ip_address=ip_address,
        )

        logger.info(f"Admin {admin_id} unbanned user {user_id}")
        return True

    async def force_password_reset(
        self,
        admin_id: str,
        user_id: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Force user to reset password on next login.

        Args:
            admin_id: Admin performing the action.
            user_id: User to force reset.
            ip_address: Admin's IP address for audit.

        Returns:
            True if successful.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE users_v2
                SET force_password_reset = true
                WHERE id = $1
                """,
                user_id,
            )

            if result == "UPDATE 0":
                return False

            # Revoke all sessions to force re-login
            await conn.execute(
                """
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE user_id = $1 AND revoked_at IS NULL
                """,
                user_id,
            )

        await self.audit(
            admin_id,
            "force_password_reset",
            "user",
            user_id,
            ip_address=ip_address,
        )

        logger.info(f"Admin {admin_id} forced password reset for user {user_id}")
        return True

    async def change_user_role(
        self,
        admin_id: str,
        user_id: str,
        new_role: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Change user role.

        Args:
            admin_id: Admin performing the action.
            user_id: User to modify.
            new_role: New role ("user" or "admin").
            ip_address: Admin's IP address for audit.

        Returns:
            True if successful.
        """
        if new_role not in ("user", "admin"):
            return False

        async with self.pool.acquire() as conn:
            # Get old role for audit
            old = await conn.fetchrow(
                "SELECT role FROM users_v2 WHERE id = $1",
                user_id,
            )

            if not old:
                return False

            await conn.execute(
                "UPDATE users_v2 SET role = $1 WHERE id = $2",
                new_role,
                user_id,
            )

        await self.audit(
            admin_id,
            "change_role",
            "user",
            user_id,
            {"old_role": old["role"], "new_role": new_role},
            ip_address,
        )

        logger.info(f"Admin {admin_id} changed role for user {user_id}: {old['role']} -> {new_role}")
        return True

    async def get_user_ban_history(self, user_id: str) -> List[dict]:
        """
        Get ban history for a user.

        Args:
            user_id: User UUID.

        Returns:
            List of ban records.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.id, b.reason, b.banned_at, b.expires_at,
                       b.unbanned_at, u1.username as banned_by_username,
                       u2.username as unbanned_by_username
                FROM user_bans b
                JOIN users_v2 u1 ON b.banned_by = u1.id
                LEFT JOIN users_v2 u2 ON b.unbanned_by = u2.id
                WHERE b.user_id = $1
                ORDER BY b.banned_at DESC
                """,
                user_id,
            )

            return [
                {
                    "id": row["id"],
                    "reason": row["reason"],
                    "banned_at": row["banned_at"].isoformat() if row["banned_at"] else None,
                    "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                    "unbanned_at": row["unbanned_at"].isoformat() if row["unbanned_at"] else None,
                    "banned_by": row["banned_by_username"],
                    "unbanned_by": row["unbanned_by_username"],
                }
                for row in rows
            ]

    # -------------------------------------------------------------------------
    # User Impersonation (Read-Only)
    # -------------------------------------------------------------------------

    async def impersonate_user(
        self,
        admin_id: str,
        user_id: str,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """
        Get user object for read-only impersonation.

        This allows an admin to view the app as another user would see it,
        without being able to make changes. The returned User object should
        only be used for read operations.

        Args:
            admin_id: Admin performing impersonation.
            user_id: User to impersonate.
            ip_address: Admin's IP address for audit.

        Returns:
            User object for impersonation, or None if user not found.
        """
        user = await self.user_store.get_user_by_id(user_id)

        if user:
            await self.audit(
                admin_id,
                "impersonate_user",
                "user",
                user_id,
                ip_address=ip_address,
            )
            logger.info(f"Admin {admin_id} started impersonating user {user_id}")

        return user

    # -------------------------------------------------------------------------
    # Game Moderation
    # -------------------------------------------------------------------------

    async def get_active_games(self) -> List[dict]:
        """
        Get all active games.

        Returns:
            List of active game info dicts.
        """
        if not self.state_cache:
            # Fall back to database
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, room_code, status, created_at, started_at,
                           num_players, num_rounds, host_id
                    FROM games_v2
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    """
                )
                return [
                    {
                        "game_id": str(row["id"]),
                        "room_code": row["room_code"],
                        "status": row["status"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                        "player_count": row["num_players"] or 0,
                        "num_rounds": row["num_rounds"] or 0,
                        "host_id": row["host_id"],
                    }
                    for row in rows
                ]

        # Use Redis state cache for live data
        rooms = await self.state_cache.get_active_rooms()
        games = []

        for room_code in rooms:
            room = await self.state_cache.get_room(room_code)
            if room:
                game_id = room.get("game_id")
                state = None
                if game_id:
                    state = await self.state_cache.get_game_state(game_id)

                players = await self.state_cache.get_room_players(room_code)

                games.append({
                    "room_code": room_code,
                    "game_id": game_id,
                    "status": room.get("status"),
                    "created_at": room.get("created_at"),
                    "player_count": len(players),
                    "phase": state.get("phase") if state else None,
                    "current_round": state.get("current_round") if state else None,
                })

        return games

    async def get_game_details(
        self,
        admin_id: str,
        game_id: str,
        ip_address: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Get full game state (admin view).

        Args:
            admin_id: Admin requesting the view.
            game_id: Game UUID.
            ip_address: Admin's IP address for audit.

        Returns:
            Full game state dict, or None if not found.
        """
        state = None

        if self.state_cache:
            state = await self.state_cache.get_game_state(game_id)

        if not state:
            # Try database
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, room_code, status, created_at, started_at,
                           completed_at, num_players, num_rounds, options,
                           winner_id, host_id, player_ids
                    FROM games_v2
                    WHERE id = $1
                    """,
                    game_id,
                )
                if row:
                    state = {
                        "game_id": str(row["id"]),
                        "room_code": row["room_code"],
                        "status": row["status"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                        "num_players": row["num_players"],
                        "num_rounds": row["num_rounds"],
                        "options": json.loads(row["options"]) if row["options"] else {},
                        "winner_id": row["winner_id"],
                        "host_id": row["host_id"],
                        "player_ids": row["player_ids"] or [],
                    }

        if state:
            await self.audit(
                admin_id,
                "view_game",
                "game",
                game_id,
                ip_address=ip_address,
            )

        return state

    async def end_game(
        self,
        admin_id: str,
        game_id: str,
        reason: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Force-end a stuck game.

        Args:
            admin_id: Admin ending the game.
            game_id: Game UUID.
            reason: Reason for ending.
            ip_address: Admin's IP address for audit.

        Returns:
            True if game was ended.
        """
        room_code = None

        if self.state_cache:
            state = await self.state_cache.get_game_state(game_id)
            if state:
                room_code = state.get("room_code")
                # Mark game as ended in cache
                state["phase"] = "game_over"
                state["admin_ended"] = True
                state["admin_end_reason"] = reason
                await self.state_cache.save_game_state(game_id, state)

        # Update database
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE games_v2
                SET status = 'abandoned', completed_at = NOW()
                WHERE id = $1 AND status = 'active'
                """,
                game_id,
            )

            if result == "UPDATE 0" and not room_code:
                return False

            # Get room code if we didn't have it
            if not room_code:
                row = await conn.fetchrow(
                    "SELECT room_code FROM games_v2 WHERE id = $1",
                    game_id,
                )
                if row:
                    room_code = row["room_code"]

        await self.audit(
            admin_id,
            "end_game",
            "game",
            game_id,
            {"reason": reason, "room_code": room_code},
            ip_address,
        )

        logger.info(f"Admin {admin_id} ended game {game_id}: {reason}")
        return True

    async def _kick_from_games(self, user_id: str) -> None:
        """
        Kick user from any active games.

        Args:
            user_id: User to kick.
        """
        if not self.state_cache:
            return

        player_room = await self.state_cache.get_player_room(user_id)
        if player_room:
            await self.state_cache.remove_player_from_room(player_room, user_id)
            logger.info(f"Kicked user {user_id} from room {player_room}")

    # -------------------------------------------------------------------------
    # System Stats
    # -------------------------------------------------------------------------

    async def get_system_stats(self) -> SystemStats:
        """
        Get current system statistics.

        Returns:
            SystemStats snapshot.
        """
        # Active games from Redis
        active_games = 0
        if self.state_cache:
            active_rooms = await self.state_cache.get_active_rooms()
            active_games = len(active_rooms)

        async with self.pool.acquire() as conn:
            # Total users
            total_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users_v2 WHERE deleted_at IS NULL"
            )

            # Total completed games
            total_games = await conn.fetchval(
                "SELECT COUNT(*) FROM games_v2 WHERE status = 'completed'"
            )

            # Registrations today
            reg_today = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users_v2
                WHERE created_at >= CURRENT_DATE
                AND deleted_at IS NULL
                """
            )

            # Registrations this week
            reg_week = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users_v2
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                AND deleted_at IS NULL
                """
            )

            # Games today
            games_today = await conn.fetchval(
                "SELECT COUNT(*) FROM games_v2 WHERE created_at >= CURRENT_DATE"
            )

            # Events last hour
            events_hour = await conn.fetchval(
                """
                SELECT COUNT(*) FROM events
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                """
            ) or 0

            # Top players (by wins)
            top_players = await conn.fetch(
                """
                SELECT u.username, s.games_won, s.games_played
                FROM player_stats s
                JOIN users_v2 u ON s.user_id = u.id
                WHERE s.games_played >= 3
                ORDER BY s.games_won DESC
                LIMIT 10
                """
            )

            # Active users (sessions used in last hour)
            active_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM user_sessions
                WHERE last_used_at >= NOW() - INTERVAL '1 hour'
                AND revoked_at IS NULL
                """
            )

        return SystemStats(
            active_users_now=active_users or 0,
            active_games_now=active_games,
            total_users=total_users or 0,
            total_games_completed=total_games or 0,
            registrations_today=reg_today or 0,
            registrations_week=reg_week or 0,
            games_today=games_today or 0,
            events_last_hour=events_hour,
            top_players=[
                {
                    "username": p["username"],
                    "games_won": p["games_won"],
                    "games_played": p["games_played"],
                }
                for p in top_players
            ],
        )

    # -------------------------------------------------------------------------
    # Invite Codes
    # -------------------------------------------------------------------------

    async def create_invite_code(
        self,
        admin_id: str,
        max_uses: int = 1,
        expires_days: int = 7,
        ip_address: Optional[str] = None,
    ) -> str:
        """
        Create a new invite code.

        Args:
            admin_id: Admin creating the code.
            max_uses: Maximum number of uses.
            expires_days: Days until expiration.
            ip_address: Admin's IP address for audit.

        Returns:
            The generated invite code.
        """
        code = secrets.token_urlsafe(6).upper()[:8]
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO invite_codes (code, created_by, expires_at, max_uses)
                VALUES ($1, $2, $3, $4)
                """,
                code,
                admin_id,
                expires_at,
                max_uses,
            )

        await self.audit(
            admin_id,
            "create_invite",
            "invite_code",
            code,
            {"max_uses": max_uses, "expires_days": expires_days},
            ip_address,
        )

        logger.info(f"Admin {admin_id} created invite code {code}")
        return code

    async def get_invite_codes(self, include_expired: bool = False) -> List[InviteCode]:
        """
        Get all invite codes.

        Args:
            include_expired: Include expired/inactive codes.

        Returns:
            List of invite codes.
        """
        async with self.pool.acquire() as conn:
            query = """
                SELECT c.code, c.created_by, c.created_at, c.expires_at,
                       c.max_uses, c.use_count, c.is_active,
                       u.username as created_by_username
                FROM invite_codes c
                JOIN users_v2 u ON c.created_by = u.id
            """
            if not include_expired:
                query += " WHERE c.expires_at > NOW() AND c.is_active = true"

            query += " ORDER BY c.created_at DESC"

            rows = await conn.fetch(query)

            return [
                InviteCode(
                    code=row["code"],
                    created_by=str(row["created_by"]),
                    created_by_username=row["created_by_username"],
                    created_at=row["created_at"].replace(tzinfo=timezone.utc) if row["created_at"] else None,
                    expires_at=row["expires_at"].replace(tzinfo=timezone.utc) if row["expires_at"] else None,
                    max_uses=row["max_uses"],
                    use_count=row["use_count"],
                    is_active=row["is_active"],
                )
                for row in rows
            ]

    async def revoke_invite_code(
        self,
        admin_id: str,
        code: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Revoke an invite code.

        Args:
            admin_id: Admin revoking the code.
            code: Code to revoke.
            ip_address: Admin's IP address for audit.

        Returns:
            True if code was revoked.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE invite_codes SET is_active = false WHERE code = $1",
                code,
            )

            if result == "UPDATE 0":
                return False

        await self.audit(
            admin_id,
            "revoke_invite",
            "invite_code",
            code,
            ip_address=ip_address,
        )

        logger.info(f"Admin {admin_id} revoked invite code {code}")
        return True

    async def validate_invite_code(self, code: str) -> bool:
        """
        Check if an invite code is valid.

        Args:
            code: Code to validate.

        Returns:
            True if code is valid and has remaining uses.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT max_uses, use_count, expires_at, is_active
                FROM invite_codes
                WHERE code = $1
                """,
                code,
            )

            if not row:
                return False

            if not row["is_active"]:
                return False

            if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
                return False

            if row["use_count"] >= row["max_uses"]:
                return False

            return True

    async def use_invite_code(self, code: str) -> bool:
        """
        Use an invite code (increment use count).

        Args:
            code: Code to use.

        Returns:
            True if code was successfully used.
        """
        if not await self.validate_invite_code(code):
            return False

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE invite_codes
                SET use_count = use_count + 1
                WHERE code = $1 AND is_active = true
                AND use_count < max_uses
                AND expires_at > NOW()
                """,
                code,
            )

            return result != "UPDATE 0"


# Global admin service instance
_admin_service: Optional[AdminService] = None


async def get_admin_service(
    pool: asyncpg.Pool,
    user_store: UserStore,
    state_cache=None,
) -> AdminService:
    """
    Get or create the global admin service instance.

    Args:
        pool: asyncpg connection pool.
        user_store: User persistence store.
        state_cache: Optional Redis state cache.

    Returns:
        AdminService instance.
    """
    global _admin_service
    if _admin_service is None:
        _admin_service = AdminService(pool, user_store, state_cache)
    return _admin_service


def close_admin_service() -> None:
    """Close the global admin service."""
    global _admin_service
    _admin_service = None
