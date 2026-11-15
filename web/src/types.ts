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
  kind: "bar" | "hbar" | "line" | "pie" | "area" | "waterfall";
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

/** Ячейка раскладки. Координат нет: место задаётся порядком в списке, строки
 *  считает укладка. Несколько панелей в ячейке — склеенная коробка с
 *  вкладками внутри. */
export interface Slot {
  id: string;
  w: number;
  panels: string[];
  active: number;
}

export interface BoardTab {
  id: string;
  title: string;
  slots: Slot[];
}

export interface Layout {
  columns: number;
  tabs: BoardTab[];
  active: string;
}

/** Выбор для своей панели. Подписи приходят с сервера: клиент никогда не
 *  строит их из имени поля. */
export interface Choice {
  value: string;
  label: string;
}

export interface PanelOptions {
  dimensions: Choice[];
  metrics: Choice[];
  charts: Choice[];
}

export interface PanelDraft {
  dimension: string;
  metric: string;
  chart: string;
  limit?: number;
}

export interface Dashboard {
  kpis: Kpi[];
  panels: ChartPanel[];
  filters: FilterOption[];
  toggles: ToggleOption[];
  layout: Layout;
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

export interface GapFactor {
  label: string;
  value: number;
  share: number;
  direction: "drag" | "lift";
}

export interface GapLevel {
  dimension: string;
  label: string;
  factors: GapFactor[];
}

export interface Decomposition {
  headline: string;
  total: number;
  unit: Unit;
  levels: GapLevel[];
  chain: string[];
}

export interface Anomaly {
  label: string;
  text: string;
  severity: "high" | "medium";
  dimension: string;
}

export interface Formula {
  field: string;
  title: string;
  kind: string;
  expression: string;
  inputs: string[];
}

/** Происхождение цифр: чем именно обеспечено то, что бот не навредит. */
export interface Provenance {
  sql: string | null;
  role: string;
  statement_timeout: string;
  read_only: boolean;
  row_count: number;
  load_ms: number;
  model: string;
  llm_calls: number;
  formulas: Formula[];
  guarantees: string[];
}

export interface TimelineEntry {
  id: string;
  label: string;
  at: string;
  summary: string;
  current: boolean;
}

/** Шаг разбора реплики, приходящий потоком, пока бот работает. */
export interface Stage {
  text: string;
  detail: string;
}

export interface SessionView {
  session_id: string;
  title: string;
  question: string;
  spec: unknown;
  view: ViewState;
  recipe: unknown;
  steps: StepView[];
  table: Table;
  dashboard: Dashboard;
  summary: string;
  insights: string[];
  anomalies: Anomaly[];
  decomposition: Decomposition | null;
  provenance: Provenance | null;
  timeline: TimelineEntry[];
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
  stages?: Stage[];
  /** Реплика-пасхалка: ответа сервера за ней нет, только настроение зверька.
   *  Отдельное поле, а не поддельный AskResponse: подделка однажды утечёт в
   *  код, который ждёт настоящие данные. */
  pet?: string;
  petSay?: string;
}

/** Черновик: рецепт анализа, а не данные. Лежит в браузере, переживает
 *  перезагрузку страницы и перезапуск сервера — сессия на сервере не
 *  переживает ни того, ни другого. */
export interface Draft {
  title: string;
  question: string;
  recipe: unknown;
  at: number;
}
