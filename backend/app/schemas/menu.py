import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DietaryType


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


class ItemIn(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal = Field(ge=0, le=1_000_000, decimal_places=2)
    dietary_type: DietaryType | None = None
    is_available: bool = True
    sort_order: int = 0


class ItemUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=2)
    dietary_type: DietaryType | None = None
    is_available: bool | None = None
    sort_order: int | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    image_url: str | None
    dietary_type: DietaryType | None
    is_available: bool
    sort_order: int


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    sort_order: int
    is_active: bool
    items: list[ItemOut] = []


class MenuOut(BaseModel):
    menu_url: str
    menu_published: bool
    categories: list[CategoryOut]


class PublicItem(BaseModel):
    name: str
    description: str | None
    price: Decimal
    image_url: str | None
    dietary_type: DietaryType | None


class PublicCategory(BaseModel):
    name: str
    description: str | None
    items: list[PublicItem]


class PublicMenuOut(BaseModel):
    restaurant_name: str
    logo_url: str | None
    address: str | None
    currency: str
    intro: str | None
    categories: list[PublicCategory]
