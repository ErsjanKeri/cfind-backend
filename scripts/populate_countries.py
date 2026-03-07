"""Populate countries and cities. Idempotent — safe to re-run."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.country import Country, City

COUNTRIES_DATA = {
    "al": {
        "name": "Albania",
        "cities": [
            "Tirana", "Durrës", "Vlorë", "Shkodër", "Elbasan",
            "Korçë", "Fier", "Berat", "Lushnjë", "Sarandë",
        ],
    },
    "ae": {
        "name": "United Arab Emirates",
        "cities": [
            "Dubai", "Abu Dhabi", "Sharjah", "Ajman",
            "Ras Al Khaimah", "Umm Al Quwain", "Fujairah",
        ],
    },
}


async def populate():
    async with AsyncSessionLocal() as db:
        try:
            for code, data in COUNTRIES_DATA.items():
                # Check if country exists
                result = await db.execute(select(Country).where(Country.code == code))
                country = result.scalar_one_or_none()

                if country:
                    print(f"Country '{data['name']}' ({code}) already exists — skipped")
                else:
                    country = Country(code=code, name=data["name"])
                    db.add(country)
                    await db.flush()
                    print(f"Added country: {data['name']} ({code})")

                # Add cities
                for city_name in data["cities"]:
                    result = await db.execute(
                        select(City).where(City.country_code == code, City.name == city_name)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        print(f"  City '{city_name}' already exists — skipped")
                    else:
                        db.add(City(country_code=code, name=city_name))
                        print(f"  Added city: {city_name}")

            await db.commit()
            print("\nDone.")

        except Exception as e:
            await db.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(populate())
