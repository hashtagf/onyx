"""CE Usage Report admin API.

Read-only aggregations over CE tables (chat_session / chat_message /
user_usage / chat_feedback). Independent of the EE analytics endpoints.
"""

import csv
import io
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import CHAT_QUALITY_REVIEW_CLAIM_MINUTES
from onyx.db.chat_quality import (
    QualityEvaluation,
    QualityEvaluationInput,
    QualityKpiOverview,
    QualityReviewQueueItemSnapshot,
    QualityReviewQueuePage,
    claim_quality_review_queue_item,
    complete_quality_review_queue_item,
    delete_quality_evaluation,
    fetch_quality_evaluation,
    fetch_quality_evaluations,
    fetch_quality_kpi_overview,
    fetch_quality_review_queue,
    release_quality_review_queue_item,
    skip_quality_review_queue_item,
    upsert_quality_evaluation,
)
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


class SkipQualityReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/overview")
def get_overview(
    days: int = Query(default=30, ge=1, le=_MAX_DAYS),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> UsageOverview:
    return fetch_usage_overview(db_session, days)


@router.get("/quality-overview")
def get_quality_overview(
    days: int = Query(default=30, ge=1, le=_MAX_DAYS),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityKpiOverview:
    return fetch_quality_kpi_overview(db_session, days)


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


@router.get("/quality-evaluations/{chat_message_id}")
def get_quality_evaluation(
    chat_message_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityEvaluation | None:
    return fetch_quality_evaluation(db_session, chat_message_id, "human")


@router.get("/quality-evaluations/{chat_message_id}/sources")
def get_quality_evaluation_sources(
    chat_message_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, QualityEvaluation]:
    return fetch_quality_evaluations(db_session, chat_message_id)


@router.put("/quality-evaluations/{chat_message_id}")
def put_quality_evaluation(
    chat_message_id: int,
    evaluation: QualityEvaluationInput,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityEvaluation:
    human_evaluation = evaluation.model_copy(
        update={
            "evaluation_source": "human",
            "judge_model": None,
            "judge_version": None,
            "rubric_version": None,
            "confidence": None,
        }
    )
    saved_evaluation = upsert_quality_evaluation(
        db_session=db_session,
        chat_message_id=chat_message_id,
        reviewer_user_id=user.id,
        evaluation_input=human_evaluation,
    )
    complete_quality_review_queue_item(
        db_session,
        chat_message_id=chat_message_id,
        user_id=user.id,
    )
    return saved_evaluation


@router.delete("/quality-evaluations/{chat_message_id}", status_code=204)
def remove_quality_evaluation(
    chat_message_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    delete_quality_evaluation(db_session, chat_message_id, "human")


@router.get("/quality-review-queue")
def get_quality_review_queue(
    status: str = Query(
        default="pending", pattern="^(pending|claimed|completed|skipped)$"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityReviewQueuePage:
    return fetch_quality_review_queue(
        db_session,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/quality-review-queue/{queue_item_id}/claim")
def claim_quality_review(
    queue_item_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityReviewQueueItemSnapshot:
    return claim_quality_review_queue_item(
        db_session,
        queue_item_id=queue_item_id,
        user_id=user.id,
        claim_duration=timedelta(minutes=CHAT_QUALITY_REVIEW_CLAIM_MINUTES),
    )


@router.post("/quality-review-queue/{queue_item_id}/release")
def release_quality_review(
    queue_item_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityReviewQueueItemSnapshot:
    return release_quality_review_queue_item(
        db_session,
        queue_item_id=queue_item_id,
        user_id=user.id,
    )


@router.post("/quality-review-queue/{queue_item_id}/skip")
def skip_quality_review(
    queue_item_id: int,
    request: SkipQualityReviewRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> QualityReviewQueueItemSnapshot:
    return skip_quality_review_queue_item(
        db_session,
        queue_item_id=queue_item_id,
        user_id=user.id,
        reason=request.reason,
    )


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
