import { useMemo, useState } from "react";

import type { FilterOption } from "../types";

const VISIBLE = 80;

/** Фильтр с поиском и мультивыбором. Триста точек в списке — поиск обязателен,
 *  и он идёт по уже загруженным значениям, без запроса на сервер. */
function FilterBox({
  option,
  busy,
  onToggle,
  onClear,
}: {
  option: FilterOption;
  busy: boolean;
  onToggle: (dimension: string, value: string) => void;
  onClear: (dimension: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const found = useMemo(() => {
    const folded = query.trim().toLowerCase();
    const list = folded
      ? option.values.filter((v) => v.toLowerCase().includes(folded))
      : option.values;
    return list;
  }, [option.values, query]);

  const chosen = option.selected.length;
  return (
    <div className={`filter ${open ? "open" : ""}`}>
      <button className="filter-head" disabled={busy} onClick={() => setOpen((v) => !v)}>
        <span className="filter-label">{option.label}</span>
        <span className="filter-state">
          {chosen ? `${chosen} из ${option.values.length}` : `все · ${option.values.length}`}
        </span>
      </button>

      {open && (
        <div className="filter-body">
          <input
            value={query}
            placeholder="Поиск…"
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
          />
          <div className="filter-list">
            {found.slice(0, VISIBLE).map((value) => (
              <label key={value} title={value}>
                <input
                  type="checkbox"
                  checked={option.selected.includes(value)}
                  disabled={busy}
                  onChange={() => onToggle(option.dimension, value)}
                />
                <span>{value}</span>
              </label>
            ))}
            {!found.length && <p className="filter-empty">Ничего не нашлось</p>}
            {found.length > VISIBLE && (
              <p className="filter-empty">
                Показаны первые {VISIBLE} из {found.length} — уточните поиск
              </p>
            )}
          </div>
          {chosen > 0 && (
            <button className="link" disabled={busy} onClick={() => onClear(option.dimension)}>
              Сбросить {option.label.toLowerCase()}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function Filters({
  filters,
  busy,
  onToggle,
  onClear,
  onClearAll,
}: {
  filters: FilterOption[];
  busy: boolean;
  onToggle: (dimension: string, value: string) => void;
  onClear: (dimension: string) => void;
  onClearAll: () => void;
}) {
  const active = filters.filter((f) => f.selected.length).length;
  return (
    <div className="filters">
      {filters.map((option) => (
        <FilterBox
          key={option.dimension}
          option={option}
          busy={busy}
          onToggle={onToggle}
          onClear={onClear}
        />
      ))}
      {active > 0 && (
        <button className="link clear-all" disabled={busy} onClick={onClearAll}>
          Снять все фильтры
        </button>
      )}
    </div>
  );
}
