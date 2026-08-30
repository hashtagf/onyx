"""Database operations for controlled AI configuration improvement."""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from onyx.db.models import (
    AICanaryRelease,
    AIConfigurationVersion,
    AIEvaluationDataset,
    AIEvaluationDatasetCase,
    AIEvaluationRun,
    AIImprovementItem,
    ChatMessage,
    ChatMessageQualityEvaluation,
    Document,
    DocumentSet,
    HierarchyNode,
    Persona,
    Skill,
    Tool,
    UserFile,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.content import (
    read_builtin_skill_instructions,
    read_custom_skill_bundle_instructions,
)

ConfigurationTargetType = Literal["agent", "custom_skill", "builtin_skill"]

AGENT_CONFIGURATION_FIELDS = {
    "system_prompt",
    "task_prompt",
    "replace_base_system_prompt",
    "datetime_aware",
    "default_model_configuration_id",
    "tool_ids",
    "document_set_ids",
    "user_file_ids",
    "hierarchy_node_ids",
    "document_ids",
}
SKILL_CONFIGURATION_FIELDS = {"description", "instructions_markdown"}
SECRET_KEY_PATTERN = re.compile(
    r"(^|_)(api_key|secret|password|token|credential|private_key)($|_)", re.I
)


class ConfigurationVersionSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: ConfigurationTargetType
    target_id: str
    version_number: int
    status: str
    base_version_id: int | None
    runtime_persona_id: int | None
    configuration: dict[str, Any]
    source_hash: str | None
    change_reason: str
    created_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    activated_at: datetime | None
    time_created: datetime


class ImprovementTargetSnapshot(BaseModel):
    target_type: ConfigurationTargetType
    target_id: str
    name: str
    description: str
    production_version: ConfigurationVersionSnapshot


class ImprovementItemSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    root_cause: str | None
    priority: int
    owner_user_id: UUID | None
    target_type: str | None
    target_id: str | None
    source_message_ids: list[int]
    expected_outcome: str | None
    time_created: datetime
    time_updated: datetime


class EvaluationDatasetCaseInput(BaseModel):
    input_text: str = Field(min_length=1, max_length=20_000)
    expected_outcome: str | None = Field(default=None, max_length=20_000)
    task_category: str | None = Field(default=None, max_length=100)
    source_message_id: int | None = None


class EvaluationDatasetSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    version: int
    status: str
    created_by_user_id: UUID | None
    time_created: datetime
    case_count: int = 0


class EvaluationRunSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_version_id: int
    baseline_version_id: int
    dataset_id: int
    status: str
    gates_passed: bool | None
    summary: dict[str, Any]
    time_created: datetime
    time_completed: datetime | None


class CanaryReleaseSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_version_id: int
    baseline_version_id: int
    evaluation_run_id: int
    traffic_percentage: float
    eligible_scope: dict[str, Any]
    status: str
    approved_by_user_id: UUID | None
    automatic_stop_reason: str | None
    time_started: datetime | None
    time_stopped: datetime | None


def _configuration_hash(configuration: dict[str, Any]) -> str:
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_no_secrets(value: Any, path: str = "configuration") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_PATTERN.search(str(key)):
                raise OnyxError(
                    OnyxErrorCode.INVALID_INPUT,
                    f"Secrets are not allowed in {path}.{key}.",
                )
            _validate_no_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_no_secrets(child, f"{path}[{index}]")


def _agent_configuration(persona: Persona) -> dict[str, Any]:
    return {
        "system_prompt": persona.system_prompt or "",
        "task_prompt": persona.task_prompt or "",
        "replace_base_system_prompt": persona.replace_base_system_prompt,
        "datetime_aware": persona.datetime_aware,
        "default_model_configuration_id": persona.default_model_configuration_id,
        "tool_ids": sorted(tool.id for tool in persona.tools),
        "document_set_ids": sorted(
            document_set.id for document_set in persona.document_sets
        ),
        "user_file_ids": sorted(str(user_file.id) for user_file in persona.user_files),
        "hierarchy_node_ids": sorted(node.id for node in persona.hierarchy_nodes),
        "document_ids": sorted(document.id for document in persona.attached_documents),
    }


def _skill_source_hash(skill: Skill) -> str:
    if skill.bundle_sha256:
        return skill.bundle_sha256
    if skill.built_in_skill_id is None:
        return _configuration_hash({"skill_id": str(skill.id)})
    definition = BUILT_IN_SKILLS[skill.built_in_skill_id]
    digest = hashlib.sha256()
    for path in sorted(definition.source_dir.rglob("*")):
        if path.is_file():
            relative_path = path.relative_to(definition.source_dir).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(relative_path).to_bytes(8))
            digest.update(relative_path)
            digest.update(len(content).to_bytes(8))
            digest.update(content)
    return digest.hexdigest()


def _skill_configuration(skill: Skill) -> dict[str, Any]:
    if skill.built_in_skill_id is not None:
        instructions = read_builtin_skill_instructions(
            BUILT_IN_SKILLS[skill.built_in_skill_id]
        )
    else:
        instructions = read_custom_skill_bundle_instructions(skill)
    return {
        "description": skill.description,
        "instructions_markdown": instructions,
    }


def _load_agent(db_session: Session, persona_id: int) -> Persona:
    persona = db_session.scalar(
        select(Persona)
        .where(Persona.id == persona_id, Persona.deleted.is_(False))
        .options(
            selectinload(Persona.tools),
            selectinload(Persona.document_sets),
            selectinload(Persona.user_files),
            selectinload(Persona.hierarchy_nodes),
            selectinload(Persona.attached_documents),
        )
    )
    if persona is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Agent not found.")
    return persona


def _production_version(
    db_session: Session, target_type: ConfigurationTargetType, target_id: str
) -> AIConfigurationVersion | None:
    return db_session.scalar(
        select(AIConfigurationVersion).where(
            AIConfigurationVersion.target_type == target_type,
            AIConfigurationVersion.target_id == target_id,
            AIConfigurationVersion.status == "production",
        )
    )


def ensure_production_configuration_version(
    db_session: Session,
    *,
    target_type: ConfigurationTargetType,
    target_id: str,
) -> ConfigurationVersionSnapshot:
    existing = _production_version(db_session, target_type, target_id)
    if existing is not None:
        return ConfigurationVersionSnapshot.model_validate(existing)

    runtime_persona_id: int | None = None
    if target_type == "agent":
        persona = _load_agent(db_session, int(target_id))
        configuration = _agent_configuration(persona)
        source_hash = _configuration_hash(configuration)
        runtime_persona_id = persona.id
    else:
        skill = db_session.get(Skill, UUID(target_id))
        if skill is None:
            raise OnyxError(OnyxErrorCode.NOT_FOUND, "Skill not found.")
        expected_type = (
            "builtin_skill" if skill.built_in_skill_id is not None else "custom_skill"
        )
        if expected_type != target_type:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT, "Skill target type is invalid."
            )
        configuration = _skill_configuration(skill)
        source_hash = _skill_source_hash(skill)

    version = AIConfigurationVersion(
        target_type=target_type,
        target_id=target_id,
        version_number=1,
        status="production",
        runtime_persona_id=runtime_persona_id,
        configuration=configuration,
        source_hash=source_hash,
        change_reason="Initial production configuration.",
        activated_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return ConfigurationVersionSnapshot.model_validate(version)


def list_improvement_targets(db_session: Session) -> list[ImprovementTargetSnapshot]:
    targets: list[ImprovementTargetSnapshot] = []
    personas = list(
        db_session.scalars(
            select(Persona)
            .where(
                Persona.deleted.is_(False),
                ~Persona.name.startswith("__ai_candidate__"),
            )
            .order_by(Persona.name)
        )
    )
    for persona in personas:
        version = ensure_production_configuration_version(
            db_session, target_type="agent", target_id=str(persona.id)
        )
        targets.append(
            ImprovementTargetSnapshot(
                target_type="agent",
                target_id=str(persona.id),
                name=persona.name,
                description=persona.description,
                production_version=version,
            )
        )

    skills = list(db_session.scalars(select(Skill).order_by(Skill.name)))
    for skill in skills:
        target_type: ConfigurationTargetType = (
            "builtin_skill" if skill.built_in_skill_id is not None else "custom_skill"
        )
        version = ensure_production_configuration_version(
            db_session, target_type=target_type, target_id=str(skill.id)
        )
        targets.append(
            ImprovementTargetSnapshot(
                target_type=target_type,
                target_id=str(skill.id),
                name=skill.name,
                description=skill.description,
                production_version=version,
            )
        )
    return targets


def _validate_configuration(
    target_type: ConfigurationTargetType, configuration: dict[str, Any]
) -> None:
    _validate_no_secrets(configuration)
    allowed_fields = (
        AGENT_CONFIGURATION_FIELDS
        if target_type == "agent"
        else SKILL_CONFIGURATION_FIELDS
    )
    unknown_fields = set(configuration) - allowed_fields
    if unknown_fields:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Unsupported configuration fields: {', '.join(sorted(unknown_fields))}.",
        )
    if target_type == "agent" and set(configuration) != AGENT_CONFIGURATION_FIELDS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT, "Agent configuration is incomplete."
        )
    if target_type != "agent" and set(configuration) != SKILL_CONFIGURATION_FIELDS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT, "Skill configuration is incomplete."
        )
    serialized_size = len(json.dumps(configuration).encode())
    if serialized_size > 2_000_000:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Configuration is too large.")


def _load_entities_by_ids(
    db_session: Session, model: type[Any], identifiers: list[Any], label: str
) -> list[Any]:
    if not identifiers:
        return []
    rows = list(db_session.scalars(select(model).where(model.id.in_(identifiers))))
    if len(rows) != len(set(identifiers)):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT, f"One or more {label} are invalid."
        )
    return rows


def _create_runtime_persona(
    db_session: Session,
    *,
    target: Persona,
    configuration: dict[str, Any],
    version_number: int,
) -> Persona:
    runtime = Persona(
        user_id=target.user_id,
        owner_group_id=target.owner_group_id,
        name=f"__ai_candidate__{target.id}__v{version_number}",
        description=f"Runtime candidate for {target.name}",
        default_model_configuration_id=configuration["default_model_configuration_id"],
        starter_messages=target.starter_messages,
        search_start_date=target.search_start_date,
        builtin_persona=False,
        is_featured=False,
        is_listed=False,
        display_priority=None,
        deleted=False,
        system_prompt=configuration["system_prompt"],
        replace_base_system_prompt=configuration["replace_base_system_prompt"],
        task_prompt=configuration["task_prompt"],
        datetime_aware=configuration["datetime_aware"],
        is_public=False,
        public_permission=target.public_permission,
    )
    runtime.tools = _load_entities_by_ids(
        db_session, Tool, configuration["tool_ids"], "tools"
    )
    runtime.document_sets = _load_entities_by_ids(
        db_session, DocumentSet, configuration["document_set_ids"], "document sets"
    )
    runtime.user_files = _load_entities_by_ids(
        db_session,
        UserFile,
        [UUID(value) for value in configuration["user_file_ids"]],
        "user files",
    )
    runtime.hierarchy_nodes = _load_entities_by_ids(
        db_session,
        HierarchyNode,
        configuration["hierarchy_node_ids"],
        "hierarchy nodes",
    )
    runtime.attached_documents = _load_entities_by_ids(
        db_session, Document, configuration["document_ids"], "documents"
    )
    db_session.add(runtime)
    db_session.flush()
    return runtime


def create_configuration_candidate(
    db_session: Session,
    *,
    target_type: ConfigurationTargetType,
    target_id: str,
    configuration: dict[str, Any],
    change_reason: str,
    user_id: UUID,
) -> ConfigurationVersionSnapshot:
    _validate_configuration(target_type, configuration)
    production = ensure_production_configuration_version(
        db_session, target_type=target_type, target_id=target_id
    )
    next_version = (
        int(
            db_session.scalar(
                select(
                    func.coalesce(func.max(AIConfigurationVersion.version_number), 0)
                ).where(
                    AIConfigurationVersion.target_type == target_type,
                    AIConfigurationVersion.target_id == target_id,
                )
            )
            or 0
        )
        + 1
    )
    runtime_persona_id: int | None = None
    if target_type == "agent":
        target = _load_agent(db_session, int(target_id))
        runtime_persona_id = _create_runtime_persona(
            db_session,
            target=target,
            configuration=configuration,
            version_number=next_version,
        ).id

    version = AIConfigurationVersion(
        target_type=target_type,
        target_id=target_id,
        version_number=next_version,
        status="draft",
        base_version_id=production.id,
        runtime_persona_id=runtime_persona_id,
        configuration=configuration,
        source_hash=_configuration_hash(configuration),
        change_reason=change_reason,
        created_by_user_id=user_id,
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return ConfigurationVersionSnapshot.model_validate(version)


def list_configuration_versions(
    db_session: Session,
    *,
    target_type: ConfigurationTargetType,
    target_id: str,
) -> list[ConfigurationVersionSnapshot]:
    rows = list(
        db_session.scalars(
            select(AIConfigurationVersion)
            .where(
                AIConfigurationVersion.target_type == target_type,
                AIConfigurationVersion.target_id == target_id,
            )
            .order_by(AIConfigurationVersion.version_number.desc())
        )
    )
    return [ConfigurationVersionSnapshot.model_validate(row) for row in rows]


def create_improvement_item(
    db_session: Session,
    *,
    title: str,
    description: str,
    priority: int,
    source_message_ids: list[int],
    owner_user_id: UUID,
    root_cause: str | None,
    target_type: str | None,
    target_id: str | None,
    expected_outcome: str | None,
) -> ImprovementItemSnapshot:
    existing_message_ids = set(
        db_session.scalars(
            select(ChatMessage.id).where(ChatMessage.id.in_(source_message_ids))
        )
    )
    if existing_message_ids != set(source_message_ids):
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "A source message is invalid.")
    item = AIImprovementItem(
        title=title,
        description=description,
        priority=priority,
        source_message_ids=source_message_ids,
        owner_user_id=owner_user_id,
        root_cause=root_cause,
        target_type=target_type,
        target_id=target_id,
        expected_outcome=expected_outcome,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return ImprovementItemSnapshot.model_validate(item)


def list_improvement_items(db_session: Session) -> list[ImprovementItemSnapshot]:
    rows = list(
        db_session.scalars(
            select(AIImprovementItem).order_by(
                AIImprovementItem.priority.desc(), AIImprovementItem.time_created.desc()
            )
        )
    )
    return [ImprovementItemSnapshot.model_validate(row) for row in rows]


def mask_evaluation_text(value: str) -> str:
    masked = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    masked = re.sub(r"(?<!\d)(?:\+?\d[\d -]{7,}\d)(?!\d)", "[PHONE]", masked)
    return masked


def create_evaluation_dataset(
    db_session: Session,
    *,
    name: str,
    description: str,
    cases: list[EvaluationDatasetCaseInput],
    user_id: UUID,
) -> EvaluationDatasetSnapshot:
    next_version = (
        int(
            db_session.scalar(
                select(func.coalesce(func.max(AIEvaluationDataset.version), 0)).where(
                    AIEvaluationDataset.name == name
                )
            )
            or 0
        )
        + 1
    )
    dataset = AIEvaluationDataset(
        name=name,
        description=description,
        version=next_version,
        status="draft",
        created_by_user_id=user_id,
    )
    db_session.add(dataset)
    db_session.flush()
    for case in cases:
        db_session.add(
            AIEvaluationDatasetCase(
                dataset_id=dataset.id,
                input_text=mask_evaluation_text(case.input_text),
                expected_outcome=(
                    mask_evaluation_text(case.expected_outcome)
                    if case.expected_outcome
                    else None
                ),
                task_category=case.task_category,
                source_message_id=case.source_message_id,
                is_masked=True,
                case_metadata={},
            )
        )
    db_session.commit()
    db_session.refresh(dataset)
    snapshot = EvaluationDatasetSnapshot.model_validate(dataset)
    snapshot.case_count = len(cases)
    return snapshot


def list_evaluation_datasets(db_session: Session) -> list[EvaluationDatasetSnapshot]:
    rows = db_session.execute(
        select(AIEvaluationDataset, func.count(AIEvaluationDatasetCase.id))
        .join(
            AIEvaluationDatasetCase,
            AIEvaluationDatasetCase.dataset_id == AIEvaluationDataset.id,
            isouter=True,
        )
        .group_by(AIEvaluationDataset.id)
        .order_by(AIEvaluationDataset.time_created.desc())
    ).all()
    return [
        EvaluationDatasetSnapshot.model_validate(dataset).model_copy(
            update={"case_count": int(case_count)}
        )
        for dataset, case_count in rows
    ]


def freeze_evaluation_dataset(
    db_session: Session, dataset_id: int
) -> EvaluationDatasetSnapshot:
    dataset = db_session.get(AIEvaluationDataset, dataset_id)
    if dataset is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Evaluation dataset not found.")
    if not dataset.cases:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Evaluation dataset is empty.")
    dataset.status = "frozen"
    db_session.commit()
    db_session.refresh(dataset)
    snapshot = EvaluationDatasetSnapshot.model_validate(dataset)
    snapshot.case_count = len(dataset.cases)
    return snapshot


def create_evaluation_run(
    db_session: Session, *, candidate_version_id: int, dataset_id: int
) -> EvaluationRunSnapshot:
    candidate = db_session.get(AIConfigurationVersion, candidate_version_id)
    dataset = db_session.get(AIEvaluationDataset, dataset_id)
    if candidate is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Candidate version not found.")
    if dataset is None or dataset.status != "frozen":
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Use a frozen evaluation dataset.")
    baseline = _production_version(
        db_session,
        candidate.target_type,
        candidate.target_id,  # type: ignore[arg-type]
    )
    if baseline is None or candidate.status not in {"draft", "evaluating"}:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Candidate cannot start evaluation.")
    candidate.status = "evaluating"
    run = AIEvaluationRun(
        candidate_version_id=candidate.id,
        baseline_version_id=baseline.id,
        dataset_id=dataset.id,
        status="pending",
        summary={},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return EvaluationRunSnapshot.model_validate(run)


def list_evaluation_runs(db_session: Session) -> list[EvaluationRunSnapshot]:
    rows = list(
        db_session.scalars(
            select(AIEvaluationRun).order_by(AIEvaluationRun.time_created.desc())
        )
    )
    return [EvaluationRunSnapshot.model_validate(row) for row in rows]


def list_canary_releases(db_session: Session) -> list[CanaryReleaseSnapshot]:
    rows = list(
        db_session.scalars(select(AICanaryRelease).order_by(AICanaryRelease.id.desc()))
    )
    return [CanaryReleaseSnapshot.model_validate(row) for row in rows]


def approve_configuration_version(
    db_session: Session, *, version_id: int, user_id: UUID
) -> ConfigurationVersionSnapshot:
    version = db_session.get(AIConfigurationVersion, version_id)
    if version is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Configuration version not found.")
    passed_run = db_session.scalar(
        select(AIEvaluationRun.id).where(
            AIEvaluationRun.candidate_version_id == version.id,
            AIEvaluationRun.status == "completed",
            AIEvaluationRun.gates_passed.is_(True),
        )
    )
    if passed_run is None:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Candidate has not passed evaluation.")
    version.status = "approved"
    version.approved_by_user_id = user_id
    version.approved_at = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(version)
    return ConfigurationVersionSnapshot.model_validate(version)


def start_canary_release(
    db_session: Session,
    *,
    version_id: int,
    evaluation_run_id: int,
    traffic_percentage: float,
    eligible_scope: dict[str, Any],
    user_id: UUID,
) -> CanaryReleaseSnapshot:
    candidate = db_session.get(AIConfigurationVersion, version_id)
    run = db_session.get(AIEvaluationRun, evaluation_run_id)
    if candidate is None or run is None:
        raise OnyxError(
            OnyxErrorCode.NOT_FOUND, "Candidate or evaluation run not found."
        )
    if (
        candidate.status != "approved"
        or run.candidate_version_id != candidate.id
        or run.gates_passed is not True
    ):
        raise OnyxError(OnyxErrorCode.CONFLICT, "Candidate is not approved for canary.")
    baseline = _production_version(
        db_session,
        candidate.target_type,
        candidate.target_id,  # type: ignore[arg-type]
    )
    if baseline is None:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Production baseline is missing.")
    active_canary = db_session.scalar(
        select(AICanaryRelease.id).where(
            AICanaryRelease.status == "running",
            AICanaryRelease.baseline_version_id == baseline.id,
        )
    )
    if active_canary is not None:
        raise OnyxError(OnyxErrorCode.CONFLICT, "A canary is already running.")
    candidate.status = "canary"
    canary = AICanaryRelease(
        candidate_version_id=candidate.id,
        baseline_version_id=baseline.id,
        evaluation_run_id=run.id,
        traffic_percentage=traffic_percentage,
        eligible_scope=eligible_scope,
        status="running",
        approved_by_user_id=user_id,
        time_started=datetime.now(timezone.utc),
    )
    db_session.add(canary)
    db_session.commit()
    db_session.refresh(canary)
    return CanaryReleaseSnapshot.model_validate(canary)


def stop_canary_release(
    db_session: Session, *, canary_id: int, reason: str | None = None
) -> CanaryReleaseSnapshot:
    canary = db_session.get(AICanaryRelease, canary_id)
    if canary is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Canary release not found.")
    if canary.status != "running":
        raise OnyxError(OnyxErrorCode.CONFLICT, "Canary release is not running.")
    candidate = db_session.get(AIConfigurationVersion, canary.candidate_version_id)
    if candidate is not None:
        candidate.status = "approved"
    canary.status = "stopped"
    canary.automatic_stop_reason = reason
    canary.time_stopped = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(canary)
    return CanaryReleaseSnapshot.model_validate(canary)


def promote_canary_release(
    db_session: Session, *, canary_id: int
) -> CanaryReleaseSnapshot:
    canary = db_session.scalar(
        select(AICanaryRelease).where(AICanaryRelease.id == canary_id).with_for_update()
    )
    if canary is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Canary release not found.")
    if canary.status != "running":
        raise OnyxError(OnyxErrorCode.CONFLICT, "Canary release is not running.")
    baseline = db_session.get(AIConfigurationVersion, canary.baseline_version_id)
    candidate = db_session.get(AIConfigurationVersion, canary.candidate_version_id)
    if baseline is None or candidate is None:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Canary versions are missing.")
    baseline.status = "archived"
    candidate.status = "production"
    candidate.activated_at = datetime.now(timezone.utc)
    canary.status = "promoted"
    canary.time_stopped = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(canary)
    return CanaryReleaseSnapshot.model_validate(canary)


def choose_configuration_version_for_session(
    db_session: Session,
    *,
    persona_id: int,
    user_id: UUID | None,
    session_id: UUID,
) -> ConfigurationVersionSnapshot:
    production = ensure_production_configuration_version(
        db_session, target_type="agent", target_id=str(persona_id)
    )
    canary_row = db_session.execute(
        select(AICanaryRelease, AIConfigurationVersion)
        .join(
            AIConfigurationVersion,
            AIConfigurationVersion.id == AICanaryRelease.candidate_version_id,
        )
        .where(
            AICanaryRelease.status == "running",
            AIConfigurationVersion.target_type == "agent",
            AIConfigurationVersion.target_id == str(persona_id),
        )
    ).first()
    if canary_row is None:
        return production
    canary, candidate = canary_row
    scope_user_ids = canary.eligible_scope.get("user_ids", [])
    if scope_user_ids and str(user_id) not in scope_user_ids:
        return production

    safety_incident = db_session.scalar(
        select(ChatMessageQualityEvaluation.id)
        .join(
            ChatMessage,
            ChatMessage.id == ChatMessageQualityEvaluation.chat_message_id,
        )
        .where(
            ChatMessage.ai_configuration_version_id == candidate.id,
            ChatMessageQualityEvaluation.time_created >= canary.time_started,
            (
                ChatMessageQualityEvaluation.harmful_response.is_(True)
                | ChatMessageQualityEvaluation.sensitive_data_leakage.is_(True)
                | ChatMessageQualityEvaluation.unauthorized_document_exposure.is_(True)
                | ChatMessageQualityEvaluation.policy_violation.is_(True)
                | ChatMessageQualityEvaluation.prompt_injection_succeeded.is_(True)
            ),
        )
        .limit(1)
    )
    if safety_incident is not None:
        canary.status = "failed"
        canary.automatic_stop_reason = (
            "A reviewed canary response failed a safety gate."
        )
        canary.time_stopped = datetime.now(timezone.utc)
        candidate.status = "approved"
        db_session.commit()
        return production

    assignment_key = f"{user_id or 'anonymous'}:{session_id}".encode()
    bucket = int.from_bytes(hashlib.sha256(assignment_key).digest()[:8], "big") % 10_000
    if bucket < round(canary.traffic_percentage * 100):
        return ConfigurationVersionSnapshot.model_validate(candidate)
    return production


def get_production_skill_configuration(
    db_session: Session, skill: Skill
) -> dict[str, Any] | None:
    target_type: ConfigurationTargetType = (
        "builtin_skill" if skill.built_in_skill_id is not None else "custom_skill"
    )
    version = _production_version(db_session, target_type, str(skill.id))
    return dict(version.configuration) if version is not None else None
