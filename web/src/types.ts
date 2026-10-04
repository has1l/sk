export type Unit = "rub" | "qty" | "count" | "none";

export interface Column {
  field: string;
  label: string;
  kind: "dimension" | "metric";
  unit: Unit;
}

export interface Table {
  columns: Column[];
  rows: Record<string, string | number | null>[];
  row_count: number;
}

export interface Series {
  field: string;
  label: string;
}

export interface ChartSpec {
  kind: "bar" | "line";
  title: string;
  x_field: string;
  x_label: string;
  y_label: string;
  series: Series[];
  stacked: boolean;
}

export interface Clarification {
  question: string;
  reason: string;
}

export interface AskResponse {
  message: string;
  spec: unknown | null;
  table: Table | null;
  chart: ChartSpec | null;
  clarification: Clarification | null;
  notes: string[];
  sql: string | null;
}

export interface ChatTurn {
  id: string;
  question: string;
  state: "pending" | "done" | "error";
  answer?: AskResponse;
  error?: string;
}
