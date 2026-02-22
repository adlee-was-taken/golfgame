"""
Authentication API router for Golf game V2.

Provides endpoints for user registration, login, password management,
and session handling.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, EmailStr

from config import config
from models.user import User
from services.auth_service import AuthService
from services.admin_service import AdminService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# =============================================================================
# Request/Response Models
# =============================================================================


class RegisterRequest(BaseModel):
    """Registration request."""
    username: str
    password: str
    email: Optional[str] = None
    invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class VerifyEmailRequest(BaseModel):
    """Email verification request."""
    token: str


class ResendVerificationRequest(BaseModel):
    """Resend verification email request."""
    email: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""
    email: str


class ResetPasswordRequest(BaseModel):
    """Password reset request."""
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str
    new_password: str


class UpdatePreferencesRequest(BaseModel):
    """Update preferences request."""
    preferences: dict


class ConvertGuestRequest(BaseModel):
    """Convert guest to user request."""
    guest_id: str
    username: str
    password: str
    email: Optional[str] = None


class UserResponse(BaseModel):
    """User response (public fields only)."""
    id: str
    username: str
    email: Optional[str]
    role: str
    email_verified: bool
    preferences: dict
    created_at: str
    last_login: Optional[str]


class AuthResponse(BaseModel):
    """Authentication response with token."""
    user: UserResponse
    token: str
    expires_at: str


class SessionResponse(BaseModel):
    """Session response."""
    id: str
    device_info: dict
    ip_address: Optional[str]
    created_at: str
    last_used_at: str


# =============================================================================
# Dependencies
# =============================================================================

# These will be set by main.py during startup
_auth_service: Optional[AuthService] = None
_admin_service: Optional[AdminService] = None


def set_auth_service(service: AuthService) -> None:
    """Set the auth service instance (called from main.py)."""
    global _auth_service
    _auth_service = service


def set_admin_service_for_auth(service: AdminService) -> None:
    """Set the admin service instance for invite code validation (called from main.py)."""
    global _admin_service
    _admin_service = service


def get_auth_service_dep() -> AuthService:
    """Dependency to get auth service."""
    if _auth_service is None:
        raise HTTPException(status_code=503, detail="Auth service not initialized")
    return _auth_service


async def get_current_user_v2(
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service_dep),
) -> Optional[User]:
    """Get current user from Authorization header (optional)."""
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    return await auth_service.get_user_from_token(token)


async def require_user_v2(
    user: Optional[User] = Depends(get_current_user_v2),
) -> User:
    """Require authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


async def require_admin_v2(
    user: User = Depends(require_user_v2),
) -> User:
    """Require admin user."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_device_info(request: Request) -> dict:
    """Extract device info from request headers."""
    return {
        "user_agent": request.headers.get("user-agent", ""),
    }


def get_token_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


# =============================================================================
# Registration Endpoints
# =============================================================================


@router.post("/register", response_model=AuthResponse)
async def register(
    request_body: RegisterRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Register a new user account."""
    # Validate invite code when invite-only mode is enabled
    if config.INVITE_ONLY:
        if not request_body.invite_code:
            raise HTTPException(status_code=400, detail="Invite code required")
        if not _admin_service:
            raise HTTPException(status_code=503, detail="Admin service not initialized")
        if not await _admin_service.validate_invite_code(request_body.invite_code):
            raise HTTPException(status_code=400, detail="Invalid or expired invite code")

    result = await auth_service.register(
        username=request_body.username,
        password=request_body.password,
        email=request_body.email,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    # Consume the invite code after successful registration
    if config.INVITE_ONLY and request_body.invite_code:
        await _admin_service.use_invite_code(request_body.invite_code)

    if result.requires_verification:
        # Return user info but note they need to verify
        return {
            "user": _user_to_response(result.user),
            "token": "",
            "expires_at": "",
            "message": "Please check your email to verify your account",
        }

    # Auto-login after registration
    login_result = await auth_service.login(
        username=request_body.username,
        password=request_body.password,
        device_info=get_device_info(request),
        ip_address=get_client_ip(request),
    )

    if not login_result.success:
        raise HTTPException(status_code=500, detail="Registration succeeded but login failed")

    return {
        "user": _user_to_response(login_result.user),
        "token": login_result.token,
        "expires_at": login_result.expires_at.isoformat(),
    }


@router.post("/verify-email")
async def verify_email(
    request_body: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Verify email address with token."""
    result = await auth_service.verify_email(request_body.token)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {"status": "ok", "message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    request_body: ResendVerificationRequest,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Resend verification email."""
    await auth_service.resend_verification(request_body.email)
    # Always return success to prevent email enumeration
    return {"status": "ok", "message": "If the email exists, a verification link has been sent"}


# =============================================================================
# Login/Logout Endpoints
# =============================================================================


@router.post("/login", response_model=AuthResponse)
async def login(
    request_body: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Login with username/email and password."""
    result = await auth_service.login(
        username=request_body.username,
        password=request_body.password,
        device_info=get_device_info(request),
        ip_address=get_client_ip(request),
    )

    if not result.success:
        raise HTTPException(status_code=401, detail=result.error)

    return {
        "user": _user_to_response(result.user),
        "token": result.token,
        "expires_at": result.expires_at.isoformat(),
    }


@router.post("/logout")
async def logout(
    token: Optional[str] = Depends(get_token_from_header),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Logout current session."""
    if token:
        await auth_service.logout(token)
    return {"status": "ok"}


@router.post("/logout-all")
async def logout_all(
    user: User = Depends(require_user_v2),
    token: Optional[str] = Depends(get_token_from_header),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Logout all sessions except current."""
    count = await auth_service.logout_all(user.id, except_token=token)
    return {"status": "ok", "sessions_revoked": count}


# =============================================================================
# Password Management Endpoints
# =============================================================================


@router.post("/forgot-password")
async def forgot_password(
    request_body: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Request password reset email."""
    await auth_service.forgot_password(request_body.email)
    # Always return success to prevent email enumeration
    return {"status": "ok", "message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    request_body: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Reset password with token."""
    result = await auth_service.reset_password(
        token=request_body.token,
        new_password=request_body.new_password,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {"status": "ok", "message": "Password reset successfully"}


@router.put("/password")
async def change_password(
    request_body: ChangePasswordRequest,
    user: User = Depends(require_user_v2),
    token: Optional[str] = Depends(get_token_from_header),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Change password for current user."""
    result = await auth_service.change_password(
        user_id=user.id,
        current_password=request_body.current_password,
        new_password=request_body.new_password,
        current_token=token,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {"status": "ok", "message": "Password changed successfully"}


# =============================================================================
# User Profile Endpoints
# =============================================================================


@router.get("/me")
async def get_me(user: User = Depends(require_user_v2)):
    """Get current user info."""
    return {"user": _user_to_response(user)}


@router.put("/me/preferences")
async def update_preferences(
    request_body: UpdatePreferencesRequest,
    user: User = Depends(require_user_v2),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Update user preferences."""
    updated = await auth_service.update_preferences(user.id, request_body.preferences)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update preferences")
    return {"user": _user_to_response(updated)}


# =============================================================================
# Session Management Endpoints
# =============================================================================


@router.get("/sessions")
async def get_sessions(
    user: User = Depends(require_user_v2),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Get all active sessions for current user."""
    sessions = await auth_service.get_sessions(user.id)
    return {
        "sessions": [
            {
                "id": s.id,
                "device_info": s.device_info,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user: User = Depends(require_user_v2),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Revoke a specific session."""
    success = await auth_service.revoke_session(user.id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# =============================================================================
# Guest Conversion Endpoint
# =============================================================================


@router.post("/convert-guest", response_model=AuthResponse)
async def convert_guest(
    request_body: ConvertGuestRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Convert guest session to full user account."""
    result = await auth_service.convert_guest(
        guest_id=request_body.guest_id,
        username=request_body.username,
        password=request_body.password,
        email=request_body.email,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    # Auto-login after conversion
    login_result = await auth_service.login(
        username=request_body.username,
        password=request_body.password,
        device_info=get_device_info(request),
        ip_address=get_client_ip(request),
    )

    if not login_result.success:
        raise HTTPException(status_code=500, detail="Conversion succeeded but login failed")

    return {
        "user": _user_to_response(login_result.user),
        "token": login_result.token,
        "expires_at": login_result.expires_at.isoformat(),
    }


# =============================================================================
# Account Deletion Endpoint
# =============================================================================


@router.delete("/me")
async def delete_account(
    user: User = Depends(require_user_v2),
    auth_service: AuthService = Depends(get_auth_service_dep),
):
    """Delete (soft delete) current user account."""
    success = await auth_service.delete_account(user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete account")
    return {"status": "ok", "message": "Account deleted"}


# =============================================================================
# Helpers
# =============================================================================


def _user_to_response(user: User) -> dict:
    """Convert User to response dict (public fields only)."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "email_verified": user.email_verified,
        "preferences": user.preferences,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }
