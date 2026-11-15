/**
 * Единственный источник цвета. Палитра подобрана под тёплую бумагу интерфейса
 * и прогнана валидатором (skill dataviz) в обеих темах: полоса светлоты,
 * насыщенность, расхождение соседних пар при дальтонизме, нормальное зрение и
 * контраст к поверхности. Обе проходят все пять проверок без предупреждений —
 * прежняя холодная палитра не дотягивала по контрасту на трёх слотах.
 *
 * Светлая проверена на поверхности #fbfaf7, тёмная — на #232220, отдельным
 * подбором: тёмная тема не получается переворотом светлой, у неё своя полоса
 * светлоты (0,48–0,67 против 0,43–0,77).
 *
 * Правило, которое нельзя нарушать: цвет закреплён за сущностью, а не за местом
 * в списке. План всегда слот 1, факт всегда слот 2 — на всех графиках.
 */

export type Mode = "light" | "dark";

export const CATEGORICAL: Record<Mode, string[]> = {
  light: ["#2f7ab8", "#c65a2e", "#1f9b7a", "#a87d12", "#9a4f9e", "#4a9e2f", "#d1577e", "#5a56c4"],
  dark: ["#4a8cc0", "#d2693c", "#25a07e", "#b88a16", "#a566aa", "#4da033", "#db6a8d", "#7b76dc"],
};

/** Статусные цвета никогда не достаются серии. Набор свой на каждую тему:
 *  один цвет не вытягивает и текст KPI на светлой бумаге (нужно 4,5:1), и
 *  заливку столбца на тёмной. Светлые значения проверены на фоне #f5f4ee:
 *  good 4,6:1, warning 5,2:1, serious 4,6:1, critical 6,0:1. */
export const STATUS_BY_MODE: Record<Mode, Record<string, string>> = {
  light: {
    good: "#3f7d3f",
    warning: "#8a5e0c",
    serious: "#a85518",
    critical: "#a93226",
  },
  dark: {
    good: "#6fbf6f",
    warning: "#d9a441",
    serious: "#e08a52",
    critical: "#e0705f",
  },
};

/** Поверхности графика. Держатся вровень с токенами `styles.css`: график на
 *  холодно-сером фоне посреди тёплой бумаги читается как чужая заплатка. */
export const CHROME: Record<Mode, Record<string, string>> = {
  light: {
    surface: "#fbfaf7",
    plane: "#f5f4ee",
    inkPrimary: "#1f1e1c",
    inkSecondary: "#5a574e",
    inkMuted: "#8c887c",
    grid: "#e6e3d8",
    baseline: "#c7c2b2",
    border: "rgba(31,30,28,0.09)",
  },
  dark: {
    surface: "#232220",
    plane: "#1b1a17",
    inkPrimary: "#efede4",
    inkSecondary: "#b5b0a3",
    inkMuted: "#8a857a",
    grid: "#302e2a",
    baseline: "#413e38",
    border: "rgba(239,237,228,0.10)",
  },
};

/** Закреплённые роли метрик. Порядок серий на графике их не меняет. */
const METRIC_SLOT: Record<string, number> = {
  plan_amount: 0,
  plan_qty: 0,
  fact_amount: 1,
  fact_qty: 1,
  sales_count: 2,
};

export function metricColor(field: string, mode: Mode, fallbackIndex: number): string {
  const slots = CATEGORICAL[mode];
  const slot = METRIC_SLOT[field];
  return slots[slot ?? fallbackIndex % slots.length];
}

/**
 * Цвет сущности. Привязан к имени, а не к месту в списке: переключение разреза
 * или сортировки не должно перекрашивать Центральный регион из синего в
 * оранжевый — иначе два графика рядом рассказывают разные истории.
 */
/** «Прочее» — свёрнутый хвост, а не сущность: слот палитры ему не положен.
 *  Получив цвет, он спорил бы с настоящими значениями, хотя часто занимает
 *  больше половины круга. */
export const OTHER_LABEL = "Прочее";
const OTHER_COLOR: Record<Mode, string> = { light: "#a8a294", dark: "#5c5850" };

export function entityColor(name: string, mode: Mode, universe: string[]): string {
  if (name === OTHER_LABEL) return OTHER_COLOR[mode];
  const slots = CATEGORICAL[mode];
  const order = universe.filter((n) => n !== OTHER_LABEL).sort((a, b) => a.localeCompare(b, "ru"));
  const at = order.indexOf(name);
  return slots[(at < 0 ? 0 : at) % slots.length];
}

/** Статусные цвета — только для статуса. Серии их не получают никогда. */
export function statusColor(status: string, mode: Mode): string | undefined {
  if (status === "neutral") return undefined;
  return STATUS_BY_MODE[mode][status];
}

/** Фон зон пере- и недовыполнения под линией 100%. Намеренно почти незаметный:
 *  это подложка, а не ещё одна серия. */
export const ZONE = {
  good: "rgba(63,125,63,0.06)",
  bad: "rgba(169,50,38,0.06)",
} as const;

export function currentMode(): Mode {
  const stamped = document.documentElement.dataset.theme;
  if (stamped === "dark" || stamped === "light") return stamped;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Выбор темы: «system» отдаёт решение операционной системе, иначе тема
 *  закрепляется явно. Нужен не для красоты — на проекторе в светлом зале
 *  тёмная тема проваливается, и переключить её надо за секунду, а не через
 *  настройки macOS.
 *
 *  Графики Plotly живут вне CSS: цвета уходят в layout, поэтому на смену темы
 *  они обязаны перерисоваться. Сигналом служит событие, а не только
 *  matchMedia: при явном выборе системная настройка не меняется. */
export type ThemeChoice = Mode | "system";

const THEME_KEY = "puzzle.theme";
export const THEME_EVENT = "puzzle:theme";

export function storedTheme(): ThemeChoice {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* приватный режим — просто идём за системой */
  }
  return "system";
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* не сохранилось — тема живёт до перезагрузки */
  }
  window.dispatchEvent(new CustomEvent(THEME_EVENT));
}
