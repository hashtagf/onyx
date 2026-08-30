"use client";

import { useState } from "react";
import { mutate } from "swr";
import {
  Button,
  Card,
  Checkbox,
  InputSelect,
  InputTextArea,
  InputTypeIn,
  Text,
} from "@opal/components";
import { toast } from "@opal/layouts";
import {
  qualityEvaluationUrl,
  qualityOverviewUrl,
  sessionMessagesUrl,
} from "@/app/admin/usage-report/lib";
import {
  QualityEvaluation,
  QualityEvaluationInput,
} from "@/app/admin/usage-report/types";

type BooleanReviewValue = "not_reviewed" | "yes" | "no";

const EMPTY_EVALUATION: QualityEvaluationInput = {
  evaluation_source: "human",
  judge_model: null,
  judge_version: null,
  rubric_version: null,
  confidence: null,
  task_category: null,
  task_success: null,
  first_answer_resolution: null,
  required_rephrase: null,
  correctness: null,
  relevance: null,
  completeness: null,
  clarity: null,
  instruction_following: null,
  grounded: null,
  citation_accuracy: null,
  retrieval_relevance: null,
  hallucination_detected: null,
  appropriate_refusal: null,
  false_refusal: null,
  harmful_response: false,
  sensitive_data_leakage: false,
  unauthorized_document_exposure: false,
  policy_violation: false,
  prompt_injection_succeeded: false,
  notes: null,
};

function toBooleanReviewValue(value: boolean | null): BooleanReviewValue {
  if (value === null) return "not_reviewed";
  return value ? "yes" : "no";
}

function fromBooleanReviewValue(value: string): boolean | null {
  if (value === "not_reviewed") return null;
  return value === "yes";
}

interface BooleanReviewFieldProps {
  label: string;
  value: boolean | null;
  onChange: (value: boolean | null) => void;
}

function BooleanReviewField({
  label,
  value,
  onChange,
}: BooleanReviewFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <Text font="secondary-body" color="text-03">
        {label}
      </Text>
      <InputSelect
        value={toBooleanReviewValue(value)}
        onValueChange={(nextValue) =>
          onChange(fromBooleanReviewValue(nextValue))
        }
      >
        <InputSelect.Trigger placeholder="Not reviewed" />
        <InputSelect.Content>
          <InputSelect.Item value="not_reviewed">Not reviewed</InputSelect.Item>
          <InputSelect.Item value="yes">Yes</InputSelect.Item>
          <InputSelect.Item value="no">No</InputSelect.Item>
        </InputSelect.Content>
      </InputSelect>
    </div>
  );
}

interface ScoreFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}

function ScoreField({ label, value, onChange }: ScoreFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <Text font="secondary-body" color="text-03">
        {label}
      </Text>
      <InputSelect
        value={value === null ? "not_reviewed" : String(value)}
        onValueChange={(nextValue) =>
          onChange(nextValue === "not_reviewed" ? null : Number(nextValue))
        }
      >
        <InputSelect.Trigger placeholder="Not reviewed" />
        <InputSelect.Content>
          <InputSelect.Item value="not_reviewed">Not reviewed</InputSelect.Item>
          {[1, 2, 3, 4, 5].map((score) => (
            <InputSelect.Item key={score} value={String(score)}>
              {`${score} – ${score === 1 ? "Poor" : score === 5 ? "Excellent" : ""}`}
            </InputSelect.Item>
          ))}
        </InputSelect.Content>
      </InputSelect>
    </div>
  );
}

interface SafetyFieldProps {
  id: string;
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}

function SafetyField({ id, label, checked, onChange }: SafetyFieldProps) {
  return (
    <label htmlFor={id} className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={onChange} />
      <Text font="main-ui-body" color="text-04">
        {label}
      </Text>
    </label>
  );
}

interface QualityReviewFormProps {
  chatMessageId: number;
  sessionId: string;
  days: number;
  evaluation: QualityEvaluation | null;
  onSaved?: () => void;
  onRemoved?: () => void;
}

export default function QualityReviewForm({
  chatMessageId,
  sessionId,
  days,
  evaluation,
  onSaved,
  onRemoved,
}: QualityReviewFormProps) {
  const [form, setForm] = useState<QualityEvaluationInput>(
    evaluation ?? EMPTY_EVALUATION
  );
  const [saving, setSaving] = useState(false);

  function update<K extends keyof QualityEvaluationInput>(
    key: K,
    value: QualityEvaluationInput[K]
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function refreshData() {
    await Promise.all([
      mutate(sessionMessagesUrl(sessionId)),
      mutate(qualityOverviewUrl(days)),
    ]);
  }

  async function save() {
    const qualityScores = [
      form.correctness,
      form.relevance,
      form.completeness,
      form.clarity,
      form.instruction_following,
    ];
    if (
      qualityScores.some((score) => score !== null) &&
      qualityScores.some((score) => score === null)
    ) {
      toast.error("Set all five answer-quality scores together.");
      return;
    }

    setSaving(true);
    try {
      const response = await fetch(qualityEvaluationUrl(chatMessageId), {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "Failed to save quality review.");
      }
      await refreshData();
      toast.success("Quality review saved.");
      onSaved?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    setSaving(true);
    try {
      const response = await fetch(qualityEvaluationUrl(chatMessageId), {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Failed to remove quality review.");
      setForm(EMPTY_EVALUATION);
      await refreshData();
      toast.success("Quality review removed.");
      onRemoved?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Remove failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card border="solid" background="heavy" padding={3}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <Text font="main-ui-action">Quality review</Text>
          <Text font="secondary-body" color="text-03">
            Score the response against the user request and the available
            sources. Missing values do not count as failures.
          </Text>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <BooleanReviewField
            label="Task succeeded"
            value={form.task_success}
            onChange={(value) => update("task_success", value)}
          />
          <BooleanReviewField
            label="First answer resolved task"
            value={form.first_answer_resolution}
            onChange={(value) => update("first_answer_resolution", value)}
          />
          <BooleanReviewField
            label="User needed to rephrase"
            value={form.required_rephrase}
            onChange={(value) => update("required_rephrase", value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <ScoreField
            label="Correctness"
            value={form.correctness}
            onChange={(value) => update("correctness", value)}
          />
          <ScoreField
            label="Relevance"
            value={form.relevance}
            onChange={(value) => update("relevance", value)}
          />
          <ScoreField
            label="Completeness"
            value={form.completeness}
            onChange={(value) => update("completeness", value)}
          />
          <ScoreField
            label="Clarity"
            value={form.clarity}
            onChange={(value) => update("clarity", value)}
          />
          <ScoreField
            label="Instruction following"
            value={form.instruction_following}
            onChange={(value) => update("instruction_following", value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <BooleanReviewField
            label="Grounded in sources"
            value={form.grounded}
            onChange={(value) => update("grounded", value)}
          />
          <ScoreField
            label="Citation accuracy"
            value={form.citation_accuracy}
            onChange={(value) => update("citation_accuracy", value)}
          />
          <ScoreField
            label="Retrieval relevance"
            value={form.retrieval_relevance}
            onChange={(value) => update("retrieval_relevance", value)}
          />
          <BooleanReviewField
            label="Hallucination detected"
            value={form.hallucination_detected}
            onChange={(value) => update("hallucination_detected", value)}
          />
          <BooleanReviewField
            label="Refusal was appropriate"
            value={form.appropriate_refusal}
            onChange={(value) => update("appropriate_refusal", value)}
          />
          <BooleanReviewField
            label="False refusal"
            value={form.false_refusal}
            onChange={(value) => update("false_refusal", value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Text font="secondary-body" color="text-03">
              Task category
            </Text>
            <InputTypeIn
              value={form.task_category ?? ""}
              onChange={(event) =>
                update("task_category", event.target.value || null)
              }
              placeholder="Search, summary, support, analysis…"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Text font="secondary-body" color="text-03">
              Review notes
            </Text>
            <InputTextArea
              value={form.notes ?? ""}
              onChange={(event) => update("notes", event.target.value || null)}
              placeholder="Record evidence or the reason for the score."
              rows={2}
              autoResize
              maxRows={6}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Text font="main-ui-action">Safety incidents</Text>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <SafetyField
              id={`harmful-${chatMessageId}`}
              label="Harmful response"
              checked={form.harmful_response === true}
              onChange={(value) => update("harmful_response", value)}
            />
            <SafetyField
              id={`leak-${chatMessageId}`}
              label="Sensitive data leakage"
              checked={form.sensitive_data_leakage === true}
              onChange={(value) => update("sensitive_data_leakage", value)}
            />
            <SafetyField
              id={`access-${chatMessageId}`}
              label="Unauthorized document exposure"
              checked={form.unauthorized_document_exposure === true}
              onChange={(value) =>
                update("unauthorized_document_exposure", value)
              }
            />
            <SafetyField
              id={`policy-${chatMessageId}`}
              label="Policy violation"
              checked={form.policy_violation === true}
              onChange={(value) => update("policy_violation", value)}
            />
            <SafetyField
              id={`injection-${chatMessageId}`}
              label="Prompt injection succeeded"
              checked={form.prompt_injection_succeeded === true}
              onChange={(value) => update("prompt_injection_succeeded", value)}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2">
          {evaluation && (
            <Button
              variant="danger"
              prominence="secondary"
              disabled={saving}
              onClick={() => void remove()}
            >
              Remove review
            </Button>
          )}
          <Button disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save review"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
