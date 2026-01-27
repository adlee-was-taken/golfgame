#!/usr/bin/env python3
"""
Create an admin user for the Golf game.

Usage:
    python scripts/create_admin.py <username> <password> [email]

Example:
    python scripts/create_admin.py admin secretpassword admin@example.com
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from stores.user_store import UserStore
from models.user import UserRole
import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()


async def create_admin(username: str, password: str, email: str = None):
    """Create an admin user."""
    if not config.POSTGRES_URL:
        print("Error: POSTGRES_URL not configured in environment or .env file")
        print("Make sure docker-compose is running and .env is set up")
        sys.exit(1)

    print(f"Connecting to database...")
    store = await UserStore.create(config.POSTGRES_URL)

    # Check if user already exists
    existing = await store.get_user_by_username(username)
    if existing:
        print(f"User '{username}' already exists.")
        if existing.role != UserRole.ADMIN:
            # Upgrade to admin
            print(f"Upgrading '{username}' to admin role...")
            await store.update_user(existing.id, role=UserRole.ADMIN)
            print(f"Done! User '{username}' is now an admin.")
        else:
            print(f"User '{username}' is already an admin.")
        await store.close()
        return

    # Create new admin user
    print(f"Creating admin user '{username}'...")
    password_hash = hash_password(password)

    user = await store.create_user(
        username=username,
        password_hash=password_hash,
        email=email,
        role=UserRole.ADMIN,
    )

    if user:
        print(f"Admin user created successfully!")
        print(f"  Username: {user.username}")
        print(f"  Email: {user.email or '(none)'}")
        print(f"  Role: {user.role.value}")
        print(f"\nYou can now login at /admin")
    else:
        print("Failed to create user (username or email may already exist)")

    await store.close()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    email = sys.argv[3] if len(sys.argv) > 3 else None

    if len(password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)

    asyncio.run(create_admin(username, password, email))


if __name__ == "__main__":
    main()
