"""
Admin API router for Golf game V2.

Provides endpoints for admin operations: user management, game moderation,
system statistics, invite codes, and audit logging.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from models.user import User
from services.admin_service import AdminService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# Request/Response Models
# =============================================================================


class BanUserRequest(BaseModel):
    """Ban user request."""
    reason: str
    duration_days: Optional[int] = None


class ChangeRoleRequest(BaseModel):
    """Change user role request."""
    role: str


class CreateInviteRequest(BaseModel):
    """Create invite code request."""
    max_uses: int = 1
    expires_days: int = 7


class EndGameRequest(BaseModel):
    """End game request."""
    reason: str


# =============================================================================
# Dependencies
# =============================================================================

# These will be set by main.py during startup
_admin_service: Optional[AdminService] = None


def set_admin_service(service: AdminService) -> None:
    """Set the admin service instance (called from main.py)."""
    global _admin_service
    _admin_service = service


def get_admin_service_dep() -> AdminService:
    """Dependency to get admin service."""
    if _admin_service is None:
        raise HTTPException(status_code=503, detail="Admin service not initialized")
    return _admin_service


# Import the auth dependency from the auth router
from routers.auth import require_admin_v2, get_client_ip


# =============================================================================
# User Management Endpoints
# =============================================================================


@router.get("/users")
async def list_users(
    query: str = "",
    limit: int = 50,
    offset: int = 0,
    include_banned: bool = True,
    include_deleted: bool = False,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Search and list users.

    Args:
        query: Search by username or email.
        limit: Maximum results to return.
        offset: Results to skip.
        include_banned: Include banned users.
        include_deleted: Include soft-deleted users.
    """
    users = await service.search_users(
        query=query,
        limit=limit,
        offset=offset,
        include_banned=include_banned,
        include_deleted=include_deleted,
    )
    return {"users": [u.to_dict() for u in users]}


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """Get detailed user information."""
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


@router.get("/users/{user_id}/ban-history")
async def get_user_ban_history(
    user_id: str,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """Get ban history for a user."""
    history = await service.get_user_ban_history(user_id)
    return {"history": history}


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    request_body: BanUserRequest,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Ban a user.

    Banning revokes all sessions and optionally removes from active games.
    Admins cannot be banned.
    """
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")

    success = await service.ban_user(
        admin_id=admin.id,
        user_id=user_id,
        reason=request_body.reason,
        duration_days=request_body.duration_days,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot ban user (user not found or is admin)")
    return {"message": "User banned successfully"}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """Unban a user."""
    success = await service.unban_user(
        admin_id=admin.id,
        user_id=user_id,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot unban user")
    return {"message": "User unbanned successfully"}


@router.post("/users/{user_id}/force-password-reset")
async def force_password_reset(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Force user to reset password on next login.

    All existing sessions are revoked.
    """
    success = await service.force_password_reset(
        admin_id=admin.id,
        user_id=user_id,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot force password reset")
    return {"message": "Password reset required for user"}


@router.put("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    request_body: ChangeRoleRequest,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Change user role.

    Valid roles: "user", "admin"
    """
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    if request_body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'user' or 'admin'")

    success = await service.change_user_role(
        admin_id=admin.id,
        user_id=user_id,
        new_role=request_body.role,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot change user role")
    return {"message": f"Role changed to {request_body.role}"}


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Start read-only impersonation of a user.

    Returns the user's data as they would see it. This is for
    debugging and support purposes only.
    """
    user = await service.impersonate_user(
        admin_id=admin.id,
        user_id=user_id,
        ip_address=get_client_ip(request),
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "message": "Impersonation started (read-only)",
        "user": user.to_dict(),
    }


# =============================================================================
# Game Moderation Endpoints
# =============================================================================


@router.get("/games")
async def list_active_games(
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """List all active games."""
    games = await service.get_active_games()
    return {"games": games}


@router.get("/games/{game_id}")
async def get_game_details(
    game_id: str,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Get full game state (admin view).

    This view shows all cards, including face-down cards.
    """
    game = await service.get_game_details(
        admin_id=admin.id,
        game_id=game_id,
        ip_address=get_client_ip(request),
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/games/{game_id}/end")
async def end_game(
    game_id: str,
    request_body: EndGameRequest,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Force-end a stuck or problematic game.

    The game will be marked as abandoned.
    """
    success = await service.end_game(
        admin_id=admin.id,
        game_id=game_id,
        reason=request_body.reason,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot end game")
    return {"message": "Game ended successfully"}


# =============================================================================
# System Stats Endpoints
# =============================================================================


@router.get("/stats")
async def get_system_stats(
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """Get current system statistics."""
    stats = await service.get_system_stats()
    return stats.to_dict()


# =============================================================================
# Audit Log Endpoints
# =============================================================================


@router.get("/audit")
async def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    admin_id: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Get admin audit log.

    Can filter by admin_id, action type, or target type.
    """
    entries = await service.get_audit_log(
        limit=limit,
        offset=offset,
        admin_id=admin_id,
        action=action,
        target_type=target_type,
    )
    return {"entries": [e.to_dict() for e in entries]}


# =============================================================================
# Invite Code Endpoints
# =============================================================================


@router.get("/invites")
async def list_invite_codes(
    include_expired: bool = False,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """List all invite codes."""
    codes = await service.get_invite_codes(include_expired=include_expired)
    return {"codes": [c.to_dict() for c in codes]}


@router.post("/invites")
async def create_invite_code(
    request_body: CreateInviteRequest,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """
    Create a new invite code.

    Args:
        max_uses: Maximum number of times the code can be used.
        expires_days: Number of days until the code expires.
    """
    code = await service.create_invite_code(
        admin_id=admin.id,
        max_uses=request_body.max_uses,
        expires_days=request_body.expires_days,
        ip_address=get_client_ip(request),
    )
    return {"code": code, "message": "Invite code created successfully"}


@router.delete("/invites/{code}")
async def revoke_invite_code(
    code: str,
    request: Request,
    admin: User = Depends(require_admin_v2),
    service: AdminService = Depends(get_admin_service_dep),
):
    """Revoke an invite code."""
    success = await service.revoke_invite_code(
        admin_id=admin.id,
        code=code,
        ip_address=get_client_ip(request),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Invite code not found")
    return {"message": "Invite code revoked successfully"}
