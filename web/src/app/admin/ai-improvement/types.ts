export type TargetType = "agent" | "custom_skill" | "builtin_skill";

export interface ConfigurationVersion {
  id: number;
  target_type: TargetType;
  target_id: string;
  version_number: number;
  status: string;
  base_version_id: number | null;
  configuration: Record<string, unknown>;
  change_reason: string;
  time_created: string;
}

export interface ImprovementTarget {
  target_type: TargetType;
  target_id: string;
  name: string;
  description: string;
  production_version: ConfigurationVersion;
}

export interface EvaluationDataset {
  id: number;
  name: string;
  description: string;
  version: number;
  status: string;
  case_count: number;
  time_created: string;
}

export interface EvaluationRun {
  id: number;
  candidate_version_id: number;
  baseline_version_id: number;
  dataset_id: number;
  status: string;
  gates_passed: boolean | null;
  summary: Record<string, unknown>;
  time_created: string;
}

export interface CanaryRelease {
  id: number;
  candidate_version_id: number;
  baseline_version_id: number;
  evaluation_run_id: number;
  traffic_percentage: number;
  status: string;
  automatic_stop_reason: string | null;
}
