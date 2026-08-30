"use client";

import useSWR from "swr";
import { Card, MessageCard, Text } from "@opal/components";
import { ContentAction, PageLoader } from "@opal/layouts";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { qualityOverviewUrl } from "@/app/admin/usage-report/lib";
import {
  KpiMetric,
  ModelQualityRow,
  QualityKpiOverview,
  TaskCategoryQualityRow,
} from "@/app/admin/usage-report/types";

type MetricFormat = "percent" | "score" | "seconds" | "cost" | "number";

interface MetricTileProps {
  label: string;
  description: string;
  metric: KpiMetric;
  format?: MetricFormat;
}

function formatMetric(metric: KpiMetric, format: MetricFormat): string {
  if (metric.value === null) return "—";
  if (format === "percent") return `${metric.value.toFixed(1)}%`;
  if (format === "score") return `${metric.value.toFixed(2)} / 5`;
  if (format === "seconds") return `${metric.value.toFixed(2)}s`;
  if (format === "number") return metric.value.toFixed(2);
  return `$${(metric.value / 100).toFixed(2)}`;
}

function MetricTile({
  label,
  description,
  metric,
  format = "percent",
}: MetricTileProps) {
  return (
    <Card border="solid" padding={3}>
      <div className="flex h-full flex-col gap-1">
        <Text font="secondary-body" color="text-03">
          {label}
        </Text>
        <Text font="heading-h3">{formatMetric(metric, format)}</Text>
        <Text font="secondary-body" color="text-03">
          {description}
        </Text>
        <Text font="secondary-mono" color="text-02">
          {`n=${metric.sample_size}`}
        </Text>
      </div>
    </Card>
  );
}

interface SafetyTileProps {
  label: string;
  count: number;
}

function SafetyTile({ label, count }: SafetyTileProps) {
  return (
    <Card
      border="solid"
      borderColor={count > 0 ? "error" : "success"}
      padding={3}
    >
      <div className="flex items-center justify-between gap-2">
        <Text font="main-ui-body" color="text-04">
          {label}
        </Text>
        <Text font="heading-h3">{String(count)}</Text>
      </div>
    </Card>
  );
}

function ModelRow({ row }: { row: ModelQualityRow }) {
  return (
    <div className="grid grid-cols-2 gap-2 border-b border-border-01 py-2 last:border-b-0 md:grid-cols-6">
      <Text font="main-ui-body" color="text-04">
        {row.model}
      </Text>
      <Text font="secondary-body" color="text-03">
        {`${row.reviewed_responses} / ${row.assistant_responses} reviewed`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.task_success_rate === null
          ? "Task success —"
          : `Task success ${row.task_success_rate.toFixed(1)}%`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.answer_quality_score === null
          ? "Quality —"
          : `Quality ${row.answer_quality_score.toFixed(2)} / 5`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.hallucination_rate === null
          ? "Hallucination —"
          : `Hallucination ${row.hallucination_rate.toFixed(1)}%`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.p95_response_seconds === null
          ? "P95 —"
          : `P95 ${row.p95_response_seconds.toFixed(2)}s`}
      </Text>
    </div>
  );
}

function TaskCategoryRow({ row }: { row: TaskCategoryQualityRow }) {
  return (
    <div className="grid grid-cols-2 gap-2 border-b border-border-01 py-2 last:border-b-0 md:grid-cols-5">
      <Text font="main-ui-body" color="text-04">
        {row.task_category}
      </Text>
      <Text font="secondary-body" color="text-03">
        {`${row.reviewed_responses} reviewed`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.task_success_rate === null
          ? "Task success —"
          : `Task success ${row.task_success_rate.toFixed(1)}%`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.answer_quality_score === null
          ? "Quality —"
          : `Quality ${row.answer_quality_score.toFixed(2)} / 5`}
      </Text>
      <Text font="secondary-body" color="text-03">
        {row.hallucination_rate === null
          ? "Hallucination —"
          : `Hallucination ${row.hallucination_rate.toFixed(1)}%`}
      </Text>
    </div>
  );
}

interface QualityDashboardProps {
  days: number;
}

export default function QualityDashboard({ days }: QualityDashboardProps) {
  const { data, error, isLoading } = useSWR<QualityKpiOverview>(
    qualityOverviewUrl(days),
    errorHandlingFetcher
  );

  if (isLoading) return <PageLoader />;
  if (error || !data) {
    return (
      <MessageCard
        variant="error"
        title="Failed to load AI quality metrics."
        description="Check that the quality evaluation migration is installed."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ContentAction
        title="AI response quality"
        description={`${data.assistant_responses} responses · ${data.human_reviewed_responses} human reviews · ${data.llm_reviewed_responses} judge reviews · ${data.paired_reviewed_responses} paired reviews.`}
        sizePreset="main-content"
        variant="section"
      />

      {data.failed_judge_jobs > 0 && (
        <MessageCard
          variant="warning"
          title={`${data.failed_judge_jobs} judge jobs need attention.`}
          description="Inspect failed jobs before increasing automatic evaluation coverage."
        />
      )}

      {data.reviewed_responses === 0 && (
        <MessageCard
          variant="info"
          title="No responses have a quality review yet."
          description="Open a conversation below. Expand an assistant response and complete its quality review."
        />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile
          label="Human–judge agreement"
          description="Matching paired boolean decisions."
          metric={data.boolean_agreement_rate}
        />
        <MetricTile
          label="Judge score error"
          description="Mean absolute error against human scores."
          metric={data.score_mean_absolute_error}
          format="number"
        />
        <MetricTile
          label="Pending reviews"
          description="Responses waiting for a human reviewer."
          metric={{
            value: data.pending_review_items,
            sample_size: data.pending_review_items,
          }}
          format="number"
        />
        <MetricTile
          label="Claimed reviews"
          description="Responses currently assigned to reviewers."
          metric={{
            value: data.claimed_review_items,
            sample_size: data.claimed_review_items,
          }}
          format="number"
        />
        <MetricTile
          label="Task success"
          description="The response completed the user's task."
          metric={data.task_success_rate}
        />
        <MetricTile
          label="First-answer resolution"
          description="The first response solved the task."
          metric={data.first_answer_resolution_rate}
        />
        <MetricTile
          label="Answer quality"
          description="Weighted score for correctness and usefulness."
          metric={data.answer_quality_score}
          format="score"
        />
        <MetricTile
          label="Grounded answers"
          description="Claims are supported by available sources."
          metric={data.grounded_answer_rate}
        />
        <MetricTile
          label="Hallucination"
          description="Reviewed responses with unsupported claims."
          metric={data.hallucination_rate}
        />
        <MetricTile
          label="Required rephrase"
          description="The user needed to restate the request."
          metric={data.rephrase_rate}
        />
        <MetricTile
          label="Citation coverage"
          description="Responses that include at least one citation."
          metric={data.citation_coverage_rate}
        />
        <MetricTile
          label="Citation accuracy"
          description="Citations support the claims in the response."
          metric={data.citation_accuracy_score}
          format="score"
        />
        <MetricTile
          label="Positive feedback"
          description="Positive ratings among rated responses."
          metric={data.positive_feedback_rate}
        />
        <MetricTile
          label="Response errors"
          description="Assistant responses that stored an error."
          metric={data.response_error_rate}
        />
        <MetricTile
          label="P95 response time"
          description="95% of measured responses complete within this time."
          metric={data.p95_response_seconds}
          format="seconds"
        />
        <MetricTile
          label="Estimated cost per success"
          description="Period cost divided by estimated successful responses."
          metric={data.estimated_cost_per_success_cents}
          format="cost"
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <Text font="heading-h3">Diagnostic metrics</Text>
          <Text font="secondary-body" color="text-03">
            Use these measures to find why the main outcome measures changed.
          </Text>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricTile
            label="Evaluation coverage"
            description="Responses with an explicit quality review."
            metric={data.evaluation_coverage_rate}
          />
          <MetricTile
            label="Feedback coverage"
            description="Responses with a positive or negative rating."
            metric={data.feedback_coverage_rate}
          />
          <MetricTile
            label="Average response time"
            description="Mean stored processing time for measured responses."
            metric={data.average_response_seconds}
            format="seconds"
          />
          <MetricTile
            label="User turns per session"
            description="Average user messages in each active session."
            metric={data.average_user_turns_per_session}
            format="number"
          />
          <MetricTile
            label="Correctness"
            description="The response contains accurate information."
            metric={data.correctness_score}
            format="score"
          />
          <MetricTile
            label="Relevance"
            description="The response directly addresses the request."
            metric={data.relevance_score}
            format="score"
          />
          <MetricTile
            label="Completeness"
            description="The response includes the required information."
            metric={data.completeness_score}
            format="score"
          />
          <MetricTile
            label="Clarity"
            description="The response is easy to understand and use."
            metric={data.clarity_score}
            format="score"
          />
          <MetricTile
            label="Instruction following"
            description="The response follows the user's constraints."
            metric={data.instruction_following_score}
            format="score"
          />
          <MetricTile
            label="Retrieval relevance"
            description="Retrieved sources are useful for the request."
            metric={data.retrieval_relevance_score}
            format="score"
          />
          <MetricTile
            label="Appropriate refusal"
            description="A required refusal was handled correctly."
            metric={data.appropriate_refusal_rate}
          />
          <MetricTile
            label="False refusal"
            description="The AI refused a request it could answer."
            metric={data.false_refusal_rate}
          />
        </div>
      </div>

      <Card border="solid" padding={4}>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Text font="heading-h3">Safety guardrails</Text>
            <Text font="secondary-body" color="text-03">
              {`${data.safety.reviewed_responses} responses have a safety review. Any incident requires investigation.`}
            </Text>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <SafetyTile
              label="Harmful responses"
              count={data.safety.harmful_responses}
            />
            <SafetyTile
              label="Sensitive data leaks"
              count={data.safety.sensitive_data_leaks}
            />
            <SafetyTile
              label="Unauthorized sources"
              count={data.safety.unauthorized_document_exposures}
            />
            <SafetyTile
              label="Policy violations"
              count={data.safety.policy_violations}
            />
            <SafetyTile
              label="Prompt injections"
              count={data.safety.successful_prompt_injections}
            />
          </div>
        </div>
      </Card>

      {data.by_model.length > 0 && (
        <Card border="solid" padding={4}>
          <div className="flex flex-col gap-2">
            <Text font="heading-h3">Quality by model</Text>
            {data.by_model.map((row) => (
              <ModelRow key={row.model} row={row} />
            ))}
          </div>
        </Card>
      )}

      {data.by_task_category.length > 0 && (
        <Card border="solid" padding={4}>
          <div className="flex flex-col gap-2">
            <Text font="heading-h3">Quality by task category</Text>
            {data.by_task_category.map((row) => (
              <TaskCategoryRow key={row.task_category} row={row} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
