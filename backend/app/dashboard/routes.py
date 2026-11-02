import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.dashboard import service
from app.dashboard.schemas import (
    AuditAction,
    AuditListOut,
    AuditResult,
    AuditTrigger,
    DashboardSummaryOut,
)
from app.deps import CurrentUserDep, SessionDep

summary_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


@summary_router.get("/summary", response_model=DashboardSummaryOut)
async def get_dashboard_summary(user: CurrentUserDep, session: SessionDep) -> DashboardSummaryOut:
    return await service.summary(session, user.merchant)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@audit_router.get("", response_model=AuditListOut)
async def list_audit(
    user: CurrentUserDep,
    session: SessionDep,
    order_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    trigger: AuditTrigger | None = None,
    result: AuditResult | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditListOut:
    since_utc = _as_utc(since)
    until_utc = _as_utc(until)
    if since_utc is not None and until_utc is not None and since_utc > until_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="`since` must be before `until`",
        )

    return await service.list_audit(
        session,
        user.merchant_id,
        order_id=order_id,
        action=action,
        trigger=trigger,
        result=result,
        since=since_utc,
        until=until_utc,
        limit=limit,
        offset=offset,
    )
