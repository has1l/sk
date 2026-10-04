import type {
  AskResponse,
  SavedDashboard,
  SavedVersion,
  SessionView,
  QueryTemplate,
  ViewState,
} from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Сервер ответил ${response.status}`);
  }
  return response.json();
}

export function ask(question: string, sessionId: string | null): Promise<AskResponse> {
  return call("/api/ask", {
    method: "POST",
    body: JSON.stringify({ question, session_id: sessionId }),
  });
}

/** Фильтры и переключатели: пересчёт без модели и без новой выборки. */
export function setView(sessionId: string, view: ViewState): Promise<SessionView> {
  return call("/api/view", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, view }),
  });
}

export function undo(sessionId: string): Promise<AskResponse> {
  return call(`/api/session/${sessionId}/undo`, { method: "POST" });
}

export function dropStep(sessionId: string, stepId: string): Promise<AskResponse> {
  return call(`/api/session/${sessionId}/step/${stepId}`, { method: "DELETE" });
}

export function listDashboards(q = "", sort = "updated"): Promise<SavedDashboard[]> {
  const query = new URLSearchParams({ sort });
  if (q) query.set("q", q);
  return call(`/api/dashboards?${query}`);
}

export function saveDashboard(
  sessionId: string,
  title: string | null,
  asNew = false,
): Promise<AskResponse> {
  return call("/api/dashboards", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, title, as_new: asNew }),
  });
}

export function openDashboard(id: string): Promise<AskResponse> {
  return call(`/api/dashboards/${id}/open`);
}

export function renameDashboard(id: string, title: string): Promise<SavedDashboard[]> {
  return call(`/api/dashboards/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
}

export function copyDashboard(id: string): Promise<AskResponse> {
  return call(`/api/dashboards/${id}/copy`, { method: "POST" });
}

export function deleteDashboard(id: string): Promise<SavedDashboard[]> {
  return call(`/api/dashboards/${id}`, { method: "DELETE" });
}

export function listVersions(id: string): Promise<SavedVersion[]> {
  return call(`/api/dashboards/${id}/versions`);
}

export function openVersion(id: string, version: number): Promise<AskResponse> {
  return call(`/api/dashboards/${id}/versions/${version}/open`, { method: "POST" });
}

export function listTemplates(): Promise<QueryTemplate[]> {
  return call("/api/templates");
}

export const exportCsvUrl = (sessionId: string) => `/api/export/csv/${sessionId}`;
export const exportHtmlUrl = (sessionId: string) => `/api/export/html/${sessionId}`;
