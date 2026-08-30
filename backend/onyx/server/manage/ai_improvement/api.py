"""Admin API for versioned AI configuration changes and release gates."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.ai_improvement import (
    CanaryReleaseSnapshot,
    ConfigurationTargetType,
    ConfigurationVersionSnapshot,
    EvaluationDatasetCaseInput,
    EvaluationDatasetSnapshot,
    EvaluationRunSnapshot,
    ImprovementItemSnapshot,
    ImprovementTargetSnapshot,
    approve_configuration_version,
    create_configuration_candidate,
    create_evaluation_dataset,
    create_evaluation_run,
    create_improvement_item,
    freeze_evaluation_dataset,
    list_canary_releases,
    list_configuration_versions,
    list_evaluation_datasets,
    list_evaluation_runs,
    list_improvement_items,
    list_improvement_targets,
    promote_canary_release,
    start_canary_release,
    stop_canary_release,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import AICanaryRelease, AIConfigurationVersion, Skill, User
from onyx.quality.offline_eval import execute_evaluation_run
from onyx.skills.push import push_skill_to_affected_sandboxes

router = APIRouter(prefix="/manage/admin/ai-improvement")


def _user_id(user: User) -> UUID:
    if user.id is None:
        raise HTTPException(status_code=400, detail="User ID is missing.")
    return user.id


class CandidateRequest(BaseModel):
    target_type: ConfigurationTargetType
    target_id: str = Field(min_length=1, max_length=200)
    configuration: dict[str, Any]
    change_reason: str = Field(min_length=3, max_length=4000)


class ImprovementItemRequest(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=10_000)
    priority: int = Field(default=50, ge=0, le=100)
    source_message_ids: list[int] = Field(default_factory=list, max_length=100)
    root_cause: str | None = Field(default=None, max_length=250)
    target_type: str | None = Field(default=None, max_length=50)
    target_id: str | None = Field(default=None, max_length=200)
    expected_outcome: str | None = Field(default=None, max_length=10_000)


class DatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    description: str = Field(default="", max_length=4000)
    cases: list[EvaluationDatasetCaseInput] = Field(min_length=1, max_length=50)


class EvaluationRunRequest(BaseModel):
    candidate_version_id: int
    dataset_id: int


class CanaryRequest(BaseModel):
    version_id: int
    evaluation_run_id: int
    traffic_percentage: float = Field(gt=0, le=100)
    eligible_scope: dict[str, Any] = Field(default_factory=dict)


class StopCanaryRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


@router.get("/targets")
def get_targets(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[ImprovementTargetSnapshot]:
    return list_improvement_targets(db_session)


@router.get("/versions")
def get_versions(
    target_type: ConfigurationTargetType = Query(),
    target_id: str = Query(min_length=1, max_length=200),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[ConfigurationVersionSnapshot]:
    return list_configuration_versions(
        db_session, target_type=target_type, target_id=target_id
    )


@router.post("/versions")
def post_candidate(
    request: CandidateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ConfigurationVersionSnapshot:
    return create_configuration_candidate(
        db_session,
        target_type=request.target_type,
        target_id=request.target_id,
        configuration=request.configuration,
        change_reason=request.change_reason,
        user_id=_user_id(user),
    )


@router.post("/versions/{version_id}/approve")
def approve_candidate(
    version_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ConfigurationVersionSnapshot:
    return approve_configuration_version(
        db_session, version_id=version_id, user_id=_user_id(user)
    )


@router.get("/items")
def get_items(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[ImprovementItemSnapshot]:
    return list_improvement_items(db_session)


@router.post("/items")
def post_item(
    request: ImprovementItemRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ImprovementItemSnapshot:
    return create_improvement_item(
        db_session,
        owner_user_id=_user_id(user),
        **request.model_dump(),
    )


@router.get("/datasets")
def get_datasets(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[EvaluationDatasetSnapshot]:
    return list_evaluation_datasets(db_session)


@router.post("/datasets")
def post_dataset(
    request: DatasetRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvaluationDatasetSnapshot:
    return create_evaluation_dataset(
        db_session,
        name=request.name,
        description=request.description,
        cases=request.cases,
        user_id=_user_id(user),
    )


@router.post("/datasets/{dataset_id}/freeze")
def freeze_dataset(
    dataset_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvaluationDatasetSnapshot:
    return freeze_evaluation_dataset(db_session, dataset_id)


@router.get("/runs")
def get_runs(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[EvaluationRunSnapshot]:
    return list_evaluation_runs(db_session)


@router.post("/runs")
def post_run(
    request: EvaluationRunRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvaluationRunSnapshot:
    return create_evaluation_run(
        db_session,
        candidate_version_id=request.candidate_version_id,
        dataset_id=request.dataset_id,
    )


@router.post("/runs/{run_id}/execute")
def execute_run(
    run_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvaluationRunSnapshot:
    run = execute_evaluation_run(db_session, run_id)
    return EvaluationRunSnapshot.model_validate(run)


@router.get("/canaries")
def get_canaries(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[CanaryReleaseSnapshot]:
    return list_canary_releases(db_session)


@router.post("/canaries")
def post_canary(
    request: CanaryRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CanaryReleaseSnapshot:
    return start_canary_release(
        db_session,
        user_id=_user_id(user),
        **request.model_dump(),
    )


@router.post("/canaries/{canary_id}/stop")
def stop_canary(
    canary_id: int,
    request: StopCanaryRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CanaryReleaseSnapshot:
    return stop_canary_release(db_session, canary_id=canary_id, reason=request.reason)


@router.post("/canaries/{canary_id}/promote")
def promote_canary(
    canary_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CanaryReleaseSnapshot:
    canary = db_session.get(AICanaryRelease, canary_id)
    candidate = (
        db_session.get(AIConfigurationVersion, canary.candidate_version_id)
        if canary
        else None
    )
    result = promote_canary_release(db_session, canary_id=canary_id)
    if candidate is not None and candidate.target_type != "agent":
        skill = db_session.get(Skill, UUID(candidate.target_id))
        if skill is not None:
            push_skill_to_affected_sandboxes(skill, db_session)
    return result
