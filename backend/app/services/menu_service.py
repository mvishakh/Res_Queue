import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.security import StaffContext
from app.models import MenuCategory, MenuItem, Restaurant
from app.schemas.menu import (
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    ItemIn,
    ItemOut,
    ItemUpdate,
    MenuOut,
    PublicCategory,
    PublicItem,
    PublicMenuOut,
)
from app.services import supabase_admin, whatsapp_service
from app.services.common import log_activity

ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _categories(db: Session, restaurant_id: uuid.UUID) -> list[MenuCategory]:
    return list(
        db.scalars(
            select(MenuCategory)
            .where(MenuCategory.restaurant_id == restaurant_id)
            .order_by(MenuCategory.sort_order, MenuCategory.name)
        )
    )


def _items(db: Session, restaurant_id: uuid.UUID) -> list[MenuItem]:
    return list(
        db.scalars(
            select(MenuItem).where(MenuItem.restaurant_id == restaurant_id).order_by(MenuItem.sort_order, MenuItem.name)
        )
    )


def get_menu(db: Session, ctx: StaffContext) -> MenuOut:
    restaurant = db.get(Restaurant, ctx.restaurant_id)
    items = _items(db, ctx.restaurant_id)
    cats = []
    for c in _categories(db, ctx.restaurant_id):
        out = CategoryOut.model_validate(c)
        out.items = [ItemOut.model_validate(i) for i in items if i.category_id == c.id]
        cats.append(out)
    return MenuOut(
        menu_url=whatsapp_service.menu_url(restaurant), menu_published=restaurant.menu_published, categories=cats
    )


def get_public_menu(db: Session, slug: str) -> PublicMenuOut:
    restaurant = db.scalar(select(Restaurant).where(Restaurant.slug == slug))
    if restaurant is None or not restaurant.menu_published:
        raise NotFoundError("Menu not found")
    items = [i for i in _items(db, restaurant.id) if i.is_available]
    categories = []
    for c in _categories(db, restaurant.id):
        if not c.is_active:
            continue
        cat_items = [
            PublicItem(
                name=i.name, description=i.description, price=i.price, image_url=i.image_url, dietary_type=i.dietary_type
            )
            for i in items
            if i.category_id == c.id
        ]
        if cat_items:
            categories.append(PublicCategory(name=c.name, description=c.description, items=cat_items))
    return PublicMenuOut(
        restaurant_name=restaurant.name,
        logo_url=restaurant.logo_url,
        address=restaurant.address,
        currency=restaurant.currency,
        intro=restaurant.menu_intro,
        categories=categories,
    )


def _get_category(db: Session, ctx: StaffContext, category_id: uuid.UUID) -> MenuCategory:
    c = db.get(MenuCategory, category_id)
    if c is None or c.restaurant_id != ctx.restaurant_id:
        raise NotFoundError("Category not found")
    return c


def _get_item(db: Session, ctx: StaffContext, item_id: uuid.UUID) -> MenuItem:
    i = db.get(MenuItem, item_id)
    if i is None or i.restaurant_id != ctx.restaurant_id:
        raise NotFoundError("Menu item not found")
    return i


def _commit_unique(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc


def create_category(db: Session, ctx: StaffContext, data: CategoryIn) -> MenuCategory:
    c = MenuCategory(id=uuid.uuid4(), restaurant_id=ctx.restaurant_id, **data.model_dump())
    db.add(c)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_CATEGORY_CREATED", entity_type="menu_category",
                 entity_id=c.id, actor_id=ctx.staff_id, details={"name": c.name})
    _commit_unique(db, f"Category '{data.name}' already exists")
    return c


def update_category(db: Session, ctx: StaffContext, category_id: uuid.UUID, data: CategoryUpdate) -> MenuCategory:
    c = _get_category(db, ctx, category_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_CATEGORY_UPDATED", entity_type="menu_category",
                 entity_id=c.id, actor_id=ctx.staff_id, details=data.model_dump(exclude_unset=True, mode="json"))
    _commit_unique(db, "A category with this name already exists")
    return c


def delete_category(db: Session, ctx: StaffContext, category_id: uuid.UUID) -> None:
    c = _get_category(db, ctx, category_id)
    if db.scalar(select(MenuItem.id).where(MenuItem.category_id == c.id).limit(1)):
        raise ConflictError("Move or delete the items in this category first")
    db.delete(c)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_CATEGORY_DELETED", entity_type="menu_category",
                 entity_id=category_id, actor_id=ctx.staff_id, details={"name": c.name})
    db.commit()


def create_item(db: Session, ctx: StaffContext, data: ItemIn) -> MenuItem:
    _get_category(db, ctx, data.category_id)
    i = MenuItem(id=uuid.uuid4(), restaurant_id=ctx.restaurant_id, **data.model_dump())
    db.add(i)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_ITEM_CREATED", entity_type="menu_item",
                 entity_id=i.id, actor_id=ctx.staff_id, details={"name": i.name, "price": str(i.price)})
    db.commit()
    return i


def update_item(db: Session, ctx: StaffContext, item_id: uuid.UUID, data: ItemUpdate) -> MenuItem:
    i = _get_item(db, ctx, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] is not None:
        _get_category(db, ctx, changes["category_id"])
    for k, v in changes.items():
        if k == "category_id" and v is None:
            continue
        setattr(i, k, v)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_ITEM_UPDATED", entity_type="menu_item",
                 entity_id=i.id, actor_id=ctx.staff_id, details=data.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return i


def delete_item(db: Session, ctx: StaffContext, item_id: uuid.UUID) -> None:
    i = _get_item(db, ctx, item_id)
    path = i.image_path
    db.delete(i)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_ITEM_DELETED", entity_type="menu_item",
                 entity_id=item_id, actor_id=ctx.staff_id, details={"name": i.name})
    db.commit()
    if path:
        supabase_admin.delete_object(path)


def upload_item_image(db: Session, ctx: StaffContext, item_id: uuid.UUID, content: bytes, content_type: str) -> MenuItem:
    i = _get_item(db, ctx, item_id)
    ext = ALLOWED_IMAGE_TYPES.get(content_type)
    if ext is None:
        raise ValidationFailed("Upload a JPEG, PNG or WebP image")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValidationFailed("Images must be 5 MB or smaller")
    path = f"{ctx.restaurant_id}/{i.id}-{uuid.uuid4().hex[:8]}.{ext}"
    url = supabase_admin.upload_public_object(path, content, content_type)
    old = i.image_path
    i.image_url, i.image_path = url, path
    log_activity(db, restaurant_id=ctx.restaurant_id, action="MENU_ITEM_IMAGE_UPLOADED", entity_type="menu_item",
                 entity_id=i.id, actor_id=ctx.staff_id)
    db.commit()
    if old:
        supabase_admin.delete_object(old)
    return i
