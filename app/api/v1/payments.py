from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.payment import (
    PaymentCaptureRequest,
    PaymentCaptureResponse,
    PaymentOrderCreateRequest,
    PaymentOrderCreateResponse,
    PaymentStatusResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["PayPal Payments & Capture"])


@router.post("/create-order", response_model=PaymentOrderCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_order(
    req: PaymentOrderCreateRequest,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a PayPal Orders v2 with CAPTURE intent for an AUTHORIZED purchase request.
    Returns the PayPal approval URL for the frontend/buyer redirect.
    """
    _, _, org = context
    service = PaymentService(db)
    return await service.create_payment_order(req.purchase_request_id, org.id)


@router.post("/capture", response_model=PaymentCaptureResponse)
async def capture_payment(
    req: PaymentCaptureRequest,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Capture an approved PayPal Order and settle the budget reservation into spent funds.
    A frontend return URL is NOT proof of payment; only a successful backend capture authorizes delivery.
    """
    _, _, org = context
    service = PaymentService(db)
    return await service.capture_payment(req.provider_order_id, org.id)


@router.get("/{provider_order_id}", response_model=PaymentStatusResponse)
async def get_payment_status(
    provider_order_id: str,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Check the current status of a PayPal order attempt.
    """
    _, _, org = context
    service = PaymentService(db)
    return await service.get_payment_status(provider_order_id, org.id)


@router.post("/{provider_order_id}/reconcile", response_model=PaymentStatusResponse)
async def reconcile_single_payment(
    provider_order_id: str,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Reconcile an uncertain or pending payment attempt against PayPal's authoritative API.
    Enforces atomic state transitions, budget settlement/release, and audit recording.
    """
    _, _, org = context
    service = PaymentService(db)
    return await service.reconcile_payment(provider_order_id, org.id)


@router.post("/reconcile", response_model=List[PaymentStatusResponse])
async def reconcile_pending_payments(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Reconcile all in-flight or pending payment attempts for the authenticated organization.
    """
    _, _, org = context
    service = PaymentService(db)
    return await service.reconcile_pending_payments(org.id)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public webhook receiver for asynchronous PayPal event notifications.
    Authenticity is cryptographically verified against PayPal's signature API.
    Enforces idempotency using provider_event_id.
    """
    headers = dict(request.headers)
    body = await request.json()
    service = PaymentService(db)
    return await service.process_paypal_webhook(headers, body)
