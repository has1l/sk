/** Зеркало контракта бэкенда. Расходиться им нельзя: клиент ничего не считает. */

export type Unit = "rub" | "qty" | "count" | "percent" | "rank" | "none";
export type Status = "good" | "warning" | "serious" | "critical" | "neutral";

export interface Column {
  field: string;
  label: string;
  kind: "dimension" | "metric" | "calc";
  unit: Unit;
}

export type Row = Record<string, string | number | null>;

export interface Table {
  columns: Column[];
  rows: Row[];
  row_count: number;
}

export interface Series {
  field: string;
  label: string;
  unit: Unit;
}

export interface ChartSpec {
  kind: "bar" | "hbar" | "line" | "pie" | "area";
  title: string;
  x_field: string;
  x_label: string;
  y_label: string;
  series: Series[];
  stacked: boolean;
  reference: number | null;
  zoom_group: string | null;
}

export interface ChartPanel {
  id: string;
  spec: ChartSpec;
  table: Table;
  note: string | null;
}

export interface Kpi {
  key: string;
  label: string;
  value: number | null;
  unit: Unit;
  kind: "value" | "delta" | "percent";
  status: Status;
  hint: string | null;
}

export interface FilterOption {
  dimension: string;
  label: string;
  values: string[];
  selected: string[];
  parent: string | null;
}

export interface ToggleOption {
  key: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
}

export interface Dashboard {
  kpis: Kpi[];
  panels: ChartPanel[];
  filters: FilterOption[];
  toggles: ToggleOption[];
}

export interface AppliedFilter {
  dimension: string;
  values: string[];
}

export interface ViewState {
  primary: string;
  period_grain: "month" | "quarter" | "year";
  metric: string;
  mode: "absolute" | "percent" | "growth";
  table_dimensions: string[];
  filters: AppliedFilter[];
  date_from: string | null;
  date_to: string | null;
  sort_field: string | null;
  sort_order: "asc" | "desc";
  limit: number | null;
}

export interface StepView {
  id: string;
  title: string;
  field: string;
  formula: string;
}

export interface SessionView {
  session_id: string;
  title: string;
  question: string;
  spec: unknown;
  view: ViewState;
  steps: StepView[];
  table: Table;
  dashboard: Dashboard;
  insights: string[];
  notes: string[];
  sql: string | null;
  saved_id: string | null;
  dirty: boolean;
}

export interface Clarification {
  question: string;
  reason: string;
}

export interface SavedDashboard {
  id: string;
  title: string;
  question: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SavedVersion {
  version: number;
  title: string;
  note: string;
  created_at: string;
}

export interface QueryTemplate {
  group: string;
  question: string;
}

export interface AskResponse {
  message: string;
  session: SessionView | null;
  clarification: Clarification | null;
  saved: SavedDashboard[] | null;
  action: string | null;
}

export interface ChatTurn {
  id: string;
  question: string | null;
  state: "pending" | "done" | "error";
  answer?: AskResponse;
  error?: string;
}
