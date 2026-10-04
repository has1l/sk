import type { ToggleOption } from "../types";

/** Переключатели разреза, метрики, периода и вида. Пересчёт мгновенный:
 *  модель не участвует, новая выборка не нужна. */
export function Toggles({
  toggles,
  busy,
  onChange,
}: {
  toggles: ToggleOption[];
  busy: boolean;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="toggles">
      {toggles.map((toggle) => (
        <label className="toggle" key={toggle.key}>
          <span>{toggle.label}</span>
          <select
            value={toggle.value}
            disabled={busy}
            onChange={(event) => onChange(toggle.key, event.target.value)}
          >
            {toggle.options.map((option) => (
              <option value={option.value} key={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
