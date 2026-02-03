"""Test repository functions directly"""
import asyncio
from app.db.session import AsyncSessionLocal
from app.repositories import promotion_repo

async def test():
    async with AsyncSessionLocal() as db:
        print("Testing promotion_repo.get_credit_packages...")
        packages = await promotion_repo.get_credit_packages(db)
        print(f"Found {len(packages)} credit packages:")
        for pkg in packages:
            print(f"  - {pkg.name}: {pkg.credits} credits for €{pkg.price_eur}")

if __name__ == "__main__":
    asyncio.run(test())