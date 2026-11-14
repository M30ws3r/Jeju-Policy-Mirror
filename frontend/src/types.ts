export type Level = "A" | "B" | "C";
export type CheckStatus = "pass" | "warn" | "fail";

export interface Meta {
  data_mode: "sample" | "real";
  data_label: string;
  auth_required: boolean;
  areas: string[];
  industries: string[];
  first_month: string;
  last_month: string;
  signed_in: boolean;
}

export interface Estimate {
  effect_pct: number;
  ci_low: number;
  ci_high: number;
  p_value: number;
  n_months: number;
  method?: string;
  ci_method?: string;
  industry?: string;
}

export interface Check {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  required: boolean;
}

export interface Spec {
  area: string | null;
  policy_month: string | null;
  industry: string;
  policy_label: string;
  missing: string[];
  parsed_by: string;
}

export interface Step {
  name: string;
  summary: string;
}

export interface AnalysisResult {
  status: "done" | "needs_input";
  message?: string;
  analysis_id?: string;
  question: string;
  spec: Spec;
  data_source: { mode: string; label: string; datasets: string[] };
  steps: Step[];
  controls?: { area: string; score: number; corr: number; rmse: number }[];
  excluded_neighbors?: string[];
  estimates?: {
    did?: Estimate;
    did_unadjusted?: Estimate;
    negative_control?: Estimate;
    mechanism_bus?: Estimate;
    placebo_space?: { p_value: number | null; n_placebos: number };
  };
  observed?: { area_yoy_pct?: number; island_yoy_pct?: number; before_after_pct?: number | null };
  checks?: Check[];
  verdict?: { level: Level; title: string; statement: string; causal_language_allowed: boolean; plain_explanation?: string };
  series?: { months?: string[]; treated?: number[]; control?: number[] };
  limitations?: string[];
}

export interface ApiError {
  code: string;
  message: string;
  fields?: string[];
}
