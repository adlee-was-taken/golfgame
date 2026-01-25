"""
Tests for the authentication system.

Run with: pytest test_auth.py -v
"""

import os
import pytest
import tempfile
from datetime import datetime, timedelta

from auth import AuthManager, User, UserRole, Session, InviteCode


@pytest.fixture
def auth_manager():
    """Create a fresh auth manager with temporary database."""
    # Use a temporary file for testing
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Create manager (this will create default admin)
    manager = AuthManager(db_path=path)

    yield manager

    # Cleanup
    os.unlink(path)


class TestUserCreation:
    """Test user creation and retrieval."""

    def test_create_user(self, auth_manager):
        """Can create a new user."""
        user = auth_manager.create_user(
            username="testuser",
            password="password123",
            email="test@example.com",
        )

        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == UserRole.USER
        assert user.is_active is True

    def test_create_duplicate_username_fails(self, auth_manager):
        """Cannot create user with duplicate username."""
        auth_manager.create_user(username="testuser", password="pass1")
        user2 = auth_manager.create_user(username="testuser", password="pass2")

        assert user2 is None

    def test_create_duplicate_email_fails(self, auth_manager):
        """Cannot create user with duplicate email."""
        auth_manager.create_user(
            username="user1",
            password="pass1",
            email="test@example.com"
        )
        user2 = auth_manager.create_user(
            username="user2",
            password="pass2",
            email="test@example.com"
        )

        assert user2 is None

    def test_create_admin_user(self, auth_manager):
        """Can create admin user."""
        user = auth_manager.create_user(
            username="newadmin",
            password="adminpass",
            role=UserRole.ADMIN,
        )

        assert user is not None
        assert user.is_admin() is True

    def test_get_user_by_id(self, auth_manager):
        """Can retrieve user by ID."""
        created = auth_manager.create_user(username="testuser", password="pass")
        retrieved = auth_manager.get_user_by_id(created.id)

        assert retrieved is not None
        assert retrieved.username == "testuser"

    def test_get_user_by_username(self, auth_manager):
        """Can retrieve user by username."""
        auth_manager.create_user(username="testuser", password="pass")
        retrieved = auth_manager.get_user_by_username("testuser")

        assert retrieved is not None
        assert retrieved.username == "testuser"


class TestAuthentication:
    """Test login and session management."""

    def test_authenticate_valid_credentials(self, auth_manager):
        """Can authenticate with valid credentials."""
        auth_manager.create_user(username="testuser", password="correctpass")
        user = auth_manager.authenticate("testuser", "correctpass")

        assert user is not None
        assert user.username == "testuser"

    def test_authenticate_invalid_password(self, auth_manager):
        """Invalid password returns None."""
        auth_manager.create_user(username="testuser", password="correctpass")
        user = auth_manager.authenticate("testuser", "wrongpass")

        assert user is None

    def test_authenticate_nonexistent_user(self, auth_manager):
        """Nonexistent user returns None."""
        user = auth_manager.authenticate("nonexistent", "anypass")

        assert user is None

    def test_authenticate_inactive_user(self, auth_manager):
        """Inactive user cannot authenticate."""
        created = auth_manager.create_user(username="testuser", password="pass")
        auth_manager.update_user(created.id, is_active=False)

        user = auth_manager.authenticate("testuser", "pass")

        assert user is None

    def test_create_session(self, auth_manager):
        """Can create session for authenticated user."""
        user = auth_manager.create_user(username="testuser", password="pass")
        session = auth_manager.create_session(user)

        assert session is not None
        assert session.user_id == user.id
        assert session.is_expired() is False

    def test_get_user_from_session(self, auth_manager):
        """Can get user from valid session token."""
        user = auth_manager.create_user(username="testuser", password="pass")
        session = auth_manager.create_session(user)

        retrieved = auth_manager.get_user_from_session(session.token)

        assert retrieved is not None
        assert retrieved.id == user.id

    def test_invalid_session_token(self, auth_manager):
        """Invalid session token returns None."""
        user = auth_manager.get_user_from_session("invalid_token")

        assert user is None

    def test_invalidate_session(self, auth_manager):
        """Can invalidate a session."""
        user = auth_manager.create_user(username="testuser", password="pass")
        session = auth_manager.create_session(user)

        auth_manager.invalidate_session(session.token)
        retrieved = auth_manager.get_user_from_session(session.token)

        assert retrieved is None


class TestInviteCodes:
    """Test invite code functionality."""

    def test_create_invite_code(self, auth_manager):
        """Can create invite code."""
        admin = auth_manager.get_user_by_username("admin")
        invite = auth_manager.create_invite_code(created_by=admin.id)

        assert invite is not None
        assert len(invite.code) == 8
        assert invite.is_valid() is True

    def test_use_invite_code(self, auth_manager):
        """Can use invite code."""
        admin = auth_manager.get_user_by_username("admin")
        invite = auth_manager.create_invite_code(created_by=admin.id, max_uses=1)

        result = auth_manager.use_invite_code(invite.code)

        assert result is True

        # Check use count increased
        updated = auth_manager.get_invite_code(invite.code)
        assert updated.use_count == 1

    def test_invite_code_max_uses(self, auth_manager):
        """Invite code respects max uses."""
        admin = auth_manager.get_user_by_username("admin")
        invite = auth_manager.create_invite_code(created_by=admin.id, max_uses=1)

        # First use should work
        auth_manager.use_invite_code(invite.code)

        # Second use should fail (max_uses=1)
        updated = auth_manager.get_invite_code(invite.code)
        assert updated.is_valid() is False

    def test_invite_code_case_insensitive(self, auth_manager):
        """Invite code lookup is case insensitive."""
        admin = auth_manager.get_user_by_username("admin")
        invite = auth_manager.create_invite_code(created_by=admin.id)

        retrieved_lower = auth_manager.get_invite_code(invite.code.lower())
        retrieved_upper = auth_manager.get_invite_code(invite.code.upper())

        assert retrieved_lower is not None
        assert retrieved_upper is not None

    def test_deactivate_invite_code(self, auth_manager):
        """Can deactivate invite code."""
        admin = auth_manager.get_user_by_username("admin")
        invite = auth_manager.create_invite_code(created_by=admin.id)

        auth_manager.deactivate_invite_code(invite.code)

        updated = auth_manager.get_invite_code(invite.code)
        assert updated.is_valid() is False


class TestAdminFunctions:
    """Test admin-only functions."""

    def test_list_users(self, auth_manager):
        """Admin can list all users."""
        auth_manager.create_user(username="user1", password="pass1")
        auth_manager.create_user(username="user2", password="pass2")

        users = auth_manager.list_users()

        # Should include admin + 2 created users
        assert len(users) >= 3

    def test_update_user_role(self, auth_manager):
        """Admin can change user role."""
        user = auth_manager.create_user(username="testuser", password="pass")

        updated = auth_manager.update_user(user.id, role=UserRole.ADMIN)

        assert updated.is_admin() is True

    def test_change_password(self, auth_manager):
        """Admin can change user password."""
        user = auth_manager.create_user(username="testuser", password="oldpass")

        auth_manager.change_password(user.id, "newpass")

        # Old password should not work
        auth_fail = auth_manager.authenticate("testuser", "oldpass")
        assert auth_fail is None

        # New password should work
        auth_ok = auth_manager.authenticate("testuser", "newpass")
        assert auth_ok is not None

    def test_delete_user(self, auth_manager):
        """Admin can deactivate user."""
        user = auth_manager.create_user(username="testuser", password="pass")

        auth_manager.delete_user(user.id)

        # User should be inactive
        updated = auth_manager.get_user_by_id(user.id)
        assert updated.is_active is False

        # User should not be able to login
        auth_fail = auth_manager.authenticate("testuser", "pass")
        assert auth_fail is None


class TestDefaultAdmin:
    """Test default admin creation."""

    def test_default_admin_created(self, auth_manager):
        """Default admin is created if no admins exist."""
        admin = auth_manager.get_user_by_username("admin")

        assert admin is not None
        assert admin.is_admin() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
