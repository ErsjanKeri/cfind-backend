"""Repository for countries, cities, and neighbourhoods."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.country import Country, City, Neighbourhood


async def get_all_countries(db: AsyncSession) -> list[Country]:
    result = await db.execute(
        select(Country)
        .options(selectinload(Country.cities))
        .order_by(Country.name)
    )
    return list(result.scalars().all())


async def get_country_by_code(db: AsyncSession, code: str) -> Country | None:
    result = await db.execute(select(Country).where(Country.code == code))
    return result.scalar_one_or_none()


async def get_cities(db: AsyncSession, country_code: str) -> list[City]:
    result = await db.execute(
        select(City)
        .where(City.country_code == country_code)
        .order_by(City.name)
    )
    return list(result.scalars().all())


async def get_city_by_id(db: AsyncSession, city_id: int) -> City | None:
    result = await db.execute(select(City).where(City.id == city_id))
    return result.scalar_one_or_none()


async def create_city(db: AsyncSession, country_code: str, name: str) -> City:
    city = City(country_code=country_code, name=name)
    db.add(city)
    await db.flush()
    return city


async def update_city(db: AsyncSession, city_id: int, name: str) -> City | None:
    city = await get_city_by_id(db, city_id)
    if not city:
        return None
    city.name = name
    await db.flush()
    return city


async def delete_city(db: AsyncSession, city_id: int) -> bool:
    city = await get_city_by_id(db, city_id)
    if not city:
        return False
    await db.delete(city)
    await db.flush()
    return True


async def get_neighbourhoods(db: AsyncSession, city_id: int) -> list[Neighbourhood]:
    result = await db.execute(
        select(Neighbourhood)
        .where(Neighbourhood.city_id == city_id)
        .order_by(Neighbourhood.name)
    )
    return list(result.scalars().all())


async def get_neighbourhood_by_id(db: AsyncSession, neighbourhood_id: int) -> Neighbourhood | None:
    result = await db.execute(
        select(Neighbourhood).where(Neighbourhood.id == neighbourhood_id)
    )
    return result.scalar_one_or_none()


async def create_neighbourhood(db: AsyncSession, city_id: int, name: str) -> Neighbourhood:
    neighbourhood = Neighbourhood(city_id=city_id, name=name)
    db.add(neighbourhood)
    await db.flush()
    return neighbourhood


async def delete_neighbourhood(db: AsyncSession, neighbourhood_id: int) -> bool:
    neighbourhood = await get_neighbourhood_by_id(db, neighbourhood_id)
    if not neighbourhood:
        return False
    await db.delete(neighbourhood)
    await db.flush()
    return True
