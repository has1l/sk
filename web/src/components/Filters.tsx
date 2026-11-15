import { useEffect, useMemo, useRef, useState } from "react";

import type { FilterOption } from "../types";

const VISIBLE = 80;

/** Фильтр с поиском и мультивыбором. Триста точек в списке — поиск обязателен,
 *  и он идёт по уже загруженным значениям, без запроса на сервер. */
function FilterBox({
  option,
  busy,
  open,
  onOpen,
  onToggle,
  onClear,
}: {
  option: FilterOption;
  busy: boolean;
  open: boolean;
  onOpen: (dimension: string | null) => void;
  onToggle: (dimension: string, value: string) => void;
  onClear: (dimension: string) => void;
}) {
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
    <div className={`filter ${open ? "open" : ""}`} data-filter={option.dimension}>
      <button className="filter-head" disabled={busy} onClick={() => onOpen(open ? null : option.dimension)}>
        <span className="filter-label">{option.label}</span>
        <span className="filter-state">
          {chosen ? `${chosen} из ${option.values.length}` : `все · ${option.values.length}`}
        </span>
      </button>

      {open && (
        <div className="filter-body">
          <input
            className="filter-search"
            value={query}
            placeholder="Поиск"
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
  // Открыт один список за раз. Каждый фильтр помнил своё «открыто», и два
  // соседних списка ложились друг на друга.
  const [opened, setOpened] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!opened) return;
    // Щелчок мимо закрывает список. Escape тоже, но слой дашборда слушает ту
    // же клавишу — признак data-inner говорит ему, что клавиша наша.
    document.body.dataset.inner = "1";
    const away = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpened(null);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpened(null);
    };
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", key);
    return () => {
      delete document.body.dataset.inner;
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", key);
    };
  }, [opened]);

  return (
    <div className="filters" ref={root}>
      {filters.map((option) => (
        <FilterBox
          key={option.dimension}
          option={option}
          busy={busy}
          open={opened === option.dimension}
          onOpen={setOpened}
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
