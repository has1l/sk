import type { SessionView, ViewState } from "./types";

/** Один шаг показа: куда ведём курсор, что говорим и что при этом реально
 *  происходит. `run` не обязателен — на обзорном проходе курсор только
 *  объясняет, ничего не трогая. */
export type Move = {
  at: string;
  say: string;
  run?: () => void;
  hold?: number;
};

const TOGGLE_WORD: Record<string, string> = {
  primary: "разрез",
  metric: "метрика",
  period_grain: "зерно периода",
  mode: "вид",
};

/** Обзор только что собранного дашборда: курсор проходит по частям и
 *  называет, что откуда взялось. Ничего не меняет — дашборд уже собран,
 *  переставлять его заново было бы спектаклем, а не объяснением. */
export function tour(session: SessionView): Move[] {
  const moves: Move[] = [
    {
      at: ".kpis",
      say: `Итог: ${session.summary || session.title}`,
      hold: 1100,
    },
  ];

  for (const toggle of session.dashboard.toggles) {
    const chosen = toggle.options.find((o) => o.value === toggle.value);
    if (!chosen) continue;
    moves.push({
      at: `[data-toggle="${toggle.key}"]`,
      say: `${toggle.label}: ${chosen.label} — это ${TOGGLE_WORD[toggle.key] ?? "настройка"}, его задал ваш вопрос`,
      hold: 850,
    });
  }

  for (const filter of session.dashboard.filters) {
    if (!filter.selected.length) continue;
    moves.push({
      at: `[data-filter="${filter.dimension}"]`,
      say: `${filter.label}: ${filter.selected.slice(0, 2).join(", ")}${filter.selected.length > 2 ? " и ещё…" : ""}`,
      hold: 900,
    });
  }

  const slots = session.dashboard.layout.tabs
    .find((t) => t.id === session.dashboard.layout.active)
    ?.slots ?? [];
  for (const slot of slots.slice(0, 4)) {
    const id = slot.panels[slot.active] ?? slot.panels[0];
    const panel = session.dashboard.panels.find((p) => p.id === id);
    if (!panel) continue;
    moves.push({ at: `[data-slot="${slot.id}"]`, say: panel.spec.title, hold: 700 });
  }

  if (session.steps.length) {
    moves.push({
      at: ".steps",
      say: `Вычислений поверх таблицы: ${session.steps.length}`,
      hold: 900,
    });
  }

  return moves;
}

/** Правка готового дашборда. Здесь курсор не объясняет, а делает: каждый шаг
 *  уходит на сервер тем же путём, что и ручное переключение. Разница с
 *  обзором принципиальная — показываем настоящую работу, а не её имитацию. */
export function edits(
  before: ViewState,
  after: ViewState,
  session: SessionView,
  apply: (view: ViewState) => void,
): Move[] {
  const moves: Move[] = [];
  let running: ViewState = { ...before };

  const step = (next: Partial<ViewState>) => {
    running = { ...running, ...next };
    const snapshot = running;
    return () => apply(snapshot);
  };

  for (const toggle of session.dashboard.toggles) {
    const key = toggle.key as keyof ViewState;
    const was = before[key];
    const now = after[key];
    if (was === now || typeof now !== "string") continue;
    const chosen = toggle.options.find((o) => o.value === now);
    moves.push({
      at: `[data-toggle="${toggle.key}"]`,
      say: `${toggle.label} → ${chosen?.label ?? now}`,
      run: step({ [key]: now } as Partial<ViewState>),
      hold: 650,
    });
  }

  const had = new Map(before.filters.map((f) => [f.dimension, f.values.join("|")]));
  for (const filter of after.filters) {
    if (had.get(filter.dimension) === filter.values.join("|")) continue;
    const label = session.dashboard.filters.find((f) => f.dimension === filter.dimension)?.label;
    moves.push({
      at: `[data-filter="${filter.dimension}"]`,
      say: `${label ?? filter.dimension}: ${filter.values.slice(0, 2).join(", ")}`,
      run: step({ filters: [...running.filters.filter((f) => f.dimension !== filter.dimension), filter] }),
      hold: 750,
    });
  }

  const gone = before.filters.filter(
    (f) => !after.filters.some((n) => n.dimension === f.dimension),
  );
  for (const filter of gone) {
    const label = session.dashboard.filters.find((f) => f.dimension === filter.dimension)?.label;
    moves.push({
      at: `[data-filter="${filter.dimension}"]`,
      say: `${label ?? filter.dimension}: фильтр снят`,
      run: step({ filters: running.filters.filter((f) => f.dimension !== filter.dimension) }),
      hold: 650,
    });
  }

  return moves;
}
