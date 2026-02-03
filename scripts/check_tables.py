"""Quick script to check database tables."""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from app.db.session import engine


async def check_tables():
    """List all tables in the database."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        tables = [row[0] for row in result]

        print(f"\n✅ Found {len(tables)} tables in database:\n")
        for i, table in enumerate(tables, 1):
            print(f"  {i:2d}. {table}")
        print()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_tables())
