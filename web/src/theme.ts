/**
 * Единственный источник цвета. Палитра взята из проверенного набора и прогнана
 * валидатором в обеих темах: соседние пары расходятся по CVD, светлая тема даёт
 * предупреждение по контрасту на трёх слотах — страховка от него это таблица с
 * данными, которая в интерфейсе есть всегда.
 *
 * Правило, которое нельзя нарушать: цвет закреплён за сущностью, а не за местом
 * в списке. План всегда синий, факт всегда оранжевый — на всех графиках.
 */

export type Mode = "light" | "dark";

export const CATEGORICAL: Record<Mode, string[]> = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};

/** Статусные цвета не участвуют в темах и никогда не достаются серии. */
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

export const CHROME: Record<Mode, Record<string, string>> = {
  light: {
    surface: "#fcfcfb",
    plane: "#f9f9f7",
    inkPrimary: "#0b0b0b",
    inkSecondary: "#52514e",
    inkMuted: "#898781",
    grid: "#e1e0d9",
    baseline: "#c3c2b7",
    border: "rgba(11,11,11,0.10)",
  },
  dark: {
    surface: "#1a1a19",
    plane: "#0d0d0d",
    inkPrimary: "#ffffff",
    inkSecondary: "#c3c2b7",
    inkMuted: "#898781",
    grid: "#2c2c2a",
    baseline: "#383835",
    border: "rgba(255,255,255,0.10)",
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

export function currentMode(): Mode {
  const stamped = document.documentElement.dataset.theme;
  if (stamped === "dark" || stamped === "light") return stamped;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
