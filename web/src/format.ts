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

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
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
  return count(value);
}
