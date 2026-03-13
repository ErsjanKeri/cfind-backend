"""
Public geography routes.

Endpoints:
- GET /countries - List all countries with cities
- GET /countries/{code}/cities - List cities for a country
- GET /countries/cities/{city_id}/neighbourhoods - List neighbourhoods for a city
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories import geography_repo
from app.schemas.geography import (
    CountryListResponse, CountryResponse,
    CitiesListResponse, CityResponse,
    NeighbourhoodsListResponse, NeighbourhoodResponse,
)

router = APIRouter(prefix="/countries", tags=["Countries"])


@router.get("", response_model=CountryListResponse)
async def list_countries(db: AsyncSession = Depends(get_db)):
    """List all countries with their cities. No auth required."""
    countries = await geography_repo.get_all_countries(db)
    return CountryListResponse(
        countries=[CountryResponse.model_validate(c) for c in countries]
    )


@router.get("/cities/{city_id}/neighbourhoods", response_model=NeighbourhoodsListResponse)
async def list_neighbourhoods(city_id: int, db: AsyncSession = Depends(get_db)):
    """List neighbourhoods for a city. No auth required."""
    city = await geography_repo.get_city_by_id(db, city_id)
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    neighbourhoods = await geography_repo.get_neighbourhoods(db, city_id)
    return NeighbourhoodsListResponse(
        neighbourhoods=[NeighbourhoodResponse.model_validate(n) for n in neighbourhoods]
    )


@router.get("/{code}/cities", response_model=CitiesListResponse)
async def list_cities(code: str, db: AsyncSession = Depends(get_db)):
    """List cities for a country. No auth required."""
    country = await geography_repo.get_country_by_code(db, code)
    if not country:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    cities = await geography_repo.get_cities(db, code)
    return CitiesListResponse(
        cities=[CityResponse.model_validate(c) for c in cities]
    )
