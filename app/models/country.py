"""Country and City models."""

from sqlalchemy import Column, String, Integer, ForeignKey
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    country_code = Column(String(2), ForeignKey("countries.code"), nullable=False, index=True)
    name = Column(String, nullable=False)

    country = relationship("Country", back_populates="cities")

    def __repr__(self):
        return f"<City(id={self.id}, name={self.name}, country={self.country_code})>"
