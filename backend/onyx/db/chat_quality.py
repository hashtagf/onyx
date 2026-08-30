"""Database operations and metrics for assistant-response quality."""

from datetime import datetime, timedelta, timezone
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from onyx.configs.constants import MessageType
from onyx.db.models import (
    ChatMessage,
    ChatMessageFeedback,
    ChatMessageQualityEvaluation,
    ChatQualityEvaluationJob,
    ChatQualityReviewQueueItem,
    ChatSession,
    UserUsage,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

EvaluationSource = Literal["human", "llm_judge"]


class QualityEvaluationInput(BaseModel):
    evaluation_source: EvaluationSource = "human"
    judge_model: str | None = Field(default=None, max_length=255)
    judge_version: str | None = Field(default=None, max_length=100)
    rubric_version: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    task_category: str | None = Field(default=None, max_length=100)
    task_success: bool | None = None
    first_answer_resolution: bool | None = None
    required_rephrase: bool | None = None
    correctness: int | None = Field(default=None, ge=1, le=5)
    relevance: int | None = Field(default=None, ge=1, le=5)
    completeness: int | None = Field(default=None, ge=1, le=5)
    clarity: int | None = Field(default=None, ge=1, le=5)
    instruction_following: int | None = Field(default=None, ge=1, le=5)
    grounded: bool | None = None
    citation_accuracy: int | None = Field(default=None, ge=1, le=5)
    retrieval_relevance: int | None = Field(default=None, ge=1, le=5)
    hallucination_detected: bool | None = None
    appropriate_refusal: bool | None = None
    false_refusal: bool | None = None
    harmful_response: bool | None = None
    sensitive_data_leakage: bool | None = None
    unauthorized_document_exposure: bool | None = None
    policy_violation: bool | None = None
    prompt_injection_succeeded: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_complete_answer_quality_scores(self) -> "QualityEvaluationInput":
        score_fields = (
            self.correctness,
            self.relevance,
            self.completeness,
            self.clarity,
            self.instruction_following,
        )
        if any(score is not None for score in score_fields) and any(
            score is None for score in score_fields
        ):
            raise ValueError("Set all five answer-quality scores together.")
        return self


class QualityEvaluation(QualityEvaluationInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_message_id: int
    reviewer_user_id: UUID | None
    time_created: datetime
    time_updated: datetime


class KpiMetric(BaseModel):
    value: float | None
    sample_size: int


class SafetyGuardrails(BaseModel):
    reviewed_responses: int
    harmful_responses: int
    sensitive_data_leaks: int
    unauthorized_document_exposures: int
    policy_violations: int
    successful_prompt_injections: int


class ModelQualityRow(BaseModel):
    model: str
    assistant_responses: int
    reviewed_responses: int
    task_success_rate: float | None
    answer_quality_score: float | None
    hallucination_rate: float | None
    p95_response_seconds: float | None


class TaskCategoryQualityRow(BaseModel):
    task_category: str
    reviewed_responses: int
    task_success_rate: float | None
    answer_quality_score: float | None
    hallucination_rate: float | None


class QualityKpiOverview(BaseModel):
    days: int
    assistant_responses: int
    reviewed_responses: int
    human_reviewed_responses: int
    llm_reviewed_responses: int
    paired_reviewed_responses: int
    boolean_agreement_rate: KpiMetric
    score_mean_absolute_error: KpiMetric
    pending_review_items: int
    claimed_review_items: int
    failed_judge_jobs: int
    evaluation_coverage_rate: KpiMetric
    response_error_rate: KpiMetric
    citation_coverage_rate: KpiMetric
    feedback_coverage_rate: KpiMetric
    positive_feedback_rate: KpiMetric
    average_response_seconds: KpiMetric
    p95_response_seconds: KpiMetric
    average_user_turns_per_session: KpiMetric
    task_success_rate: KpiMetric
    first_answer_resolution_rate: KpiMetric
    rephrase_rate: KpiMetric
    answer_quality_score: KpiMetric
    correctness_score: KpiMetric
    relevance_score: KpiMetric
    completeness_score: KpiMetric
    clarity_score: KpiMetric
    instruction_following_score: KpiMetric
    grounded_answer_rate: KpiMetric
    citation_accuracy_score: KpiMetric
    retrieval_relevance_score: KpiMetric
    hallucination_rate: KpiMetric
    appropriate_refusal_rate: KpiMetric
    false_refusal_rate: KpiMetric
    estimated_cost_per_success_cents: KpiMetric
    safety: SafetyGuardrails
    by_model: list[ModelQualityRow]
    by_task_category: list[TaskCategoryQualityRow]


class ChatQualityReviewCandidate(BaseModel):
    chat_message_id: int
    user_message: str
    assistant_message: str
    citation_blurbs: list[str]
    conversation_context: list[str] = Field(default_factory=list)


class QualityEvaluationJobSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_message_id: int
    judge_version: str
    status: str
    attempts: int
    last_error: str | None


class QualityReviewQueueItemSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_message_id: int
    priority: int
    reasons: list[str]
    status: str
    assigned_user_id: UUID | None
    claim_expires_at: datetime | None
    root_cause: str | None
    skip_reason: str | None


class QualityReviewQueueEntry(QualityReviewQueueItemSnapshot):
    session_id: UUID
    model_display_name: str | None
    user_message: str
    assistant_message: str
    human_evaluation: QualityEvaluation | None
    llm_evaluation: QualityEvaluation | None


class QualityReviewQueuePage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[QualityReviewQueueEntry]


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _rate(true_count: int, sample_size: int) -> KpiMetric:
    return KpiMetric(
        value=(100.0 * true_count / sample_size) if sample_size else None,
        sample_size=sample_size,
    )


def _score(value: float | None, sample_size: int) -> KpiMetric:
    return KpiMetric(
        value=float(value) if value is not None else None, sample_size=sample_size
    )


def weighted_answer_quality_score(
    correctness: float,
    relevance: float,
    completeness: float,
    clarity: float,
    instruction_following: float,
) -> float:
    return (
        correctness * 0.35
        + relevance * 0.25
        + completeness * 0.20
        + clarity * 0.10
        + instruction_following * 0.10
    )


def upsert_quality_evaluation(
    db_session: Session,
    chat_message_id: int,
    reviewer_user_id: UUID | None,
    evaluation_input: QualityEvaluationInput,
) -> QualityEvaluation:
    message = db_session.scalar(
        select(ChatMessage).where(ChatMessage.id == chat_message_id)
    )
    if message is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Chat message not found.")
    if message.message_type != MessageType.ASSISTANT:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Only assistant messages can have a quality evaluation.",
        )

    evaluation = db_session.scalar(
        select(ChatMessageQualityEvaluation).where(
            ChatMessageQualityEvaluation.chat_message_id == chat_message_id,
            ChatMessageQualityEvaluation.evaluation_source
            == evaluation_input.evaluation_source,
        )
    )
    values = evaluation_input.model_dump()
    if evaluation is None:
        evaluation = ChatMessageQualityEvaluation(
            chat_message_id=chat_message_id,
            reviewer_user_id=reviewer_user_id,
            **values,
        )
        db_session.add(evaluation)
    else:
        for field_name, value in values.items():
            setattr(evaluation, field_name, value)
        evaluation.reviewer_user_id = reviewer_user_id
        evaluation.time_updated = datetime.now(timezone.utc)

    db_session.commit()
    db_session.refresh(evaluation)
    return QualityEvaluation.model_validate(evaluation)


def fetch_quality_review_candidates(
    db_session: Session,
    days: int,
    limit: int,
    chat_message_id: int | None = None,
) -> list[ChatQualityReviewCandidate]:
    query = (
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .join(
            ChatMessageQualityEvaluation,
            and_(
                ChatMessageQualityEvaluation.chat_message_id == ChatMessage.id,
                ChatMessageQualityEvaluation.evaluation_source == "llm_judge",
            ),
            isouter=True,
        )
        .where(
            ChatMessage.time_sent >= _cutoff(days),
            ChatMessage.message_type == MessageType.ASSISTANT,
            ChatMessage.message != "",
            ChatMessage.error.is_(None),
            ChatMessageQualityEvaluation.id.is_(None),
            ChatSession.deleted.is_(False),
            ChatSession.incognito_record_mode.is_(None),
        )
        .options(
            selectinload(ChatMessage.parent_message),
            selectinload(ChatMessage.search_docs),
        )
        .order_by(ChatMessage.time_sent.desc())
        .limit(limit)
    )
    if chat_message_id is not None:
        query = query.where(ChatMessage.id == chat_message_id)

    messages = db_session.scalars(query).all()
    candidates: list[ChatQualityReviewCandidate] = []
    for message in messages:
        context_rows = db_session.execute(
            select(ChatMessage.message_type, ChatMessage.message)
            .where(
                ChatMessage.chat_session_id == message.chat_session_id,
                ChatMessage.id < message.id,
                ChatMessage.message_type != MessageType.SYSTEM,
                ChatMessage.message != "",
            )
            .order_by(ChatMessage.id.desc())
            .limit(6)
        ).all()
        candidates.append(
            ChatQualityReviewCandidate(
                chat_message_id=message.id,
                user_message=(
                    message.parent_message.message if message.parent_message else ""
                ),
                assistant_message=message.message,
                citation_blurbs=[document.blurb for document in message.search_docs],
                conversation_context=[
                    f"{message_type.value}: {context_message}"
                    for message_type, context_message in reversed(context_rows)
                ],
            )
        )
    return candidates


def create_quality_evaluation_jobs(
    db_session: Session,
    *,
    days: int,
    limit: int,
    judge_version: str,
) -> list[int]:
    existing_evaluation = (
        select(ChatMessageQualityEvaluation.id)
        .where(
            ChatMessageQualityEvaluation.chat_message_id == ChatMessage.id,
            ChatMessageQualityEvaluation.evaluation_source == "llm_judge",
            ChatMessageQualityEvaluation.judge_version == judge_version,
        )
        .exists()
    )
    existing_job = (
        select(ChatQualityEvaluationJob.id)
        .where(
            ChatQualityEvaluationJob.chat_message_id == ChatMessage.id,
            ChatQualityEvaluationJob.judge_version == judge_version,
        )
        .exists()
    )
    message_ids = list(
        db_session.scalars(
            select(ChatMessage.id)
            .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
            .where(
                ChatMessage.time_sent >= _cutoff(days),
                ChatMessage.message_type == MessageType.ASSISTANT,
                ChatMessage.message != "",
                ChatMessage.error.is_(None),
                ChatSession.deleted.is_(False),
                ChatSession.incognito_record_mode.is_(None),
                ~existing_evaluation,
                ~existing_job,
            )
            .order_by(ChatMessage.time_sent)
            .limit(limit)
        )
    )
    if not message_ids:
        return []

    inserted_job_ids = list(
        db_session.scalars(
            pg_insert(ChatQualityEvaluationJob)
            .values(
                [
                    {
                        "chat_message_id": message_id,
                        "judge_version": judge_version,
                        "status": "pending",
                        "attempts": 0,
                    }
                    for message_id in message_ids
                ]
            )
            .on_conflict_do_nothing(
                constraint="uq_chat_quality_job_message_judge_version"
            )
            .returning(ChatQualityEvaluationJob.id)
        )
    )
    db_session.commit()
    return inserted_job_ids


def remaining_quality_evaluation_daily_capacity(
    db_session: Session, daily_limit: int
) -> int:
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    completed_today = int(
        db_session.scalar(
            select(func.count(ChatQualityEvaluationJob.id)).where(
                ChatQualityEvaluationJob.status == "completed",
                ChatQualityEvaluationJob.completed_at >= today,
            )
        )
        or 0
    )
    return max(0, daily_limit - completed_today)


def fetch_dispatchable_quality_job_ids(
    db_session: Session,
    *,
    limit: int,
    max_attempts: int,
    stale_after: timedelta,
) -> list[int]:
    if limit <= 0:
        return []
    stale_before = datetime.now(timezone.utc) - stale_after
    return list(
        db_session.scalars(
            select(ChatQualityEvaluationJob.id)
            .where(
                ChatQualityEvaluationJob.attempts < max_attempts,
                or_(
                    ChatQualityEvaluationJob.status.in_(("pending", "failed")),
                    and_(
                        ChatQualityEvaluationJob.status == "running",
                        ChatQualityEvaluationJob.claimed_at <= stale_before,
                    ),
                ),
            )
            .order_by(ChatQualityEvaluationJob.time_created)
            .limit(limit)
        )
    )


def claim_quality_evaluation_job(
    db_session: Session,
    *,
    job_id: int,
    max_attempts: int,
    stale_after: timedelta,
) -> QualityEvaluationJobSnapshot | None:
    job = db_session.scalar(
        select(ChatQualityEvaluationJob)
        .where(ChatQualityEvaluationJob.id == job_id)
        .with_for_update()
    )
    if job is None or job.status in {"completed", "skipped"}:
        return None
    now = datetime.now(timezone.utc)
    running_is_stale = (
        job.status == "running"
        and job.claimed_at is not None
        and job.claimed_at <= now - stale_after
    )
    if job.status == "running" and not running_is_stale:
        return None
    if job.attempts >= max_attempts:
        job.status = "skipped"
        job.last_error = job.last_error or "Maximum evaluation attempts reached."
        job.completed_at = now
        db_session.commit()
        return None

    job.status = "running"
    job.attempts += 1
    job.claimed_at = now
    job.last_error = None
    db_session.commit()
    db_session.refresh(job)
    return QualityEvaluationJobSnapshot.model_validate(job)


def complete_quality_evaluation_job(db_session: Session, job_id: int) -> None:
    now = datetime.now(timezone.utc)
    db_session.execute(
        update(ChatQualityEvaluationJob)
        .where(ChatQualityEvaluationJob.id == job_id)
        .values(status="completed", completed_at=now, last_error=None)
    )
    db_session.commit()


def fail_quality_evaluation_job(
    db_session: Session,
    *,
    job_id: int,
    error: str,
    max_attempts: int,
) -> None:
    job = db_session.scalar(
        select(ChatQualityEvaluationJob)
        .where(ChatQualityEvaluationJob.id == job_id)
        .with_for_update()
    )
    if job is None or job.status == "completed":
        return
    job.last_error = error[:4000]
    if job.attempts >= max_attempts:
        job.status = "skipped"
        job.completed_at = datetime.now(timezone.utc)
    else:
        job.status = "failed"
    db_session.commit()


def _quality_review_reasons(
    *,
    chat_message_id: int,
    evaluation: QualityEvaluationInput,
    feedback: bool | None,
    sample_rate: float,
    high_risk_categories: set[str],
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    priority = 0
    safety_values = (
        evaluation.harmful_response,
        evaluation.sensitive_data_leakage,
        evaluation.unauthorized_document_exposure,
        evaluation.policy_violation,
        evaluation.prompt_injection_succeeded,
    )
    if any(value is True for value in safety_values):
        reasons.append("safety_incident")
        priority = max(priority, 100)
    if evaluation.hallucination_detected is True:
        reasons.append("hallucination")
        priority = max(priority, 90)
    if evaluation.false_refusal is True:
        reasons.append("false_refusal")
        priority = max(priority, 90)
    if feedback is False:
        reasons.append("negative_feedback")
        priority = max(priority, 80)
    if evaluation.confidence is not None and evaluation.confidence < 0.7:
        reasons.append("low_judge_confidence")
        priority = max(priority, 70)
    complete_scores = (
        evaluation.correctness,
        evaluation.relevance,
        evaluation.completeness,
        evaluation.clarity,
        evaluation.instruction_following,
    )
    if all(score is not None for score in complete_scores):
        score = weighted_answer_quality_score(
            *cast(tuple[int, int, int, int, int], complete_scores)
        )
        if score < 3.5:
            reasons.append("low_answer_quality")
            priority = max(priority, 60)
    if (
        evaluation.task_category is not None
        and evaluation.task_category.lower() in high_risk_categories
    ):
        reasons.append("high_risk_category")
        priority = max(priority, 50)
    sample_threshold = round(max(0.0, min(sample_rate, 1.0)) * 10_000)
    if chat_message_id % 10_000 < sample_threshold:
        reasons.append("random_sample")
        priority = max(priority, 10)
    return priority, reasons


def ensure_quality_review_queue_item(
    db_session: Session,
    *,
    chat_message_id: int,
    evaluation: QualityEvaluationInput,
    sample_rate: float,
    high_risk_categories: set[str],
) -> QualityReviewQueueItemSnapshot | None:
    feedback = db_session.scalar(
        select(ChatMessageFeedback.is_positive)
        .where(ChatMessageFeedback.chat_message_id == chat_message_id)
        .order_by(ChatMessageFeedback.id.desc())
        .limit(1)
    )
    priority, reasons = _quality_review_reasons(
        chat_message_id=chat_message_id,
        evaluation=evaluation,
        feedback=feedback,
        sample_rate=sample_rate,
        high_risk_categories=high_risk_categories,
    )
    if not reasons:
        return None
    queue_item_id = db_session.scalar(
        pg_insert(ChatQualityReviewQueueItem)
        .values(
            chat_message_id=chat_message_id,
            priority=priority,
            reasons=reasons,
            status="pending",
        )
        .on_conflict_do_nothing(constraint="uq_chat_quality_review_queue_message")
        .returning(ChatQualityReviewQueueItem.id)
    )
    if queue_item_id is None:
        queue_item = db_session.scalar(
            select(ChatQualityReviewQueueItem).where(
                ChatQualityReviewQueueItem.chat_message_id == chat_message_id
            )
        )
    else:
        queue_item = db_session.get(ChatQualityReviewQueueItem, queue_item_id)
    db_session.commit()
    return (
        QualityReviewQueueItemSnapshot.model_validate(queue_item)
        if queue_item is not None
        else None
    )


def ensure_negative_feedback_review_queue_item(
    db_session: Session, chat_message_id: int
) -> None:
    db_session.execute(
        pg_insert(ChatQualityReviewQueueItem)
        .values(
            chat_message_id=chat_message_id,
            priority=80,
            reasons=["negative_feedback"],
            status="pending",
        )
        .on_conflict_do_nothing(constraint="uq_chat_quality_review_queue_message")
    )
    db_session.commit()


def release_stale_quality_review_claims(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.execute(
        update(ChatQualityReviewQueueItem)
        .where(
            ChatQualityReviewQueueItem.status == "claimed",
            ChatQualityReviewQueueItem.claim_expires_at <= now,
        )
        .values(
            status="pending",
            assigned_user_id=None,
            claim_expires_at=None,
        )
    )
    db_session.commit()


def fetch_quality_review_queue(
    db_session: Session,
    *,
    status: str,
    page: int,
    page_size: int,
) -> QualityReviewQueuePage:
    release_stale_quality_review_claims(db_session)
    filters = (ChatQualityReviewQueueItem.status == status,)
    total = int(
        db_session.scalar(
            select(func.count(ChatQualityReviewQueueItem.id)).where(*filters)
        )
        or 0
    )
    queue_items = list(
        db_session.scalars(
            select(ChatQualityReviewQueueItem)
            .where(*filters)
            .options(
                selectinload(ChatQualityReviewQueueItem.chat_message).selectinload(
                    ChatMessage.parent_message
                )
            )
            .order_by(
                ChatQualityReviewQueueItem.priority.desc(),
                ChatQualityReviewQueueItem.time_created,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    message_ids = [item.chat_message_id for item in queue_items]
    evaluations = (
        list(
            db_session.scalars(
                select(ChatMessageQualityEvaluation).where(
                    ChatMessageQualityEvaluation.chat_message_id.in_(message_ids)
                )
            )
        )
        if message_ids
        else []
    )
    evaluation_map = {
        (evaluation.chat_message_id, evaluation.evaluation_source): (
            QualityEvaluation.model_validate(evaluation)
        )
        for evaluation in evaluations
    }
    entries: list[QualityReviewQueueEntry] = []
    for item in queue_items:
        message = item.chat_message
        human_evaluation = evaluation_map.get((item.chat_message_id, "human"))
        entries.append(
            QualityReviewQueueEntry(
                **QualityReviewQueueItemSnapshot.model_validate(item).model_dump(),
                session_id=message.chat_session_id,
                model_display_name=message.model_display_name,
                user_message=(
                    message.parent_message.message if message.parent_message else ""
                ),
                assistant_message=message.message,
                human_evaluation=human_evaluation,
                llm_evaluation=(
                    evaluation_map.get((item.chat_message_id, "llm_judge"))
                    if human_evaluation is not None
                    else None
                ),
            )
        )
    return QualityReviewQueuePage(
        total=total,
        page=page,
        page_size=page_size,
        items=entries,
    )


def claim_quality_review_queue_item(
    db_session: Session,
    *,
    queue_item_id: int,
    user_id: UUID,
    claim_duration: timedelta,
) -> QualityReviewQueueItemSnapshot:
    item = db_session.scalar(
        select(ChatQualityReviewQueueItem)
        .where(ChatQualityReviewQueueItem.id == queue_item_id)
        .with_for_update()
    )
    if item is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Review queue item not found.")
    now = datetime.now(timezone.utc)
    active_claim = (
        item.status == "claimed"
        and item.claim_expires_at is not None
        and item.claim_expires_at > now
    )
    if active_claim and item.assigned_user_id != user_id:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Review queue item is already claimed.")
    if item.status in {"completed", "skipped"}:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Review queue item is closed.")
    item.status = "claimed"
    item.assigned_user_id = user_id
    item.claim_expires_at = now + claim_duration
    db_session.commit()
    db_session.refresh(item)
    return QualityReviewQueueItemSnapshot.model_validate(item)


def release_quality_review_queue_item(
    db_session: Session, *, queue_item_id: int, user_id: UUID
) -> QualityReviewQueueItemSnapshot:
    item = db_session.scalar(
        select(ChatQualityReviewQueueItem)
        .where(ChatQualityReviewQueueItem.id == queue_item_id)
        .with_for_update()
    )
    if item is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Review queue item not found.")
    if item.status != "claimed" or item.assigned_user_id != user_id:
        raise OnyxError(OnyxErrorCode.CONFLICT, "You do not own this review claim.")
    item.status = "pending"
    item.assigned_user_id = None
    item.claim_expires_at = None
    db_session.commit()
    db_session.refresh(item)
    return QualityReviewQueueItemSnapshot.model_validate(item)


def skip_quality_review_queue_item(
    db_session: Session,
    *,
    queue_item_id: int,
    user_id: UUID,
    reason: str,
) -> QualityReviewQueueItemSnapshot:
    item = db_session.scalar(
        select(ChatQualityReviewQueueItem)
        .where(ChatQualityReviewQueueItem.id == queue_item_id)
        .with_for_update()
    )
    if item is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Review queue item not found.")
    if item.status == "claimed" and item.assigned_user_id != user_id:
        raise OnyxError(OnyxErrorCode.CONFLICT, "You do not own this review claim.")
    item.status = "skipped"
    item.assigned_user_id = user_id
    item.claim_expires_at = None
    item.skip_reason = reason
    item.completed_at = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(item)
    return QualityReviewQueueItemSnapshot.model_validate(item)


def complete_quality_review_queue_item(
    db_session: Session,
    *,
    chat_message_id: int,
    user_id: UUID,
    root_cause: str | None = None,
) -> None:
    db_session.execute(
        update(ChatQualityReviewQueueItem)
        .where(ChatQualityReviewQueueItem.chat_message_id == chat_message_id)
        .values(
            status="completed",
            assigned_user_id=user_id,
            claim_expires_at=None,
            root_cause=root_cause,
            completed_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()


def delete_quality_evaluation(
    db_session: Session,
    chat_message_id: int,
    evaluation_source: EvaluationSource = "human",
) -> None:
    deleted_id = db_session.scalar(
        delete(ChatMessageQualityEvaluation)
        .where(
            ChatMessageQualityEvaluation.chat_message_id == chat_message_id,
            ChatMessageQualityEvaluation.evaluation_source == evaluation_source,
        )
        .returning(ChatMessageQualityEvaluation.id)
    )
    if deleted_id is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Quality evaluation not found.")
    db_session.commit()


def fetch_quality_evaluation(
    db_session: Session,
    chat_message_id: int,
    evaluation_source: EvaluationSource = "human",
) -> QualityEvaluation | None:
    evaluation = db_session.scalar(
        select(ChatMessageQualityEvaluation).where(
            ChatMessageQualityEvaluation.chat_message_id == chat_message_id,
            ChatMessageQualityEvaluation.evaluation_source == evaluation_source,
        )
    )
    return QualityEvaluation.model_validate(evaluation) if evaluation else None


def fetch_quality_evaluations(
    db_session: Session, chat_message_id: int
) -> dict[EvaluationSource, QualityEvaluation]:
    evaluations = db_session.scalars(
        select(ChatMessageQualityEvaluation).where(
            ChatMessageQualityEvaluation.chat_message_id == chat_message_id
        )
    ).all()
    return {
        cast(EvaluationSource, evaluation.evaluation_source): (
            QualityEvaluation.model_validate(evaluation)
        )
        for evaluation in evaluations
    }


def preferred_evaluations_by_message(
    evaluations: list[ChatMessageQualityEvaluation],
) -> dict[int, ChatMessageQualityEvaluation]:
    by_message: dict[int, dict[str, ChatMessageQualityEvaluation]] = {}
    for evaluation in evaluations:
        by_message.setdefault(evaluation.chat_message_id, {})[
            evaluation.evaluation_source
        ] = evaluation
    return {
        message_id: source_rows.get("human") or source_rows["llm_judge"]
        for message_id, source_rows in by_message.items()
    }


def _paired_evaluation_metrics(
    evaluations: list[ChatMessageQualityEvaluation],
) -> tuple[int, KpiMetric, KpiMetric]:
    by_message: dict[int, dict[str, ChatMessageQualityEvaluation]] = {}
    for evaluation in evaluations:
        by_message.setdefault(evaluation.chat_message_id, {})[
            evaluation.evaluation_source
        ] = evaluation

    pairs = [
        (source_rows["human"], source_rows["llm_judge"])
        for source_rows in by_message.values()
        if "human" in source_rows and "llm_judge" in source_rows
    ]
    boolean_fields = (
        "task_success",
        "first_answer_resolution",
        "required_rephrase",
        "grounded",
        "hallucination_detected",
        "appropriate_refusal",
        "false_refusal",
    )
    boolean_results = [
        getattr(human, field) == getattr(judge, field)
        for human, judge in pairs
        for field in boolean_fields
        if getattr(human, field) is not None and getattr(judge, field) is not None
    ]
    score_fields = (
        "correctness",
        "relevance",
        "completeness",
        "clarity",
        "instruction_following",
        "citation_accuracy",
        "retrieval_relevance",
    )
    score_differences = [
        abs(cast(int, getattr(human, field)) - cast(int, getattr(judge, field)))
        for human, judge in pairs
        for field in score_fields
        if getattr(human, field) is not None and getattr(judge, field) is not None
    ]
    return (
        len(pairs),
        _rate(sum(boolean_results), len(boolean_results)),
        _score(
            sum(score_differences) / len(score_differences)
            if score_differences
            else None,
            len(score_differences),
        ),
    )


def _aggregate_boolean(values: list[bool | None]) -> KpiMetric:
    reviewed = [value for value in values if value is not None]
    return _rate(sum(value is True for value in reviewed), len(reviewed))


def _aggregate_score(values: list[int | None]) -> KpiMetric:
    reviewed = [value for value in values if value is not None]
    return _score(sum(reviewed) / len(reviewed) if reviewed else None, len(reviewed))


def _quality_scores(
    evaluations: list[ChatMessageQualityEvaluation],
) -> tuple[KpiMetric, KpiMetric, KpiMetric, KpiMetric, KpiMetric, KpiMetric]:
    complete = [
        evaluation
        for evaluation in evaluations
        if evaluation.correctness is not None
        and evaluation.relevance is not None
        and evaluation.completeness is not None
        and evaluation.clarity is not None
        and evaluation.instruction_following is not None
    ]
    quality_values = [
        weighted_answer_quality_score(
            cast(int, evaluation.correctness),
            cast(int, evaluation.relevance),
            cast(int, evaluation.completeness),
            cast(int, evaluation.clarity),
            cast(int, evaluation.instruction_following),
        )
        for evaluation in complete
    ]
    quality = _score(
        sum(quality_values) / len(quality_values) if quality_values else None,
        len(quality_values),
    )
    return (
        quality,
        _aggregate_score([evaluation.correctness for evaluation in evaluations]),
        _aggregate_score([evaluation.relevance for evaluation in evaluations]),
        _aggregate_score([evaluation.completeness for evaluation in evaluations]),
        _aggregate_score([evaluation.clarity for evaluation in evaluations]),
        _aggregate_score(
            [evaluation.instruction_following for evaluation in evaluations]
        ),
    )


def fetch_quality_kpi_overview(db_session: Session, days: int) -> QualityKpiOverview:
    cutoff = _cutoff(days)
    response_filter = (
        ChatMessage.time_sent >= cutoff,
        ChatMessage.message_type == MessageType.ASSISTANT,
        ChatSession.deleted.is_(False),
    )

    responses = db_session.execute(
        select(
            ChatMessage.id,
            ChatMessage.model_display_name,
            ChatMessage.error,
            ChatMessage.citations,
            ChatMessage.processing_duration_seconds,
        )
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(*response_filter)
    ).all()
    assistant_responses = len(responses)
    response_ids = [row.id for row in responses]

    all_evaluations = (
        list(
            db_session.scalars(
                select(ChatMessageQualityEvaluation).where(
                    ChatMessageQualityEvaluation.chat_message_id.in_(response_ids)
                )
            ).all()
        )
        if response_ids
        else []
    )
    evaluation_by_message = preferred_evaluations_by_message(all_evaluations)
    evaluations = list(evaluation_by_message.values())
    human_reviewed_responses = sum(
        evaluation.evaluation_source == "human" for evaluation in all_evaluations
    )
    llm_reviewed_responses = sum(
        evaluation.evaluation_source == "llm_judge" for evaluation in all_evaluations
    )
    paired_reviewed_responses, boolean_agreement, score_mean_absolute_error = (
        _paired_evaluation_metrics(all_evaluations)
    )
    review_status_counts = (
        dict(
            db_session.execute(
                select(
                    ChatQualityReviewQueueItem.status,
                    func.count(ChatQualityReviewQueueItem.id),
                )
                .where(ChatQualityReviewQueueItem.chat_message_id.in_(response_ids))
                .group_by(ChatQualityReviewQueueItem.status)
            ).all()
        )
        if response_ids
        else {}
    )
    failed_judge_jobs = (
        int(
            db_session.scalar(
                select(func.count(ChatQualityEvaluationJob.id)).where(
                    ChatQualityEvaluationJob.chat_message_id.in_(response_ids),
                    ChatQualityEvaluationJob.status == "failed",
                )
            )
            or 0
        )
        if response_ids
        else 0
    )

    latest_feedback_ids = (
        select(func.max(ChatMessageFeedback.id).label("id"))
        .where(ChatMessageFeedback.chat_message_id.in_(response_ids))
        .group_by(ChatMessageFeedback.chat_message_id)
    )
    feedback_values = (
        list(
            db_session.scalars(
                select(ChatMessageFeedback.is_positive).where(
                    ChatMessageFeedback.id.in_(latest_feedback_ids)
                )
            ).all()
        )
        if response_ids
        else []
    )
    rated_feedback = [value for value in feedback_values if value is not None]

    session_turn_rows = db_session.execute(
        select(
            ChatMessage.chat_session_id,
            func.count(ChatMessage.id),
        )
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(
            ChatMessage.time_sent >= cutoff,
            ChatMessage.message_type == MessageType.USER,
            ChatSession.deleted.is_(False),
        )
        .group_by(ChatMessage.chat_session_id)
    ).all()
    user_turn_counts = [int(row[1]) for row in session_turn_rows]

    durations = [
        float(row.processing_duration_seconds)
        for row in responses
        if row.processing_duration_seconds is not None
    ]
    sorted_durations = sorted(durations)
    p95_duration = (
        sorted_durations[max(0, int(len(sorted_durations) * 0.95 + 0.9999) - 1)]
        if sorted_durations
        else None
    )

    total_cost_cents = float(
        db_session.scalar(
            select(func.coalesce(func.sum(UserUsage.cost_cents), 0)).where(
                UserUsage.window_start >= cutoff
            )
        )
        or 0
    )

    task_success = _aggregate_boolean(
        [evaluation.task_success for evaluation in evaluations]
    )
    estimated_successes = (
        assistant_responses * task_success.value / 100
        if task_success.value is not None
        else 0
    )
    cost_per_success = _score(
        total_cost_cents / estimated_successes if estimated_successes else None,
        task_success.sample_size,
    )
    quality, correctness, relevance, completeness, clarity, instruction = (
        _quality_scores(evaluations)
    )

    safety_fields = (
        "harmful_response",
        "sensitive_data_leakage",
        "unauthorized_document_exposure",
        "policy_violation",
        "prompt_injection_succeeded",
    )
    safety_reviewed = sum(
        any(getattr(evaluation, field) is not None for field in safety_fields)
        for evaluation in evaluations
    )

    model_rows: list[ModelQualityRow] = []
    response_models = sorted({row.model_display_name or "unknown" for row in responses})
    for model in response_models:
        model_responses = [
            row for row in responses if (row.model_display_name or "unknown") == model
        ]
        model_evaluations = [
            evaluation_by_message[row.id]
            for row in model_responses
            if row.id in evaluation_by_message
        ]
        model_task_success = _aggregate_boolean(
            [evaluation.task_success for evaluation in model_evaluations]
        )
        model_quality = _quality_scores(model_evaluations)[0]
        model_hallucination = _aggregate_boolean(
            [evaluation.hallucination_detected for evaluation in model_evaluations]
        )
        model_durations = sorted(
            float(row.processing_duration_seconds)
            for row in model_responses
            if row.processing_duration_seconds is not None
        )
        model_p95 = (
            model_durations[max(0, int(len(model_durations) * 0.95 + 0.9999) - 1)]
            if model_durations
            else None
        )
        model_rows.append(
            ModelQualityRow(
                model=model,
                assistant_responses=len(model_responses),
                reviewed_responses=len(model_evaluations),
                task_success_rate=model_task_success.value,
                answer_quality_score=model_quality.value,
                hallucination_rate=model_hallucination.value,
                p95_response_seconds=model_p95,
            )
        )

    task_category_rows: list[TaskCategoryQualityRow] = []
    task_categories = sorted(
        {evaluation.task_category or "Uncategorized" for evaluation in evaluations}
    )
    for task_category in task_categories:
        category_evaluations = [
            evaluation
            for evaluation in evaluations
            if (evaluation.task_category or "Uncategorized") == task_category
        ]
        category_task_success = _aggregate_boolean(
            [evaluation.task_success for evaluation in category_evaluations]
        )
        category_quality = _quality_scores(category_evaluations)[0]
        category_hallucination = _aggregate_boolean(
            [evaluation.hallucination_detected for evaluation in category_evaluations]
        )
        task_category_rows.append(
            TaskCategoryQualityRow(
                task_category=task_category,
                reviewed_responses=len(category_evaluations),
                task_success_rate=category_task_success.value,
                answer_quality_score=category_quality.value,
                hallucination_rate=category_hallucination.value,
            )
        )

    return QualityKpiOverview(
        days=days,
        assistant_responses=assistant_responses,
        reviewed_responses=len(evaluations),
        human_reviewed_responses=human_reviewed_responses,
        llm_reviewed_responses=llm_reviewed_responses,
        paired_reviewed_responses=paired_reviewed_responses,
        boolean_agreement_rate=boolean_agreement,
        score_mean_absolute_error=score_mean_absolute_error,
        pending_review_items=int(review_status_counts.get("pending", 0)),
        claimed_review_items=int(review_status_counts.get("claimed", 0)),
        failed_judge_jobs=failed_judge_jobs,
        evaluation_coverage_rate=_rate(len(evaluations), assistant_responses),
        response_error_rate=_rate(
            sum(row.error is not None for row in responses), assistant_responses
        ),
        citation_coverage_rate=_rate(
            sum(bool(row.citations) for row in responses), assistant_responses
        ),
        feedback_coverage_rate=_rate(len(rated_feedback), assistant_responses),
        positive_feedback_rate=_rate(
            sum(value is True for value in rated_feedback), len(rated_feedback)
        ),
        average_response_seconds=_score(
            sum(durations) / len(durations) if durations else None, len(durations)
        ),
        p95_response_seconds=_score(p95_duration, len(durations)),
        average_user_turns_per_session=_score(
            sum(user_turn_counts) / len(user_turn_counts) if user_turn_counts else None,
            len(user_turn_counts),
        ),
        task_success_rate=task_success,
        first_answer_resolution_rate=_aggregate_boolean(
            [evaluation.first_answer_resolution for evaluation in evaluations]
        ),
        rephrase_rate=_aggregate_boolean(
            [evaluation.required_rephrase for evaluation in evaluations]
        ),
        answer_quality_score=quality,
        correctness_score=correctness,
        relevance_score=relevance,
        completeness_score=completeness,
        clarity_score=clarity,
        instruction_following_score=instruction,
        grounded_answer_rate=_aggregate_boolean(
            [evaluation.grounded for evaluation in evaluations]
        ),
        citation_accuracy_score=_aggregate_score(
            [evaluation.citation_accuracy for evaluation in evaluations]
        ),
        retrieval_relevance_score=_aggregate_score(
            [evaluation.retrieval_relevance for evaluation in evaluations]
        ),
        hallucination_rate=_aggregate_boolean(
            [evaluation.hallucination_detected for evaluation in evaluations]
        ),
        appropriate_refusal_rate=_aggregate_boolean(
            [evaluation.appropriate_refusal for evaluation in evaluations]
        ),
        false_refusal_rate=_aggregate_boolean(
            [evaluation.false_refusal for evaluation in evaluations]
        ),
        estimated_cost_per_success_cents=cost_per_success,
        safety=SafetyGuardrails(
            reviewed_responses=safety_reviewed,
            harmful_responses=sum(
                evaluation.harmful_response is True for evaluation in evaluations
            ),
            sensitive_data_leaks=sum(
                evaluation.sensitive_data_leakage is True for evaluation in evaluations
            ),
            unauthorized_document_exposures=sum(
                evaluation.unauthorized_document_exposure is True
                for evaluation in evaluations
            ),
            policy_violations=sum(
                evaluation.policy_violation is True for evaluation in evaluations
            ),
            successful_prompt_injections=sum(
                evaluation.prompt_injection_succeeded is True
                for evaluation in evaluations
            ),
        ),
        by_model=model_rows,
        by_task_category=task_category_rows,
    )
