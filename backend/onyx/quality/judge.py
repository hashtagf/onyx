"""LLM judge for assistant-response quality."""

from pydantic import BaseModel, Field

from onyx.db.chat_quality import ChatQualityReviewCandidate, QualityEvaluationInput
from onyx.llm.interfaces import LLM
from onyx.llm.models import (
    LanguageModelInput,
    ReasoningEffort,
    SystemMessage,
    UserMessage,
)
from onyx.llm.utils import llm_response_to_string
from onyx.prompts.chat_quality import (
    CHAT_QUALITY_JUDGE_SYSTEM_PROMPT,
    CHAT_QUALITY_JUDGE_USER_PROMPT,
)
from onyx.tracing.flows import LLMFlow
from onyx.tracing.llm_utils import llm_generation_span, record_llm_response
from onyx.utils.text_processing import parse_llm_json_response

MAX_USER_MESSAGE_CHARS = 4_000
MAX_ASSISTANT_MESSAGE_CHARS = 12_000
MAX_CITATIONS = 10
MAX_CITATION_CHARS = 2_000
MAX_CONTEXT_MESSAGE_CHARS = 2_000
DEFAULT_JUDGE_VERSION = "chat-quality-v1"
DEFAULT_RUBRIC_VERSION = "chat-quality-rubric-v1"


class QualityJudgeResult(BaseModel):
    confidence: float = Field(ge=0, le=1)
    task_category: str = Field(max_length=100)
    task_success: bool
    first_answer_resolution: bool
    required_rephrase: bool
    correctness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    instruction_following: int = Field(ge=1, le=5)
    grounded: bool | None
    citation_accuracy: int | None = Field(ge=1, le=5)
    retrieval_relevance: int | None = Field(ge=1, le=5)
    hallucination_detected: bool
    appropriate_refusal: bool | None
    false_refusal: bool
    harmful_response: bool
    sensitive_data_leakage: bool
    unauthorized_document_exposure: bool
    policy_violation: bool
    prompt_injection_succeeded: bool
    notes: str = Field(max_length=4000)


def build_quality_judge_prompt(candidate: ChatQualityReviewCandidate) -> str:
    citation_text = "\n\n".join(
        f"Source {index}: {blurb[:MAX_CITATION_CHARS]}"
        for index, blurb in enumerate(
            candidate.citation_blurbs[:MAX_CITATIONS], start=1
        )
    )
    return CHAT_QUALITY_JUDGE_USER_PROMPT.format(
        user_message=candidate.user_message[:MAX_USER_MESSAGE_CHARS],
        assistant_message=candidate.assistant_message[:MAX_ASSISTANT_MESSAGE_CHARS],
        conversation_context="\n".join(
            context_message[:MAX_CONTEXT_MESSAGE_CHARS]
            for context_message in candidate.conversation_context
        )
        or "No earlier messages supplied.",
        citation_blurbs=citation_text or "No sources supplied.",
    )


def evaluate_response_with_llm_judge(
    candidate: ChatQualityReviewCandidate,
    llm: LLM,
    judge_model: str | None = None,
    judge_version: str = DEFAULT_JUDGE_VERSION,
    rubric_version: str = DEFAULT_RUBRIC_VERSION,
) -> QualityEvaluationInput:
    messages: LanguageModelInput = [
        SystemMessage(content=CHAT_QUALITY_JUDGE_SYSTEM_PROMPT),
        UserMessage(content=build_quality_judge_prompt(candidate)),
    ]
    with llm_generation_span(
        llm=llm,
        flow=LLMFlow.CHAT_QUALITY_EVALUATION,
        input_messages=messages,
    ) as span_generation:
        response = llm.invoke(
            messages,
            reasoning_effort=ReasoningEffort.OFF,
            max_tokens=1200,
        )
        record_llm_response(span_generation, response)

    response_text = llm_response_to_string(response)
    parsed_response = parse_llm_json_response(response_text)
    if parsed_response is None:
        raise ValueError("Quality judge returned invalid JSON.")
    judge_result = QualityJudgeResult.model_validate(parsed_response)
    return QualityEvaluationInput(
        evaluation_source="llm_judge",
        judge_model=judge_model,
        judge_version=judge_version,
        rubric_version=rubric_version,
        **judge_result.model_dump(),
    )
