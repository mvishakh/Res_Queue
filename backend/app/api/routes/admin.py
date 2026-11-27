"""Customers, dashboard, analytics, notifications, activity log and settings."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ANY_STAFF, OWNER_ONLY, QUEUE_STAFF, StaffContext
from app.models.enums import MessageStatus
from app.schemas.admin import (
    ActivityOut,
    MessageOut,
    RestaurantOut,
    RestaurantUpdate,
    StaffCreateIn,
    StaffOut,
    StaffUpdateIn,
    WhatsAppConfigIn,
    WhatsAppConfigOut,
)
from app.services import customer_service, report_service, settings_service, whatsapp_service
from app.services.customer_service import CustomerDetailOut, CustomerSummaryOut
from app.services.report_service import AnalyticsOut, OverviewOut

router = APIRouter(tags=["management"])


@router.get("/customers", response_model=list[CustomerSummaryOut])
def list_customers(search: str | None = Query(default=None, max_length=100), ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return customer_service.list_customers(db, ctx, search)


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: uuid.UUID, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return customer_service.get_customer(db, ctx, customer_id)


@router.get("/dashboard/overview", response_model=OverviewOut)
def overview(ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return report_service.overview(db, ctx)


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(days: int = Query(default=7, ge=1, le=90), ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return report_service.analytics(db, ctx, days)


@router.get("/notifications", response_model=list[MessageOut])
def notifications(
    status_: MessageStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    ctx: StaffContext = Depends(QUEUE_STAFF),
    db: Session = Depends(get_db),
):
    return report_service.list_messages(db, ctx, status=status_, limit=limit)


@router.post("/notifications/{message_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_notification(message_id: uuid.UUID, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    message = whatsapp_service.retry_failed_message(db, ctx, message_id)
    return {"id": str(message.id), "status": message.status.value}


@router.get("/activity", response_model=list[ActivityOut])
def activity(limit: int = Query(default=100, ge=1, le=500), ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return report_service.list_activity(db, ctx, limit)


@router.get("/settings/restaurant", response_model=RestaurantOut)
def get_restaurant(ctx: StaffContext = Depends(ANY_STAFF), db: Session = Depends(get_db)):
    return settings_service.get_restaurant(db, ctx)


@router.patch("/settings/restaurant", response_model=RestaurantOut)
def update_restaurant(data: RestaurantUpdate, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.update_restaurant(db, ctx, data)


@router.get("/settings/whatsapp", response_model=WhatsAppConfigOut)
def get_whatsapp(ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.get_whatsapp_config(db, ctx)


@router.put("/settings/whatsapp", response_model=WhatsAppConfigOut)
def put_whatsapp(data: WhatsAppConfigIn, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.update_whatsapp_config(db, ctx, data)


@router.get("/staff", response_model=list[StaffOut])
def list_staff(ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.list_staff(db, ctx)


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def add_staff(data: StaffCreateIn, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.add_staff(db, ctx, data)


@router.patch("/staff/{membership_id}", response_model=StaffOut)
def update_staff(membership_id: uuid.UUID, data: StaffUpdateIn, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return settings_service.update_staff(db, ctx, membership_id, data)
