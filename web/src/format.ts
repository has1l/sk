/** Русские числа и даты. Интерфейс продукта на русском целиком. */

const NBSP = " ";

export function money(value: number): string {
  if (Math.abs(value) >= 1e9) return `${decimal(value / 1e9, 2)}${NBSP}млрд${NBSP}₽`;
  if (Math.abs(value) >= 1e6) return `${decimal(value / 1e6, 1)}${NBSP}млн${NBSP}₽`;
  return `${grouped(Math.round(value))}${NBSP}₽`;
}

export function compactMoney(value: number): string {
  if (Math.abs(value) >= 1e9) return `${decimal(value / 1e9, 1)}${NBSP}млрд`;
  if (Math.abs(value) >= 1e6) return `${decimal(value / 1e6, 0)}${NBSP}млн`;
  if (Math.abs(value) >= 1e3) return `${decimal(value / 1e3, 0)}${NBSP}тыс`;
  return grouped(value);
}

export function count(value: number): string {
  return grouped(Math.round(value));
}

export function percent(value: number, digits = 1): string {
  return `${decimal(value, digits)}%`;
}

function grouped(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value).replace(/\s/g, NBSP);
}

function decimal(value: number, digits: number): string {
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
    .format(value)
    .replace(/\s/g, NBSP);
}

export const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const ROMAN = ["I", "II", "III", "IV"];

/** Даты из базы приходят первым днём периода — показываем сам период. */
export function periodLabel(iso: string, field: string): string {
  const [year, month] = iso.split("-").map(Number);
  if (field === "year") return String(year);
  if (field === "quarter") return `${ROMAN[Math.floor((month - 1) / 3)]}${NBSP}кв.${NBSP}${year}`;
  return `${MONTHS[month - 1]}${NBSP}${year}`;
}

export function cellValue(value: unknown, unit: string, field: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") {
    return /^\d{4}-\d{2}-\d{2}$/.test(value) ? periodLabel(value, field) : value;
  }
  if (typeof value !== "number") return String(value);
  if (unit === "rub") return money(value);
  if (unit === "percent") return percent(value);
  if (unit === "rank") return String(Math.round(value));
  return count(value);
}

export function signedPercent(value: number, digits = 1): string {
  return `${value >= 0 ? "+" : "−"}${decimal(Math.abs(value), digits)}%`;
}

export function signedMoney(value: number): string {
  return `${value >= 0 ? "+" : "−"}${money(Math.abs(value))}`;
}

/** Значение KPI-карточки. Знак у дельты обязателен: «−119,5 млн ₽» и
 *  «119,5 млн ₽» — разные новости. */
export function kpiValue(value: number | null, unit: string, kind: string): string {
  if (value === null) return "—";
  if (unit === "percent") return kind === "delta" ? signedPercent(value) : percent(value);
  if (unit === "rub") return kind === "delta" ? signedMoney(value) : money(value);
  return count(value);
}

/** Названия точек в датасете содержат адрес целиком — на оси это каша. */
export function shortLabel(value: string, limit = 26): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1).trimEnd()}…`;
}

export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Русские числительные: «1 панель», «2 панели», «5 панелей». Нужны везде, где
 *  к числу приписывается существительное — без них интерфейс говорит
 *  «5 панели» и сразу выглядит машинным переводом. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
