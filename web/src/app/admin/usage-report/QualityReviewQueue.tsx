"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  Button,
  Card,
  EmptyMessageCard,
  InputSelect,
  Text,
} from "@opal/components";
import { toast } from "@opal/layouts";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  qualityOverviewUrl,
  qualityReviewQueueActionUrl,
  qualityReviewQueueUrl,
} from "@/app/admin/usage-report/lib";
import {
  QualityReviewQueueItem,
  QualityReviewQueuePage,
  QualityReviewQueueStatus,
} from "@/app/admin/usage-report/types";
import QualityReviewForm from "@/app/admin/usage-report/QualityReviewForm";

const STATUS_OPTIONS: { label: string; value: QualityReviewQueueStatus }[] = [
  { label: "Pending", value: "pending" },
  { label: "Claimed", value: "claimed" },
  { label: "Completed", value: "completed" },
  { label: "Skipped", value: "skipped" },
];

function reasonLabel(reason: string): string {
  return reason.replaceAll("_", " ");
}

interface QualityReviewQueueProps {
  days: number;
}

export default function QualityReviewQueue({ days }: QualityReviewQueueProps) {
  const [status, setStatus] = useState<QualityReviewQueueStatus>("pending");
  const [activeItem, setActiveItem] = useState<QualityReviewQueueItem | null>(
    null
  );
  const [actionPending, setActionPending] = useState(false);
  const queueUrl = qualityReviewQueueUrl(status);
  const { data, isLoading } = useSWR<QualityReviewQueuePage>(
    queueUrl,
    errorHandlingFetcher
  );

  async function runAction(
    item: QualityReviewQueueItem,
    action: "claim" | "release" | "skip"
  ) {
    setActionPending(true);
    try {
      const response = await fetch(
        qualityReviewQueueActionUrl(item.id, action),
        {
          method: "POST",
          credentials: "include",
          headers:
            action === "skip"
              ? { "Content-Type": "application/json" }
              : undefined,
          body:
            action === "skip"
              ? JSON.stringify({ reason: "Skipped by the assigned reviewer." })
              : undefined,
        }
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Failed to ${action} review.`);
      }
      const updated = (await response.json()) as QualityReviewQueueItem;
      if (action === "claim") {
        setActiveItem({ ...item, ...updated });
      } else {
        setActiveItem(null);
      }
      await mutate(queueUrl);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Review action failed."
      );
    } finally {
      setActionPending(false);
    }
  }

  async function reviewSaved() {
    setActiveItem(null);
    await Promise.all([mutate(queueUrl), mutate(qualityOverviewUrl(days))]);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <Text font="heading-h3">Human review queue</Text>
          <Text font="secondary-body" color="text-03">
            Review high-risk responses and a stable sample of normal responses.
          </Text>
        </div>
        <div className="w-40">
          <InputSelect
            value={status}
            onValueChange={(value) => {
              setStatus(value as QualityReviewQueueStatus);
              setActiveItem(null);
            }}
          >
            <InputSelect.Trigger />
            <InputSelect.Content>
              {STATUS_OPTIONS.map((option) => (
                <InputSelect.Item key={option.value} value={option.value}>
                  {option.label}
                </InputSelect.Item>
              ))}
            </InputSelect.Content>
          </InputSelect>
        </div>
      </div>

      {!isLoading && (data?.items.length ?? 0) === 0 && (
        <EmptyMessageCard
          sizePreset="main-ui"
          title={`No ${status} reviews`}
          description="Items appear here when the judge, feedback, or sampling rules select them."
        />
      )}

      {(data?.items ?? []).map((item) => {
        const isActive = activeItem?.id === item.id;
        return (
          <Card
            key={item.id}
            border="solid"
            padding={4}
            data-testid={`quality-review-item-${item.id}`}
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex flex-col gap-1">
                  <Text font="main-ui-action">
                    {`Priority ${item.priority} · ${item.model_display_name ?? "Unknown model"}`}
                  </Text>
                  <Text font="secondary-body" color="text-03">
                    {item.reasons.map(reasonLabel).join(" · ")}
                  </Text>
                </div>
                <div className="flex gap-2">
                  {(item.status === "pending" || item.status === "claimed") &&
                    !isActive && (
                      <Button
                        disabled={actionPending}
                        onClick={() => void runAction(item, "claim")}
                      >
                        Claim review
                      </Button>
                    )}
                  {isActive && (
                    <>
                      <Button
                        prominence="secondary"
                        disabled={actionPending}
                        onClick={() => void runAction(item, "release")}
                      >
                        Release
                      </Button>
                      <Button
                        variant="danger"
                        prominence="secondary"
                        disabled={actionPending}
                        onClick={() => void runAction(item, "skip")}
                      >
                        Skip
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                <Card border="solid" background="light" padding={3}>
                  <div className="flex flex-col gap-1">
                    <Text font="secondary-body" color="text-03">
                      User request
                    </Text>
                    <Text font="main-ui-body" color="text-04">
                      {item.user_message}
                    </Text>
                  </div>
                </Card>
                <Card border="solid" background="light" padding={3}>
                  <div className="flex flex-col gap-1">
                    <Text font="secondary-body" color="text-03">
                      Assistant response
                    </Text>
                    <Text font="main-ui-body" color="text-04">
                      {item.assistant_message}
                    </Text>
                  </div>
                </Card>
              </div>

              {isActive && (
                <QualityReviewForm
                  chatMessageId={item.chat_message_id}
                  sessionId={item.session_id}
                  days={days}
                  evaluation={item.human_evaluation}
                  onSaved={() => void reviewSaved()}
                />
              )}

              {item.status === "completed" && item.llm_evaluation && (
                <Text font="secondary-body" color="text-03">
                  {`Judge confidence ${(item.llm_evaluation.confidence ?? 0) * 100}% · Human and judge results are available for calibration.`}
                </Text>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
