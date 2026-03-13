"""Country, City, and Neighbourhood models."""

from sqlalchemy import Column, String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.base import Base


class Country(Base):
    """Country model. Code is ISO 3166-1 alpha-2 (e.g. 'al', 'ae')."""

    __tablename__ = "countries"

    code = Column(String(2), primary_key=True)
    name = Column(String, nullable=False)

    cities = relationship("City", back_populates="country", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Country(code={self.code}, name={self.name})>"


class City(Base):
    """City within a country."""

    __tablename__ = "cities"

    __table_args__ = (UniqueConstraint("country_code", "name", name="uq_cities_country_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    country_code = Column(String(2), ForeignKey("countries.code"), nullable=False, index=True)
    name = Column(String, nullable=False)

    country = relationship("Country", back_populates="cities")
    neighbourhoods = relationship("Neighbourhood", back_populates="city", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<City(id={self.id}, name={self.name}, country={self.country_code})>"


class Neighbourhood(Base):
    """Neighbourhood/area within a city."""

    __tablename__ = "neighbourhoods"

    __table_args__ = (UniqueConstraint("city_id", "name", name="uq_neighbourhoods_city_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    name = Column(String, nullable=False)

    city = relationship("City", back_populates="neighbourhoods")

    def __repr__(self):
        return f"<Neighbourhood(id={self.id}, name={self.name}, city_id={self.city_id})>"
