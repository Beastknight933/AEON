from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks"])


@router.post("/paypal", status_code=status.HTTP_200_OK)
async def receive_paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ingest and verify asynchronous payment notifications from PayPal.
    Enforces signature verification and idempotent processing.
    """
    headers = {k.lower(): v for k, v in request.headers.items()}
    body = await request.json()

    service = PaymentService(db)
    result = await service.process_paypal_webhook(headers=headers, event_body=body)
    return result
