import type {
  AskResponse,
  Draft,
  Layout,
  PanelDraft,
  PanelOptions,
  QueryTemplate,
  SavedDashboard,
  SavedVersion,
  SessionView,
  Stage,
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

/** То же, что ask, но с показом хода работы.
 *
 *  Спиннер не отличает работу от зависания, поэтому шаги разбора приходят
 *  потоком и показываются по мере готовности. Ответ в конце — тот же самый. */
export async function askStream(
  question: string,
  sessionId: string | null,
  onStage: (stage: Stage) => void,
): Promise<AskResponse> {
  const response = await fetch("/api/ask/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Сервер ответил ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AskResponse | null = null;
  let failure: string | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Событие кончается пустой строкой; хвост без неё дочитываем следующим куском.
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = /^event: (.+)$/m.exec(chunk)?.[1];
      const data = chunk
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "stage") onStage(payload as Stage);
      else if (event === "result") result = payload as AskResponse;
      else if (event === "error") failure = payload.detail ?? "неизвестная ошибка";
    }
  }

  if (failure) throw new Error(failure);
  if (!result) throw new Error("сервер не прислал ответ");
  return result;
}

/** Фильтры и переключатели: пересчёт без модели и без новой выборки. */
export function setView(sessionId: string, view: ViewState): Promise<SessionView> {
  return call("/api/view", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, view }),
  });
}

export function setLayout(sessionId: string, layout: Layout): Promise<SessionView> {
  return call("/api/layout", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, layout }),
  });
}

/** Из чего можно собрать свою панель. Справочник, сессии не требует. */
export function panelOptions(): Promise<PanelOptions> {
  return call("/api/panel-options");
}

/** Своя панель. Ячейку в раскладке клиент не создаёт — согласование на
 *  сервере само допишет её в конец открытой вкладки. */
export function addPanel(sessionId: string, panel: PanelDraft): Promise<SessionView> {
  return call(`/api/session/${sessionId}/panel`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, ...panel }),
  });
}

export function removePanel(sessionId: string, panelId: string): Promise<SessionView> {
  return call(`/api/session/${sessionId}/panel/${panelId}`, { method: "DELETE" });
}

export function undo(sessionId: string): Promise<AskResponse> {
  return call(`/api/session/${sessionId}/undo`, { method: "POST" });
}

/** Возврат к произвольной точке переписки, а не только к предыдущей. */
export function rewind(sessionId: string, snapshotId: string): Promise<AskResponse> {
  return call(`/api/session/${sessionId}/rewind/${snapshotId}`, { method: "POST" });
}

export function restoreDraft(draft: Draft): Promise<AskResponse> {
  return call("/api/draft/restore", {
    method: "POST",
    body: JSON.stringify({ recipe: draft.recipe }),
  });
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
