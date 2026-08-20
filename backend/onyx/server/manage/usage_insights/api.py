"""CE Usage Report admin API.

Read-only aggregations over CE tables (chat_session / chat_message /
user_usage / chat_feedback). Independent of the EE analytics endpoints.
"""

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.db.usage_insights import (
    EXPORT_HEADER,
    ChatHistoryMessage,
    ChatHistoryPage,
    UsageOverview,
    fetch_chat_history,
    fetch_session_messages,
    fetch_usage_overview,
    iter_export_rows,
)

router = APIRouter(prefix="/manage/admin/usage-insights")

_MAX_DAYS = 365


@router.get("/overview")
def get_overview(
    days: int = Query(default=30, ge=1, le=_MAX_DAYS),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> UsageOverview:
    return fetch_usage_overview(db_session, days)


@router.get("/chat-history")
def get_chat_history(
    days: int = Query(default=30, ge=1, le=_MAX_DAYS),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ChatHistoryPage:
    return fetch_chat_history(db_session, days, page, page_size, q)


@router.get("/chat-history/{session_id}")
def get_session_messages(
    session_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[ChatHistoryMessage]:
    return fetch_session_messages(db_session, session_id)


@router.get("/export")
def export_csv(
    days: int = Query(default=30, ge=1, le=_MAX_DAYS),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_HEADER)
    for row in iter_export_rows(db_session, days):
        writer.writerow(row)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=onyx-usage-{days}d.csv"},
    )
