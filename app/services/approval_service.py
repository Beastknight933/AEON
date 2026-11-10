import datetime
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalStatus, PurchaseStatus, ReservationStatus
from app.core.errors import NotFoundError, PolicyViolationError, StateTransitionError
from app.models.approval import Approval
from app.models.audit import AuditEvent
from app.models.purchase import PurchaseRequest
from app.models.supplier import SupplierQuote
from app.repositories.budget_repo import BudgetRepository
from app.schemas.approval import ApprovalDecideRequest, ApprovalDetailResponse, ApprovalResponse


def ensure_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.budget_repo = BudgetRepository(session)

    async def list_approvals(
        self,
        organization_id: uuid.UUID,
        status: Optional[ApprovalStatus] = None,
    ) -> List[ApprovalResponse]:
        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = (
            select(Approval)
            .join(PurchaseRequest, Approval.purchase_request_id == PurchaseRequest.id)
            .where(PurchaseRequest.organization_id == organization_id)
        )
        if status:
            stmt = stmt.where(Approval.status == status)

        stmt = stmt.order_by(Approval.created_at.desc())
        approvals = list((await self.session.scalars(stmt)).all())

        # Check and update expired pending approvals
        has_updates = False
        for app in approvals:
            app_expires = ensure_utc(app.expires_at)
            if app.status == ApprovalStatus.PENDING and app_expires and app_expires < now:
                app.status = ApprovalStatus.EXPIRED
                has_updates = True
        if has_updates:
            await self.session.commit()

        return [ApprovalResponse.model_validate(a) for a in approvals]

    async def get_approval(
        self,
        approval_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> ApprovalDetailResponse:
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.purchase_request),
                selectinload(Approval.selected_quote),
            )
            .where(Approval.id == approval_id)
        )
        approval = await self.session.scalar(stmt)
        if not approval:
            raise NotFoundError("Approval", approval_id)

        pr = approval.purchase_request
        if not pr or pr.organization_id != organization_id:
            raise NotFoundError("Approval", approval_id)

        now = datetime.datetime.now(datetime.timezone.utc)
        app_expires = ensure_utc(approval.expires_at)
        is_expired = False
        if app_expires and app_expires < now:
            is_expired = True
            if approval.status == ApprovalStatus.PENDING:
                approval.status = ApprovalStatus.EXPIRED
                await self.session.commit()

        return ApprovalDetailResponse(
            id=approval.id,
            purchase_request_id=approval.purchase_request_id,
            selected_quote_id=approval.selected_quote_id,
            amount=approval.amount,
            currency=approval.currency,
            policy_version=approval.policy_version,
            expires_at=approval.expires_at,
            approver_id=approval.approver_id,
            status=approval.status,
            notes=approval.notes,
            decided_at=approval.decided_at,
            created_at=approval.created_at,
            updated_at=approval.updated_at,
            item_description=pr.item_description if pr else None,
            category=pr.category if pr else None,
            supplier_name=approval.selected_quote.supplier_name if approval.selected_quote else None,
            is_expired=is_expired,
        )

    async def decide_approval(
        self,
        approval_id: uuid.UUID,
        approver_id: uuid.UUID,
        organization_id: uuid.UUID,
        req: ApprovalDecideRequest,
    ) -> ApprovalResponse:
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.purchase_request),
                selectinload(Approval.selected_quote),
            )
            .where(Approval.id == approval_id)
        )
        approval = await self.session.scalar(stmt)
        if not approval:
            raise NotFoundError("Approval", approval_id)

        pr = approval.purchase_request
        if not pr or pr.organization_id != organization_id:
            raise NotFoundError("Approval", approval_id)

        # 1. State Transition Check
        if approval.status != ApprovalStatus.PENDING:
            raise StateTransitionError(
                current_state=approval.status.value,
                attempted_state=req.decision,
                entity="Approval",
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        app_expires = ensure_utc(approval.expires_at)

        # 2. Check Expiration of Approval
        if app_expires and app_expires < now:
            approval.status = ApprovalStatus.EXPIRED
            if pr.status == PurchaseStatus.REQUIRES_APPROVAL:
                pr.status = PurchaseStatus.CANCELLED
            # Release budget reservation
            reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)
            await self.session.commit()
            raise PolicyViolationError("This approval request has expired and can no longer be decided.")

        # 3. Hard Policy Invariant: Hard violations can never be overridden by human approvers
        if pr.status == PurchaseStatus.BLOCKED:
            raise PolicyViolationError("Cannot approve a purchase that has been BLOCKED by deterministic policy.")

        # 4. Underlying Purchase Lifecycle Integrity Check
        if pr.status != PurchaseStatus.REQUIRES_APPROVAL:
            raise PolicyViolationError(
                f"Underlying purchase request is not awaiting approval (current status: {pr.status.value})."
            )

        # 5. Stale Approval & Quote Identity Integrity Check
        # Reject approval if the underlying purchase or quote has changed
        if approval.selected_quote_id and pr.selected_quote_id != approval.selected_quote_id:
            raise PolicyViolationError(
                "Underlying purchase selected quote has changed since approval was requested."
            )

        if approval.selected_quote:
            quote_expires = ensure_utc(approval.selected_quote.expires_at)
            # Check if underlying quote has expired
            if quote_expires and quote_expires < now:
                approval.status = ApprovalStatus.EXPIRED
                pr.status = PurchaseStatus.CANCELLED
                reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
                if reservation and reservation.status == ReservationStatus.ACTIVE:
                    await self.budget_repo.release_reservation_atomic(reservation.id)
                await self.session.commit()
                raise PolicyViolationError("The supplier quote bound to this approval has expired.")

            # Check amount and currency integrity
            if (
                approval.selected_quote.total_amount != approval.amount
                or approval.selected_quote.currency != approval.currency
            ):
                raise PolicyViolationError(
                    "Underlying quote amount or currency has changed since approval was requested."
                )

        # 6. Apply Decision
        approval.approver_id = approver_id
        approval.decided_at = now
        approval.notes = req.notes

        if req.decision == "APPROVE":
            approval.status = ApprovalStatus.APPROVED
            pr.status = PurchaseStatus.AUTHORIZED
            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="USER",
                    actor_id=str(approver_id),
                    action="APPROVAL_APPROVED",
                    entity_type="approval",
                    entity_id=str(approval.id),
                    metadata_json={"amount": str(approval.amount), "notes": req.notes},
                )
            )
        else:
            approval.status = ApprovalStatus.REJECTED
            pr.status = PurchaseStatus.CANCELLED
            # Release budget reservation on rejection
            reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)
            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="USER",
                    actor_id=str(approver_id),
                    action="APPROVAL_REJECTED",
                    entity_type="approval",
                    entity_id=str(approval.id),
                    metadata_json={"amount": str(approval.amount), "notes": req.notes},
                )
            )

        await self.session.commit()
        await self.session.refresh(approval)
        return ApprovalResponse.model_validate(approval)
