"""
Create admin user script.

Use this in production to create the initial admin account.
Interactive script that prompts for admin credentials.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password


async def create_admin():
    """Create admin user interactively."""
    print("\n" + "="*60)
    print("👑 CompanyFinder Albania - Create Admin User")
    print("="*60 + "\n")

    # Get admin details
    print("Enter admin details:\n")

    email = input("Email: ").strip()
    if not email:
        print("❌ Email is required")
        sys.exit(1)

    name = input("Name: ").strip()
    if not name:
        print("❌ Name is required")
        sys.exit(1)

    password = getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        sys.exit(1)

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("❌ Passwords do not match")
        sys.exit(1)

    print()

    # Check if admin already exists
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"❌ User with email '{email}' already exists")
            sys.exit(1)

        # Hash password
        hashed_password = hash_password(password)

        # Create admin user
        admin = User(
            email=email,
            name=name,
            role="admin",
            password=hashed_password,
            email_verified=True,  # Admin bypass email verification
            created_at=datetime.now(timezone.utc)
        )

        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        print("="*60)
        print("✅ Admin user created successfully!")
        print("="*60 + "\n")

        print("Admin Details:")
        print(f"  ID: {admin.id}")
        print(f"  Email: {admin.email}")
        print(f"  Name: {admin.name}")
        print(f"  Role: {admin.role}")
        print(f"  Email Verified: {admin.email_verified}\n")

        print("🔐 Login at: http://localhost:8000/api/auth/login")
        print("📚 API Docs: http://localhost:8000/docs\n")


if __name__ == "__main__":
    asyncio.run(create_admin())
