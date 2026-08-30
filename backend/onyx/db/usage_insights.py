"""Read-only aggregations for the CE Usage Report admin page.

All data comes from CE tables: chat_session / chat_message (activity),
user_usage (token + cost ledger), chat_feedback (ratings).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from onyx.configs.constants import MessageType
from onyx.db.chat_quality import QualityEvaluation, weighted_answer_quality_score
from onyx.db.models import (
    ChatMessage,
    ChatMessageFeedback,
    ChatMessageQualityEvaluation,
    ChatSession,
    Persona,
    User,
    UserUsage,
)


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# === Overview ===


class DailyActivity(BaseModel):
    date: str
    messages: int
    sessions: int
    active_users: int


class ModelUsageRow(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost_cents: float


class UserUsageRow(BaseModel):
    email: str
    input_tokens: int
    output_tokens: int
    cost_cents: float


class UsageOverview(BaseModel):
    days: int
    total_messages: int
    total_sessions: int
    active_users: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cents: float
    feedback_positive: int
    feedback_negative: int
    daily: list[DailyActivity]
    by_model: list[ModelUsageRow]
    by_user: list[UserUsageRow]


def fetch_usage_overview(db_session: Session, days: int) -> UsageOverview:
    cutoff = _cutoff(days)

    day_col = cast(ChatMessage.time_sent, Date)
    daily_rows = db_session.execute(
        select(
            day_col.label("day"),
            func.count(ChatMessage.id),
            func.count(func.distinct(ChatMessage.chat_session_id)),
            func.count(func.distinct(ChatSession.user_id)),
        )
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(
            ChatMessage.time_sent >= cutoff,
            ChatMessage.message_type == MessageType.USER,
            ChatSession.deleted.is_(False),
        )
        .group_by(day_col)
        .order_by(day_col)
    ).all()

    daily = [
        DailyActivity(
            date=str(day),
            messages=messages,
            sessions=sessions,
            active_users=users,
        )
        for day, messages, sessions, users in daily_rows
    ]

    total_messages = sum(d.messages for d in daily)
    total_sessions_row = db_session.scalar(
        select(func.count(ChatSession.id)).where(
            ChatSession.time_created >= cutoff, ChatSession.deleted.is_(False)
        )
    )
    active_users_row = db_session.scalar(
        select(func.count(func.distinct(ChatSession.user_id))).where(
            ChatSession.time_created >= cutoff, ChatSession.deleted.is_(False)
        )
    )

    token_totals = db_session.execute(
        select(
            func.coalesce(func.sum(UserUsage.input_tokens), 0),
            func.coalesce(func.sum(UserUsage.output_tokens), 0),
            func.coalesce(func.sum(UserUsage.cost_cents), 0),
        ).where(UserUsage.window_start >= cutoff)
    ).one()

    feedback = db_session.execute(
        select(ChatMessageFeedback.is_positive, func.count(ChatMessageFeedback.id))
        .join(ChatMessage, ChatMessage.id == ChatMessageFeedback.chat_message_id)
        .where(ChatMessage.time_sent >= cutoff)
        .group_by(ChatMessageFeedback.is_positive)
    ).all()
    feedback_map = {bool(k): v for k, v in feedback if k is not None}

    by_model_rows = db_session.execute(
        select(
            UserUsage.model,
            func.sum(UserUsage.input_tokens),
            func.sum(UserUsage.output_tokens),
            func.sum(UserUsage.cost_cents),
        )
        .where(UserUsage.window_start >= cutoff)
        .group_by(UserUsage.model)
        .order_by(func.sum(UserUsage.cost_cents).desc())
        .limit(10)
    ).all()

    by_user_rows = db_session.execute(
        select(  # ty: ignore[no-matching-overload]
            User.email,
            func.sum(UserUsage.input_tokens),
            func.sum(UserUsage.output_tokens),
            func.sum(UserUsage.cost_cents),
        )
        .join(User, User.id == UserUsage.user_id)
        .where(UserUsage.window_start >= cutoff)
        .group_by(User.email)
        .order_by(func.sum(UserUsage.cost_cents).desc())
        .limit(10)
    ).all()

    return UsageOverview(
        days=days,
        total_messages=total_messages,
        total_sessions=total_sessions_row or 0,
        active_users=active_users_row or 0,
        total_input_tokens=int(token_totals[0]),
        total_output_tokens=int(token_totals[1]),
        total_cost_cents=float(token_totals[2]),
        feedback_positive=feedback_map.get(True, 0),
        feedback_negative=feedback_map.get(False, 0),
        daily=daily,
        by_model=[
            ModelUsageRow(
                model=model or "unknown",
                input_tokens=int(inp),
                output_tokens=int(out),
                cost_cents=float(cost),
            )
            for model, inp, out, cost in by_model_rows
        ],
        by_user=[
            UserUsageRow(
                email=email,
                input_tokens=int(inp),
                output_tokens=int(out),
                cost_cents=float(cost),
            )
            for email, inp, out, cost in by_user_rows
        ],
    )


# === Chat history ===


class ChatHistoryEntry(BaseModel):
    session_id: UUID
    time_created: datetime
    user_email: str | None
    persona_name: str | None
    description: str | None
    message_count: int


class ChatHistoryPage(BaseModel):
    total: int
    page: int
    page_size: int
    entries: list[ChatHistoryEntry]


def fetch_chat_history(
    db_session: Session,
    days: int,
    page: int,
    page_size: int,
    search: str | None,
) -> ChatHistoryPage:
    cutoff = _cutoff(days)

    base = (
        select(ChatSession)
        .where(ChatSession.time_created >= cutoff, ChatSession.deleted.is_(False))
        .order_by(ChatSession.time_created.desc())
    )
    if search:
        base = base.where(ChatSession.description.ilike(f"%{search}%"))

    total = db_session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )

    sessions = list(
        db_session.scalars(base.offset((page - 1) * page_size).limit(page_size)).all()
    )

    session_ids = [s.id for s in sessions]
    counts: dict[UUID, int] = {}
    if session_ids:
        count_rows = db_session.execute(
            select(ChatMessage.chat_session_id, func.count(ChatMessage.id))
            .where(
                ChatMessage.chat_session_id.in_(session_ids),
                ChatMessage.message_type != MessageType.SYSTEM,
            )
            .group_by(ChatMessage.chat_session_id)
        ).all()
        counts = {sid: c for sid, c in count_rows}

    user_map: dict[UUID, str] = {}
    user_ids = [s.user_id for s in sessions if s.user_id]
    if user_ids:
        user_rows = db_session.execute(
            select(User.id, User.email).where(User.id.in_(user_ids))  # ty: ignore[no-matching-overload, unresolved-attribute]
        ).all()
        user_map = {uid: email for uid, email in user_rows}

    persona_map: dict[int, str] = {}
    persona_ids = [s.persona_id for s in sessions if s.persona_id is not None]
    if persona_ids:
        persona_rows = db_session.execute(
            select(Persona.id, Persona.name).where(Persona.id.in_(persona_ids))
        ).all()
        persona_map = {pid: name for pid, name in persona_rows}

    return ChatHistoryPage(
        total=total or 0,
        page=page,
        page_size=page_size,
        entries=[
            ChatHistoryEntry(
                session_id=s.id,
                time_created=s.time_created,
                user_email=user_map.get(s.user_id) if s.user_id else None,
                persona_name=(
                    persona_map.get(s.persona_id) if s.persona_id is not None else None
                ),
                description=s.description,
                message_count=counts.get(s.id, 0),
            )
            for s in sessions
        ],
    )


class ChatHistoryMessage(BaseModel):
    id: int
    message_type: MessageType
    time_sent: datetime
    message: str
    token_count: int
    model_display_name: str | None
    processing_duration_seconds: float | None
    error: str | None
    citation_count: int
    feedback: bool | None
    quality_evaluation: QualityEvaluation | None
    human_quality_evaluation: QualityEvaluation | None
    llm_quality_evaluation: QualityEvaluation | None
    selected_quality_evaluation: QualityEvaluation | None


def fetch_session_messages(
    db_session: Session, session_id: UUID
) -> list[ChatHistoryMessage]:
    messages = db_session.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.chat_session_id == session_id,
            ChatMessage.message_type != MessageType.SYSTEM,
        )
        .order_by(ChatMessage.id)
    ).all()
    message_ids = [message.id for message in messages]
    evaluations = (
        db_session.scalars(
            select(ChatMessageQualityEvaluation).where(
                ChatMessageQualityEvaluation.chat_message_id.in_(message_ids)
            )
        ).all()
        if message_ids
        else []
    )
    evaluation_map = {
        (evaluation.chat_message_id, evaluation.evaluation_source): (
            QualityEvaluation.model_validate(evaluation)
        )
        for evaluation in evaluations
    }
    latest_feedback_ids = (
        select(func.max(ChatMessageFeedback.id).label("id"))
        .where(ChatMessageFeedback.chat_message_id.in_(message_ids))
        .group_by(ChatMessageFeedback.chat_message_id)
    )
    feedback_rows = (
        db_session.execute(
            select(
                ChatMessageFeedback.chat_message_id,
                ChatMessageFeedback.is_positive,
            ).where(ChatMessageFeedback.id.in_(latest_feedback_ids))
        ).all()
        if message_ids
        else []
    )
    feedback_map = {
        message_id: is_positive for message_id, is_positive in feedback_rows
    }
    return [
        ChatHistoryMessage(
            id=m.id,
            message_type=m.message_type,
            time_sent=m.time_sent,
            message=m.message or "",
            token_count=m.token_count,
            model_display_name=m.model_display_name,
            processing_duration_seconds=m.processing_duration_seconds,
            error=m.error,
            citation_count=len(m.citations or {}),
            feedback=feedback_map.get(m.id),
            quality_evaluation=evaluation_map.get((m.id, "human")),
            human_quality_evaluation=evaluation_map.get((m.id, "human")),
            llm_quality_evaluation=evaluation_map.get((m.id, "llm_judge")),
            selected_quality_evaluation=evaluation_map.get((m.id, "human"))
            or evaluation_map.get((m.id, "llm_judge")),
        )
        for m in messages
        if m.message
    ]


# === CSV export ===

EXPORT_HEADER = [
    "time_sent",
    "user_email",
    "persona",
    "message_type",
    "token_count",
    "model",
    "processing_duration_seconds",
    "error",
    "citation_count",
    "feedback",
    "evaluation_source",
    "task_category",
    "task_success",
    "first_answer_resolution",
    "required_rephrase",
    "answer_quality_score",
    "correctness",
    "relevance",
    "completeness",
    "clarity",
    "instruction_following",
    "grounded",
    "citation_accuracy",
    "retrieval_relevance",
    "hallucination_detected",
    "appropriate_refusal",
    "false_refusal",
    "harmful_response",
    "sensitive_data_leakage",
    "unauthorized_document_exposure",
    "policy_violation",
    "prompt_injection_succeeded",
    "evaluation_notes",
    "message",
]


def iter_export_rows(db_session: Session, days: int) -> list[list[str]]:
    cutoff = _cutoff(days)
    latest_feedback = (
        select(ChatMessageFeedback.is_positive)
        .where(ChatMessageFeedback.chat_message_id == ChatMessage.id)
        .order_by(ChatMessageFeedback.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    preferred_evaluation_id = (
        select(ChatMessageQualityEvaluation.id)
        .where(ChatMessageQualityEvaluation.chat_message_id == ChatMessage.id)
        .order_by(
            case(
                (ChatMessageQualityEvaluation.evaluation_source == "human", 0),
                else_=1,
            )
        )
        .limit(1)
        .correlate(ChatMessage)
        .scalar_subquery()
    )
    rows = db_session.execute(
        select(
            ChatMessage.time_sent,
            User.email,  # ty: ignore[invalid-argument-type]
            Persona.name,
            ChatMessage.message_type,
            ChatMessage.token_count,
            ChatMessage.model_display_name,
            ChatMessage.processing_duration_seconds,
            ChatMessage.error,
            ChatMessage.citations,
            latest_feedback,
            ChatMessageQualityEvaluation,
            ChatMessage.message,
        )
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .join(User, User.id == ChatSession.user_id, isouter=True)
        .join(Persona, Persona.id == ChatSession.persona_id, isouter=True)
        .join(
            ChatMessageQualityEvaluation,
            ChatMessageQualityEvaluation.id == preferred_evaluation_id,
            isouter=True,
        )
        .where(
            ChatMessage.time_sent >= cutoff,
            ChatMessage.message_type != MessageType.SYSTEM,
            ChatSession.deleted.is_(False),
        )
        .order_by(ChatMessage.time_sent)
    ).all()

    return [
        format_export_row(
            time_sent,
            email,
            persona,
            mtype,
            tokens,
            model,
            message,
            processing_duration_seconds=duration,
            error=error,
            citation_count=len(citations or {}),
            feedback=feedback,
            evaluation=evaluation,
        )
        for (
            time_sent,
            email,
            persona,
            mtype,
            tokens,
            model,
            duration,
            error,
            citations,
            feedback,
            evaluation,
            message,
        ) in rows
        if message
    ]


def format_export_row(
    time_sent: datetime,
    email: str | None,
    persona: str | None,
    message_type: MessageType | str,
    token_count: int | None,
    model: str | None,
    message: str | None,
    *,
    processing_duration_seconds: float | None = None,
    error: str | None = None,
    citation_count: int = 0,
    feedback: bool | None = None,
    evaluation: ChatMessageQualityEvaluation | None = None,
) -> list[str]:
    """One CSV row; message truncated so exports stay readable."""
    type_value = (
        message_type.value
        if isinstance(message_type, MessageType)
        else str(message_type)
    )
    text = (message or "").replace("\r\n", "\n")
    if len(text) > 2000:
        text = text[:2000] + "…"

    def optional(value: object | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    answer_quality_score: float | None = None
    if (
        evaluation
        and evaluation.correctness is not None
        and evaluation.relevance is not None
        and evaluation.completeness is not None
        and evaluation.clarity is not None
        and evaluation.instruction_following is not None
    ):
        answer_quality_score = weighted_answer_quality_score(
            evaluation.correctness,
            evaluation.relevance,
            evaluation.completeness,
            evaluation.clarity,
            evaluation.instruction_following,
        )
    return [
        time_sent.isoformat(),
        email or "",
        persona or "",
        type_value,
        str(token_count or 0),
        model or "",
        optional(processing_duration_seconds),
        error or "",
        str(citation_count),
        optional(feedback),
        optional(evaluation.evaluation_source if evaluation else None),
        optional(evaluation.task_category if evaluation else None),
        optional(evaluation.task_success if evaluation else None),
        optional(evaluation.first_answer_resolution if evaluation else None),
        optional(evaluation.required_rephrase if evaluation else None),
        optional(answer_quality_score),
        optional(evaluation.correctness if evaluation else None),
        optional(evaluation.relevance if evaluation else None),
        optional(evaluation.completeness if evaluation else None),
        optional(evaluation.clarity if evaluation else None),
        optional(evaluation.instruction_following if evaluation else None),
        optional(evaluation.grounded if evaluation else None),
        optional(evaluation.citation_accuracy if evaluation else None),
        optional(evaluation.retrieval_relevance if evaluation else None),
        optional(evaluation.hallucination_detected if evaluation else None),
        optional(evaluation.appropriate_refusal if evaluation else None),
        optional(evaluation.false_refusal if evaluation else None),
        optional(evaluation.harmful_response if evaluation else None),
        optional(evaluation.sensitive_data_leakage if evaluation else None),
        optional(evaluation.unauthorized_document_exposure if evaluation else None),
        optional(evaluation.policy_violation if evaluation else None),
        optional(evaluation.prompt_injection_succeeded if evaluation else None),
        optional(evaluation.notes if evaluation else None),
        text,
    ]
