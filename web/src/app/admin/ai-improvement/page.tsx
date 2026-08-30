"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { SettingsLayouts } from "@opal/layouts";

import { ErrorCallout } from "@/components/ErrorCallout";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { improvementUrls, postJson } from "./lib";
import {
  CanaryRelease,
  ConfigurationVersion,
  EvaluationDataset,
  EvaluationRun,
  ImprovementTarget,
} from "./types";

const route = ADMIN_ROUTES.AI_IMPROVEMENT;

function ActionButton({
  children,
  disabled,
  onClick,
  tone = "dark",
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
  tone?: "dark" | "light" | "danger";
}) {
  const color =
    tone === "dark"
      ? "bg-neutral-950 text-white hover:bg-neutral-800"
      : tone === "danger"
        ? "border border-red-300 text-red-700 hover:bg-red-50"
        : "border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50";
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-3 py-2 text-sm font-medium transition ${color} disabled:cursor-not-allowed disabled:opacity-40`}
    >
      {children}
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className="rounded-full border border-neutral-300 bg-white px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide text-neutral-600">
      {status}
    </span>
  );
}

export default function AIImprovementPage() {
  const {
    data: targets,
    error: targetError,
    mutate: mutateTargets,
  } = useSWR<ImprovementTarget[]>(
    improvementUrls.targets,
    errorHandlingFetcher
  );
  const { data: datasets, mutate: mutateDatasets } = useSWR<
    EvaluationDataset[]
  >(improvementUrls.datasets, errorHandlingFetcher);
  const { data: runs, mutate: mutateRuns } = useSWR<EvaluationRun[]>(
    improvementUrls.runs,
    errorHandlingFetcher
  );
  const { data: canaries, mutate: mutateCanaries } = useSWR<CanaryRelease[]>(
    improvementUrls.canaries,
    errorHandlingFetcher
  );

  const [targetKey, setTargetKey] = useState("");
  const selectedTarget = useMemo(
    () =>
      targets?.find(
        (target) => `${target.target_type}:${target.target_id}` === targetKey
      ),
    [targetKey, targets]
  );
  const versionsUrl = selectedTarget
    ? improvementUrls.versions(
        selectedTarget.target_type,
        selectedTarget.target_id
      )
    : null;
  const { data: versions, mutate: mutateVersions } = useSWR<
    ConfigurationVersion[]
  >(versionsUrl, errorHandlingFetcher);

  const [configuration, setConfiguration] = useState<Record<string, unknown>>(
    {}
  );
  const [changeReason, setChangeReason] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [testInput, setTestInput] = useState("");
  const [expectedOutcome, setExpectedOutcome] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const firstTarget = targets?.[0];
    if (!targetKey && firstTarget) {
      setTargetKey(`${firstTarget.target_type}:${firstTarget.target_id}`);
    }
  }, [targetKey, targets]);

  useEffect(() => {
    if (selectedTarget) {
      setConfiguration({ ...selectedTarget.production_version.configuration });
      setChangeReason("");
    }
  }, [selectedTarget]);

  const act = async (name: string, action: () => Promise<void>) => {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setBusy("");
    }
  };

  const setConfigText = (field: string, value: string) =>
    setConfiguration((current) => ({ ...current, [field]: value }));

  const saveCandidate = () =>
    act("candidate", async () => {
      if (!selectedTarget) return;
      await postJson<ConfigurationVersion>(improvementUrls.versionsRoot, {
        target_type: selectedTarget.target_type,
        target_id: selectedTarget.target_id,
        configuration,
        change_reason: changeReason,
      });
      setNotice("Candidate version saved. Production is unchanged.");
      await mutateVersions();
    });

  const createDataset = () =>
    act("dataset", async () => {
      const dataset = await postJson<EvaluationDataset>(
        improvementUrls.datasets,
        {
          name: datasetName,
          description: "Release-gate cases created in AI Improvement Studio.",
          cases: [{ input_text: testInput, expected_outcome: expectedOutcome }],
        }
      );
      await postJson(`${improvementUrls.datasets}/${dataset.id}/freeze`);
      setDatasetName("");
      setTestInput("");
      setExpectedOutcome("");
      setNotice("Dataset created, masked, and frozen.");
      await mutateDatasets();
    });

  const runEvaluation = (candidateId: number, datasetId: number) =>
    act(`run-${candidateId}`, async () => {
      const run = await postJson<EvaluationRun>(improvementUrls.runs, {
        candidate_version_id: candidateId,
        dataset_id: datasetId,
      });
      setNotice("Evaluation started. This can take several minutes.");
      await postJson(`${improvementUrls.runs}/${run.id}/execute`);
      setNotice("Offline evaluation finished. Review every release gate.");
      await Promise.all([mutateRuns(), mutateVersions()]);
    });

  const approve = (versionId: number) =>
    act(`approve-${versionId}`, async () => {
      await postJson(`${improvementUrls.versionsRoot}/${versionId}/approve`);
      setNotice("Candidate approved for a controlled canary.");
      await mutateVersions();
    });

  const startCanary = (versionId: number, runId: number) =>
    act(`canary-${versionId}`, async () => {
      await postJson(improvementUrls.canaries, {
        version_id: versionId,
        evaluation_run_id: runId,
        traffic_percentage: 10,
        eligible_scope: {},
      });
      setNotice("Canary started at 10% with stable session assignment.");
      await Promise.all([mutateCanaries(), mutateVersions()]);
    });

  const changeCanary = (id: number, operation: "promote" | "stop") =>
    act(`${operation}-${id}`, async () => {
      await postJson(
        `${improvementUrls.canaries}/${id}/${operation}`,
        operation === "stop" ? { reason: "Stopped by an administrator." } : {}
      );
      setNotice(
        operation === "promote"
          ? "Candidate promoted to production. New sessions use it."
          : "Canary stopped. New sessions use the baseline."
      );
      await Promise.all([mutateCanaries(), mutateVersions(), mutateTargets()]);
    });

  const frozenDataset = datasets?.find(
    (dataset) => dataset.status === "frozen"
  );
  const selectedRunFor = (versionId: number) =>
    runs?.find(
      (run) => run.candidate_version_id === versionId && run.gates_passed
    );

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        description="Turn reviewed failures into tested Prompt and Skill releases. Production changes only after every gate passes."
        divider
      />
      <SettingsLayouts.Body>
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 pb-16">
          <div className="grid gap-3 border-y border-neutral-300 bg-neutral-950 p-5 text-white md:grid-cols-4">
            {[
              ["01", "Diagnose", "Use reviewed chat evidence"],
              ["02", "Edit", "Create an immutable candidate"],
              ["03", "Prove", "Run frozen offline cases"],
              ["04", "Release", "Canary, watch, then promote"],
            ].map(([number, title, detail]) => (
              <div key={number} className="border-l border-lime-300 pl-3">
                <div className="font-mono text-xs text-lime-300">{number}</div>
                <div className="mt-1 text-sm font-semibold">{title}</div>
                <div className="text-xs text-neutral-400">{detail}</div>
              </div>
            ))}
          </div>

          {targetError && (
            <ErrorCallout
              errorMsg={
                targetError instanceof Error
                  ? targetError.message
                  : "Could not load AI configuration targets."
              }
            />
          )}
          {error && (
            <div className="border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          )}
          {notice && (
            <div className="border border-lime-400 bg-lime-50 p-3 text-sm text-neutral-800">
              {notice}
            </div>
          )}

          <section className="grid gap-5 lg:grid-cols-[320px_1fr]">
            <div className="border border-neutral-300 bg-neutral-100 p-4">
              <div className="mb-3 font-mono text-xs uppercase tracking-widest text-neutral-500">
                Configuration target
              </div>
              <select
                aria-label="Configuration target"
                value={targetKey}
                onChange={(event) => setTargetKey(event.target.value)}
                className="w-full rounded-md border border-neutral-400 bg-white p-2 text-sm"
              >
                {targets?.map((target) => (
                  <option
                    key={`${target.target_type}:${target.target_id}`}
                    value={`${target.target_type}:${target.target_id}`}
                  >
                    {target.target_type.replace("_", " ")} · {target.name}
                  </option>
                ))}
              </select>
              {selectedTarget && (
                <div className="mt-4 space-y-2 text-sm">
                  <div className="text-lg font-semibold">
                    {selectedTarget.name}
                  </div>
                  <p className="text-neutral-600">
                    {selectedTarget.description}
                  </p>
                  <div className="flex items-center gap-2 pt-2">
                    <StatusPill status="production" />
                    <span className="font-mono text-xs">
                      v{selectedTarget.production_version.version_number}
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="border border-neutral-300 bg-white p-5 shadow-[5px_5px_0_0_#d4d4d4]">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Candidate workbench</h2>
                  <p className="mt-1 text-sm text-neutral-600">
                    Start from production. Saved candidates cannot change live
                    traffic.
                  </p>
                </div>
                <span className="font-mono text-xs text-neutral-500">
                  IMMUTABLE
                </span>
              </div>

              {selectedTarget?.target_type === "agent" ? (
                <div className="grid gap-4">
                  <label className="grid gap-1 text-sm font-medium">
                    System prompt
                    <textarea
                      aria-label="System prompt"
                      rows={9}
                      value={String(configuration.system_prompt ?? "")}
                      onChange={(event) =>
                        setConfigText("system_prompt", event.target.value)
                      }
                      className="rounded-md border border-neutral-300 bg-neutral-50 p-3 font-mono text-xs leading-5"
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium">
                    Task prompt
                    <textarea
                      aria-label="Task prompt"
                      rows={5}
                      value={String(configuration.task_prompt ?? "")}
                      onChange={(event) =>
                        setConfigText("task_prompt", event.target.value)
                      }
                      className="rounded-md border border-neutral-300 bg-neutral-50 p-3 font-mono text-xs leading-5"
                    />
                  </label>
                </div>
              ) : (
                <div className="grid gap-4">
                  <label className="grid gap-1 text-sm font-medium">
                    Skill description
                    <input
                      aria-label="Skill description"
                      value={String(configuration.description ?? "")}
                      onChange={(event) =>
                        setConfigText("description", event.target.value)
                      }
                      className="rounded-md border border-neutral-300 p-2"
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium">
                    SKILL.md instructions
                    <textarea
                      aria-label="Skill instructions"
                      rows={14}
                      value={String(configuration.instructions_markdown ?? "")}
                      onChange={(event) =>
                        setConfigText(
                          "instructions_markdown",
                          event.target.value
                        )
                      }
                      className="rounded-md border border-neutral-300 bg-neutral-950 p-3 font-mono text-xs leading-5 text-lime-100"
                    />
                  </label>
                </div>
              )}

              <label className="mt-4 grid gap-1 text-sm font-medium">
                Change reason and expected effect
                <textarea
                  aria-label="Change reason"
                  rows={3}
                  value={changeReason}
                  onChange={(event) => setChangeReason(event.target.value)}
                  placeholder="Example: Reduce false refusals seen in reviewed sessions."
                  className="rounded-md border border-neutral-300 p-3"
                />
              </label>
              <div className="mt-4 flex justify-end">
                <ActionButton
                  disabled={
                    !selectedTarget || changeReason.trim().length < 3 || !!busy
                  }
                  onClick={saveCandidate}
                >
                  {busy === "candidate" ? "Saving…" : "Save candidate"}
                </ActionButton>
              </div>
            </div>
          </section>

          <section className="grid gap-5 lg:grid-cols-2">
            <div className="border border-neutral-300 bg-white p-5">
              <div className="font-mono text-xs uppercase tracking-widest text-neutral-500">
                Frozen evidence
              </div>
              <h2 className="mt-2 text-xl font-semibold">
                Create a release dataset
              </h2>
              <div className="mt-4 grid gap-3">
                <input
                  aria-label="Dataset name"
                  value={datasetName}
                  onChange={(event) => setDatasetName(event.target.value)}
                  placeholder="Dataset name"
                  className="rounded-md border border-neutral-300 p-2 text-sm"
                />
                <textarea
                  aria-label="Test input"
                  rows={3}
                  value={testInput}
                  onChange={(event) => setTestInput(event.target.value)}
                  placeholder="User input"
                  className="rounded-md border border-neutral-300 p-2 text-sm"
                />
                <textarea
                  aria-label="Expected outcome"
                  rows={3}
                  value={expectedOutcome}
                  onChange={(event) => setExpectedOutcome(event.target.value)}
                  placeholder="Expected outcome"
                  className="rounded-md border border-neutral-300 p-2 text-sm"
                />
                <div className="flex justify-end">
                  <ActionButton
                    tone="light"
                    disabled={!datasetName || !testInput || !!busy}
                    onClick={createDataset}
                  >
                    {busy === "dataset" ? "Freezing…" : "Create and freeze"}
                  </ActionButton>
                </div>
              </div>
              <div className="mt-4 divide-y divide-neutral-200 border-t border-neutral-300">
                {datasets?.slice(0, 4).map((dataset) => (
                  <div
                    key={dataset.id}
                    className="flex items-center justify-between py-2 text-sm"
                  >
                    <span>
                      {dataset.name} v{dataset.version}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-xs">
                        {dataset.case_count} cases
                      </span>
                      <StatusPill status={dataset.status} />
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-neutral-300 bg-neutral-950 p-5 text-white">
              <div className="font-mono text-xs uppercase tracking-widest text-lime-300">
                Release gates
              </div>
              <h2 className="mt-2 text-xl font-semibold">
                Prove before traffic
              </h2>
              <p className="mt-2 text-sm text-neutral-400">
                Candidate score must reach 0.70, match the baseline, keep
                success rate, and produce no unsafe output.
              </p>
              <div className="mt-5 space-y-3">
                {versions
                  ?.filter((version) => version.status !== "production")
                  .map((version) => {
                    const passedRun = selectedRunFor(version.id);
                    return (
                      <div
                        key={version.id}
                        className="border border-neutral-700 bg-neutral-900 p-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="font-mono text-sm">
                            v{version.version_number}
                          </div>
                          <StatusPill status={version.status} />
                        </div>
                        <p className="mt-2 text-xs text-neutral-400">
                          {version.change_reason}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {version.status === "draft" && (
                            <ActionButton
                              tone="light"
                              disabled={!frozenDataset || !!busy}
                              onClick={() =>
                                frozenDataset &&
                                runEvaluation(version.id, frozenDataset.id)
                              }
                            >
                              {busy === `run-${version.id}`
                                ? "Evaluating…"
                                : "Run offline eval"}
                            </ActionButton>
                          )}
                          {passedRun && version.status === "draft" && (
                            <ActionButton
                              disabled={!!busy}
                              onClick={() => approve(version.id)}
                            >
                              Approve
                            </ActionButton>
                          )}
                          {passedRun && version.status === "approved" && (
                            <ActionButton
                              disabled={!!busy}
                              onClick={() =>
                                startCanary(version.id, passedRun.id)
                              }
                            >
                              Start 10% canary
                            </ActionButton>
                          )}
                        </div>
                      </div>
                    );
                  })}
                {!versions?.some(
                  (version) => version.status !== "production"
                ) && (
                  <div className="border border-dashed border-neutral-700 p-6 text-center text-sm text-neutral-500">
                    Save a candidate to start the gate sequence.
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="border border-neutral-300 bg-white p-5">
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="font-mono text-xs uppercase tracking-widest text-neutral-500">
                  Live control
                </div>
                <h2 className="mt-2 text-xl font-semibold">Canary releases</h2>
              </div>
              <span className="text-xs text-neutral-500">
                Stable by user + session
              </span>
            </div>
            <div className="mt-4 divide-y divide-neutral-200 border-y border-neutral-300">
              {canaries?.map((canary) => (
                <div
                  key={canary.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono">#{canary.id}</span>
                    <StatusPill status={canary.status} />
                    <span>{canary.traffic_percentage}% traffic</span>
                  </div>
                  {canary.status === "running" && (
                    <div className="flex gap-2">
                      <ActionButton
                        tone="danger"
                        disabled={!!busy}
                        onClick={() => changeCanary(canary.id, "stop")}
                      >
                        Stop
                      </ActionButton>
                      <ActionButton
                        disabled={!!busy}
                        onClick={() => changeCanary(canary.id, "promote")}
                      >
                        Promote
                      </ActionButton>
                    </div>
                  )}
                </div>
              ))}
              {!canaries?.length && (
                <div className="py-6 text-center text-sm text-neutral-500">
                  No canary release yet.
                </div>
              )}
            </div>
          </section>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
