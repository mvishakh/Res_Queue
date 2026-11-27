import uuid

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import QUEUE_STAFF, StaffContext
from app.schemas.menu import CategoryIn, CategoryOut, CategoryUpdate, ItemIn, ItemOut, ItemUpdate, MenuOut, PublicMenuOut
from app.services import menu_service as svc

router = APIRouter(prefix="/menu", tags=["menu"])
public_router = APIRouter(prefix="/public", tags=["public"])


@router.get("", response_model=MenuOut)
def get_menu(ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return svc.get_menu(db, ctx)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return svc.create_category(db, ctx, data)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, data: CategoryUpdate, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return svc.update_category(db, ctx, category_id, data)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    svc.delete_category(db, ctx, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(data: ItemIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return svc.create_item(db, ctx, data)


@router.patch("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: uuid.UUID, data: ItemUpdate, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return svc.update_item(db, ctx, item_id, data)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    svc.delete_item(db, ctx, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{item_id}/image", response_model=ItemOut)
async def upload_image(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: StaffContext = Depends(QUEUE_STAFF),
    db: Session = Depends(get_db),
):
    content = await file.read(svc.MAX_IMAGE_BYTES + 1)
    return svc.upload_item_image(db, ctx, item_id, content, file.content_type or "")


@public_router.get("/menu/{slug}", response_model=PublicMenuOut)
def public_menu(slug: str, response: Response, db: Session = Depends(get_db)):
    """Public, unauthenticated digital menu. Contains no customer data."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return svc.get_public_menu(db, slug)
