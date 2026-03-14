"""Schemas for countries, cities, and neighbourhoods."""

from pydantic import BaseModel, Field
from app.schemas.base import BaseSchema


class NeighbourhoodResponse(BaseSchema):
    id: int
    city_id: int
    name: str


class CityResponse(BaseSchema):
    id: int
    country_code: str
    name: str


class CountryResponse(BaseSchema):
    code: str
    name: str
    cities: list[CityResponse] = []


class CountryListResponse(BaseModel):
    success: bool = True
    countries: list[CountryResponse]


class CitiesListResponse(BaseModel):
    success: bool = True
    cities: list[CityResponse]


class NeighbourhoodsListResponse(BaseModel):
    success: bool = True
    neighbourhoods: list[NeighbourhoodResponse]


class CreateCityRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateCityRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CreateNeighbourhoodRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)



class AdminCityResponse(BaseModel):
    success: bool = True
    message: str
    city: CityResponse


class AdminNeighbourhoodResponse(BaseModel):
    success: bool = True
    message: str
    neighbourhood: NeighbourhoodResponse
