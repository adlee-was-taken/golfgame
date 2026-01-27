"""Services package for Golf game V2 business logic."""

from .recovery_service import RecoveryService, RecoveryResult
from .email_service import EmailService, get_email_service
from .auth_service import AuthService, AuthResult, RegistrationResult, get_auth_service, close_auth_service
from .admin_service import (
    AdminService,
    UserDetails,
    AuditEntry,
    SystemStats,
    InviteCode,
    get_admin_service,
    close_admin_service,
)

__all__ = [
    "RecoveryService",
    "RecoveryResult",
    "EmailService",
    "get_email_service",
    "AuthService",
    "AuthResult",
    "RegistrationResult",
    "get_auth_service",
    "close_auth_service",
    "AdminService",
    "UserDetails",
    "AuditEntry",
    "SystemStats",
    "InviteCode",
    "get_admin_service",
    "close_admin_service",
]
