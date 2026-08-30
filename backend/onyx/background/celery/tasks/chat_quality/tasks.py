"""Celery tasks for automatic assistant-response quality evaluation."""

from datetime import timedelta
from typing import Any

from celery import Task, shared_task

from onyx.configs.app_configs import (
    CHAT_QUALITY_BATCH_SIZE,
    CHAT_QUALITY_DAILY_LIMIT,
    CHAT_QUALITY_EXTERNAL_PROCESSING_APPROVED,
    CHAT_QUALITY_HIGH_RISK_CATEGORIES,
    CHAT_QUALITY_HUMAN_SAMPLE_RATE,
    CHAT_QUALITY_JOB_STALE_SECONDS,
    CHAT_QUALITY_JUDGE_VERSION,
    CHAT_QUALITY_LOOKBACK_DAYS,
    CHAT_QUALITY_MAX_ATTEMPTS,
    CHAT_QUALITY_REQUEST_TIMEOUT_SECONDS,
    CHAT_QUALITY_RUBRIC_VERSION,
    ENABLE_CHAT_QUALITY_JUDGE,
)
from onyx.configs.constants import (
    OnyxCeleryPriority,
    OnyxCeleryQueues,
    OnyxCeleryTask,
)
from onyx.db.chat_quality import (
    claim_quality_evaluation_job,
    complete_quality_evaluation_job,
    create_quality_evaluation_jobs,
    ensure_quality_review_queue_item,
    fail_quality_evaluation_job,
    fetch_dispatchable_quality_job_ids,
    fetch_quality_review_candidates,
    remaining_quality_evaluation_daily_capacity,
    upsert_quality_evaluation,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.llm.factory import get_default_llm
from onyx.quality.judge import evaluate_response_with_llm_judge
from onyx.utils.logger import setup_logger

logger = setup_logger()

EVALUATION_TASK_EXPIRES_SECONDS = 60 * 60


def _automation_enabled() -> bool:
    return ENABLE_CHAT_QUALITY_JUDGE and CHAT_QUALITY_EXTERNAL_PROCESSING_APPROVED


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CHAT_QUALITY_DISPATCH,
    ignore_result=True,
)
def dispatch_chat_quality_evaluations(**_: Any) -> None:
    if not _automation_enabled():
        logger.info("Chat quality evaluation is disabled.")
        return

    with get_session_with_current_tenant() as db_session:
        remaining_capacity = remaining_quality_evaluation_daily_capacity(
            db_session, CHAT_QUALITY_DAILY_LIMIT
        )
        create_quality_evaluation_jobs(
            db_session,
            days=CHAT_QUALITY_LOOKBACK_DAYS,
            limit=min(CHAT_QUALITY_BATCH_SIZE, remaining_capacity),
            judge_version=CHAT_QUALITY_JUDGE_VERSION,
        )
        job_ids = fetch_dispatchable_quality_job_ids(
            db_session,
            limit=min(CHAT_QUALITY_BATCH_SIZE, remaining_capacity),
            max_attempts=CHAT_QUALITY_MAX_ATTEMPTS,
            stale_after=timedelta(seconds=CHAT_QUALITY_JOB_STALE_SECONDS),
        )

    for job_id in job_ids:
        evaluate_chat_quality_response.apply_async(
            kwargs={"job_id": job_id},
            queue=OnyxCeleryQueues.QUALITY_EVALUATION,
            priority=OnyxCeleryPriority.LOW,
            expires=EVALUATION_TASK_EXPIRES_SECONDS,
        )
    logger.info("Dispatched %s chat quality evaluation jobs.", len(job_ids))


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CHAT_QUALITY_EVALUATE,
    ignore_result=True,
    bind=True,
    max_retries=CHAT_QUALITY_MAX_ATTEMPTS - 1,
)
def evaluate_chat_quality_response(self: Task, *, job_id: int) -> None:
    if not _automation_enabled():
        logger.warning(
            "Chat quality job %s skipped because automation is disabled.", job_id
        )
        return

    with get_session_with_current_tenant() as db_session:
        job = claim_quality_evaluation_job(
            db_session,
            job_id=job_id,
            max_attempts=CHAT_QUALITY_MAX_ATTEMPTS,
            stale_after=timedelta(seconds=CHAT_QUALITY_JOB_STALE_SECONDS),
        )
        if job is None:
            return
        candidates = fetch_quality_review_candidates(
            db_session,
            days=CHAT_QUALITY_LOOKBACK_DAYS,
            limit=1,
            chat_message_id=job.chat_message_id,
        )
        if not candidates:
            complete_quality_evaluation_job(db_session, job_id)
            return

    try:
        llm = get_default_llm(
            timeout=CHAT_QUALITY_REQUEST_TIMEOUT_SECONDS,
            temperature=0,
        )
        evaluation = evaluate_response_with_llm_judge(
            candidates[0],
            llm,
            judge_model=f"{llm.config.model_provider}/{llm.config.model_name}",
            judge_version=CHAT_QUALITY_JUDGE_VERSION,
            rubric_version=CHAT_QUALITY_RUBRIC_VERSION,
        )
        with get_session_with_current_tenant() as db_session:
            upsert_quality_evaluation(
                db_session=db_session,
                chat_message_id=job.chat_message_id,
                reviewer_user_id=None,
                evaluation_input=evaluation,
            )
            ensure_quality_review_queue_item(
                db_session,
                chat_message_id=job.chat_message_id,
                evaluation=evaluation,
                sample_rate=CHAT_QUALITY_HUMAN_SAMPLE_RATE,
                high_risk_categories=CHAT_QUALITY_HIGH_RISK_CATEGORIES,
            )
            complete_quality_evaluation_job(db_session, job_id)
    except Exception as error:
        logger.exception("Chat quality evaluation job %s failed.", job_id)
        with get_session_with_current_tenant() as db_session:
            fail_quality_evaluation_job(
                db_session,
                job_id=job_id,
                error=str(error),
                max_attempts=CHAT_QUALITY_MAX_ATTEMPTS,
            )
        if job.attempts < CHAT_QUALITY_MAX_ATTEMPTS:
            raise self.retry(
                exc=error,
                countdown=min(300, 30 * (2 ** (job.attempts - 1))),
            )
        raise
