import { useEffect, useRef, useState } from "react";

import { panelOptions } from "../api";
import type { PanelDraft, PanelOptions } from "../types";

/** Справочник не меняется между открытиями, поэтому запрос один на вкладку
 *  браузера. Хранится обещание, а не результат: два быстрых открытия подряд
 *  иначе ушли бы в сеть дважды. */
let catalogue: Promise<PanelOptions> | null = null;
const load = () => (catalogue ??= panelOptions());

const START: PanelDraft = { dimension: "region", metric: "fact_amount", chart: "bar" };

/** Своя панель: человек выбирает разрез, метрику и вид графика.
 *
 *  Выбор закрыт списками, которые прислал сервер. Поля ввода здесь нет
 *  намеренно: имя колонки, набранное руками, — это путь к запросу, собранному
 *  из текста, а он в проекте закрыт.
 */
export function AddPanel({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (draft: PanelDraft) => void;
}) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<PanelOptions | null>(null);
  const [draft, setDraft] = useState<PanelDraft>(START);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    void load().then((it) => alive && setOptions(it));

    // Escape закрывает выбор, а не весь дашборд. Признак на body — та же
    // развязка, что у переноса и пристыкованного чата.
    document.body.dataset.inner = "1";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onDown = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      alive = false;
      delete document.body.dataset.inner;
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const pick = (key: keyof PanelDraft) => (event: React.ChangeEvent<HTMLSelectElement>) =>
    setDraft((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <div className="add-panel" ref={box}>
      <button className="tab-add wide" disabled={busy} onClick={() => setOpen((v) => !v)}>
        <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">
          <path d="M6 2v8M2 6h8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        Панель
      </button>

      {open && (
        <div className="add-panel-body">
          <label>
            Разрез
            <select value={draft.dimension} onChange={pick("dimension")}>
              {options?.dimensions.map((it) => (
                <option key={it.value} value={it.value}>
                  {it.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Метрика
            <select value={draft.metric} onChange={pick("metric")}>
              {options?.metrics.map((it) => (
                <option key={it.value} value={it.value}>
                  {it.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            График
            <select value={draft.chart} onChange={pick("chart")}>
              {options?.charts.map((it) => (
                <option key={it.value} value={it.value}>
                  {it.label}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary"
            disabled={busy || !options}
            onClick={() => {
              onAdd(draft);
              setOpen(false);
            }}
          >
            Добавить
          </button>
          <p className="hint">
            Панель встанет в конец открытой вкладки. Её можно перенести, склеить
            с соседней и растянуть, как и остальные.
          </p>
        </div>
      )}
    </div>
  );
}
