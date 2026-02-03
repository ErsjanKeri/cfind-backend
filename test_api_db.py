"""Test what database the API actually connects to"""
from fastapi import FastAPI
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
import asyncio

app = FastAPI()

@app.get("/test-db")
async def test_db():
    async with AsyncSessionLocal() as db:
        # Get current database
        result = await db.execute(text("SELECT current_database();"))
        current_db = result.scalar()

        # Try to count credit_packages
        try:
            result = await db.execute(text("SELECT COUNT(*) FROM credit_packages;"))
            count = result.scalar()
            return {
                "database": current_db,
                "credit_packages_count": count,
                "status": "success"
            }
        except Exception as e:
            return {
                "database": current_db,
                "error": str(e),
                "status": "error"
            }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)