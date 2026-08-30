export interface DailyActivity {
  date: string;
  messages: number;
  sessions: number;
  active_users: number;
}

export interface ModelUsageRow {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export interface UserUsageRow {
  email: string;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export interface UsageOverview {
  days: number;
  total_messages: number;
  total_sessions: number;
  active_users: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_cents: number;
  feedback_positive: number;
  feedback_negative: number;
  daily: DailyActivity[];
  by_model: ModelUsageRow[];
  by_user: UserUsageRow[];
}

export interface ChatHistoryEntry {
  session_id: string;
  time_created: string;
  user_email: string | null;
  persona_name: string | null;
  description: string | null;
  message_count: number;
}

export interface ChatHistoryPage {
  total: number;
  page: number;
  page_size: number;
  entries: ChatHistoryEntry[];
}

export interface ChatHistoryMessage {
  id: number;
  message_type: "user" | "assistant" | "tool_call_response" | "system";
  time_sent: string;
  message: string;
  token_count: number;
  model_display_name: string | null;
  processing_duration_seconds: number | null;
  error: string | null;
  citation_count: number;
  feedback: boolean | null;
  quality_evaluation: QualityEvaluation | null;
  human_quality_evaluation: QualityEvaluation | null;
  llm_quality_evaluation: QualityEvaluation | null;
  selected_quality_evaluation: QualityEvaluation | null;
}

export type EvaluationSource = "human" | "llm_judge";

export interface QualityEvaluationInput {
  evaluation_source: EvaluationSource;
  judge_model: string | null;
  judge_version: string | null;
  rubric_version: string | null;
  confidence: number | null;
  task_category: string | null;
  task_success: boolean | null;
  first_answer_resolution: boolean | null;
  required_rephrase: boolean | null;
  correctness: number | null;
  relevance: number | null;
  completeness: number | null;
  clarity: number | null;
  instruction_following: number | null;
  grounded: boolean | null;
  citation_accuracy: number | null;
  retrieval_relevance: number | null;
  hallucination_detected: boolean | null;
  appropriate_refusal: boolean | null;
  false_refusal: boolean | null;
  harmful_response: boolean | null;
  sensitive_data_leakage: boolean | null;
  unauthorized_document_exposure: boolean | null;
  policy_violation: boolean | null;
  prompt_injection_succeeded: boolean | null;
  notes: string | null;
}

export interface QualityEvaluation extends QualityEvaluationInput {
  id: number;
  chat_message_id: number;
  reviewer_user_id: string | null;
  time_created: string;
  time_updated: string;
}

export interface KpiMetric {
  value: number | null;
  sample_size: number;
}

export interface SafetyGuardrails {
  reviewed_responses: number;
  harmful_responses: number;
  sensitive_data_leaks: number;
  unauthorized_document_exposures: number;
  policy_violations: number;
  successful_prompt_injections: number;
}

export interface ModelQualityRow {
  model: string;
  assistant_responses: number;
  reviewed_responses: number;
  human_reviewed_responses: number;
  llm_reviewed_responses: number;
  paired_reviewed_responses: number;
  boolean_agreement_rate: KpiMetric;
  score_mean_absolute_error: KpiMetric;
  pending_review_items: number;
  claimed_review_items: number;
  failed_judge_jobs: number;
  task_success_rate: number | null;
  answer_quality_score: number | null;
  hallucination_rate: number | null;
  p95_response_seconds: number | null;
}

export interface TaskCategoryQualityRow {
  task_category: string;
  reviewed_responses: number;
  task_success_rate: number | null;
  answer_quality_score: number | null;
  hallucination_rate: number | null;
}

export interface QualityKpiOverview {
  days: number;
  assistant_responses: number;
  reviewed_responses: number;
  human_reviewed_responses: number;
  llm_reviewed_responses: number;
  paired_reviewed_responses: number;
  boolean_agreement_rate: KpiMetric;
  score_mean_absolute_error: KpiMetric;
  pending_review_items: number;
  claimed_review_items: number;
  failed_judge_jobs: number;
  evaluation_coverage_rate: KpiMetric;
  response_error_rate: KpiMetric;
  citation_coverage_rate: KpiMetric;
  feedback_coverage_rate: KpiMetric;
  positive_feedback_rate: KpiMetric;
  average_response_seconds: KpiMetric;
  p95_response_seconds: KpiMetric;
  average_user_turns_per_session: KpiMetric;
  task_success_rate: KpiMetric;
  first_answer_resolution_rate: KpiMetric;
  rephrase_rate: KpiMetric;
  answer_quality_score: KpiMetric;
  correctness_score: KpiMetric;
  relevance_score: KpiMetric;
  completeness_score: KpiMetric;
  clarity_score: KpiMetric;
  instruction_following_score: KpiMetric;
  grounded_answer_rate: KpiMetric;
  citation_accuracy_score: KpiMetric;
  retrieval_relevance_score: KpiMetric;
  hallucination_rate: KpiMetric;
  appropriate_refusal_rate: KpiMetric;
  false_refusal_rate: KpiMetric;
  estimated_cost_per_success_cents: KpiMetric;
  safety: SafetyGuardrails;
  by_model: ModelQualityRow[];
  by_task_category: TaskCategoryQualityRow[];
}

export type QualityReviewQueueStatus =
  | "pending"
  | "claimed"
  | "completed"
  | "skipped";

export interface QualityReviewQueueItem {
  id: number;
  chat_message_id: number;
  session_id: string;
  priority: number;
  reasons: string[];
  status: QualityReviewQueueStatus;
  assigned_user_id: string | null;
  claim_expires_at: string | null;
  root_cause: string | null;
  skip_reason: string | null;
  model_display_name: string | null;
  user_message: string;
  assistant_message: string;
  human_evaluation: QualityEvaluation | null;
  llm_evaluation: QualityEvaluation | null;
}

export interface QualityReviewQueuePage {
  total: number;
  page: number;
  page_size: number;
  items: QualityReviewQueueItem[];
}
