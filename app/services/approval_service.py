import datetime
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalStatus, PurchaseStatus, ReservationStatus
from app.core.errors import NotFoundError, PolicyViolationError, StateTransitionError
from app.models.approval import Approval
from app.models.purchase import PurchaseRequest
from app.repositories.budget_repo import BudgetRepository
from app.schemas.approval import ApprovalDecideRequest, ApprovalResponse


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.budget_repo = BudgetRepository(session)

    async def list_pending_approvals(self, organization_id: uuid.UUID) -> List[ApprovalResponse]:
        stmt = (
            select(Approval)
            .join(PurchaseRequest, Approval.purchase_request_id == PurchaseRequest.id)
            .where(
                PurchaseRequest.organization_id == organization_id,
                Approval.status == ApprovalStatus.PENDING,
            )
            .order_by(Approval.created_at.desc())
        )
        approvals = list((await self.session.scalars(stmt)).all())
        return [ApprovalResponse.model_validate(a) for a in approvals]

    async def decide_approval(
        self,
        approval_id: uuid.UUID,
        approver_id: uuid.UUID,
        organization_id: uuid.UUID,
        req: ApprovalDecideRequest,
    ) -> ApprovalResponse:
        stmt = (
            select(Approval)
            .options(selectinload(Approval.purchase_request))
            .where(Approval.id == approval_id)
        )
        approval = await self.session.scalar(stmt)
        if not approval:
            raise NotFoundError("Approval", approval_id)

        pr = approval.purchase_request
        if not pr or pr.organization_id != organization_id:
            raise NotFoundError("Approval", approval_id)

        if approval.status != ApprovalStatus.PENDING:
            raise StateTransitionError(
                current_state=approval.status.value,
                attempted_state=req.decision,
                entity="Approval",
            )

        # Enforce central rule: A hard policy violation must never be overridden by a human approver
        if pr.status == PurchaseStatus.BLOCKED:
            raise PolicyViolationError("Cannot approve a purchase that has been BLOCKED by deterministic policy.")

        now = datetime.datetime.now(datetime.timezone.utc)
        approval.approver_id = approver_id
        approval.decided_at = now
        approval.notes = req.notes

        if req.decision == "APPROVE":
            approval.status = ApprovalStatus.APPROVED
            if pr.status == PurchaseStatus.REQUIRES_APPROVAL:
                pr.status = PurchaseStatus.AUTHORIZED
        else:
            approval.status = ApprovalStatus.REJECTED
            if pr.status == PurchaseStatus.REQUIRES_APPROVAL:
                pr.status = PurchaseStatus.CANCELLED
            # Release budget reservation on rejection
            reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)

        await self.session.commit()
        await self.session.refresh(approval)
        return ApprovalResponse.model_validate(approval)
