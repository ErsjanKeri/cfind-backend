"""Test database connection"""
import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def test_connection():
    async with AsyncSessionLocal() as db:
        # Test 1: Check current database
        result = await db.execute(text("SELECT current_database();"))
        current_db = result.scalar()
        print(f"Connected to database: {current_db}")

        # Test 2: List tables
        result = await db.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        tables = result.fetchall()
        print(f"\nTables in database ({len(tables)}):")
        for table in tables:
            print(f"  - {table[0]}")

        # Test 3: Count credit packages
        result = await db.execute(text("SELECT COUNT(*) FROM credit_packages;"))
        count = result.scalar()
        print(f"\nCredit packages in database: {count}")

if __name__ == "__main__":
    asyncio.run(test_connection())