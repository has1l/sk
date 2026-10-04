import { useState } from "react";

import { exportCsvUrl, exportHtmlUrl } from "../api";
import type { SessionView, ViewState } from "../types";
import { Chart } from "./Chart";
import { DataTable } from "./DataTable";
import { Filters } from "./Filters";
import { KpiRow } from "./KpiRow";
import { StepStack } from "./StepStack";
import { Toggles } from "./Toggles";

type ZoomRange = [string, string] | null;

/** Живой дашборд: KPI, фильтры, переключатели, четыре связанных графика и
 *  единая таблица. Фильтр применяется ко всем графикам сразу, потому что все
 *  они — разные группировки одной таблицы сессии. */
export function Dashboard({
  session,
  busy,
  onView,
  onDropStep,
  onUndo,
  onSave,
}: {
  session: SessionView;
  busy: boolean;
  onView: (view: ViewState) => void;
  onDropStep: (id: string) => void;
  onUndo: () => void;
  onSave: (title: string | null, asNew: boolean) => void;
}) {
  const [zooms, setZooms] = useState<Record<string, ZoomRange>>({});
  const [showSql, setShowSql] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(session.title);

  const { dashboard, view } = session;

  const patch = (next: Partial<ViewState>) => onView({ ...view, ...next });

  const toggle = (key: string, value: string) => {
    if (key === "primary") {
      const temporal = view.table_dimensions.filter((d) =>
        ["month", "quarter", "year"].includes(d),
      );
      patch({ primary: value, table_dimensions: [...temporal, value] });
      return;
    }
    if (key === "period_grain") {
      const entities = view.table_dimensions.filter(
        (d) => !["month", "quarter", "year"].includes(d),
      );
      const hadPeriod = view.table_dimensions.length !== entities.length;
      patch({
        period_grain: value as ViewState["period_grain"],
        table_dimensions: hadPeriod ? [value, ...entities] : view.table_dimensions,
      });
      return;
    }
    patch({ [key]: value } as Partial<ViewState>);
  };

  const flip = (dimension: string, value: string) => {
    const current = view.filters.find((f) => f.dimension === dimension);
    const values = current ? [...current.values] : [];
    const at = values.indexOf(value);
    if (at >= 0) values.splice(at, 1);
    else values.push(value);
    const rest = view.filters.filter((f) => f.dimension !== dimension);
    patch({ filters: values.length ? [...rest, { dimension, values }] : rest });
  };

  const clear = (dimension: string) =>
    patch({ filters: view.filters.filter((f) => f.dimension !== dimension) });

  const onZoom = (group: string, range: ZoomRange) =>
    setZooms((prev) => ({ ...prev, [group]: range }));

  return (
    <div className="board">
      <div className="board-head">
        <div>
          {renaming ? (
            <form
              className="rename"
              onSubmit={(event) => {
                event.preventDefault();
                onSave(draftTitle.trim() || session.title, false);
                setRenaming(false);
              }}
            >
              <input value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} autoFocus />
              <button type="submit">Сохранить</button>
            </form>
          ) : (
            <h2 onDoubleClick={() => setRenaming(true)} title="Двойной щелчок — переименовать">
              {session.title}
              {session.dirty && <span className="dot" title="Есть несохранённые изменения" />}
            </h2>
          )}
          <p className="board-question">{session.question}</p>
        </div>
        <div className="board-actions">
          <button disabled={busy} onClick={() => onSave(null, false)}>
            {session.saved_id ? "Сохранить" : "Сохранить дашборд"}
          </button>
          {session.saved_id && (
            <button disabled={busy} onClick={() => onSave(`${session.title} — копия`, true)}>
              Копия
            </button>
          )}
          <a className="ghost" href={exportHtmlUrl(session.session_id)} download>
            HTML
          </a>
        </div>
      </div>

      <KpiRow kpis={dashboard.kpis} />

      <div className="controls">
        <Toggles toggles={dashboard.toggles} busy={busy} onChange={toggle} />
        <Filters
          filters={dashboard.filters}
          busy={busy}
          onToggle={flip}
          onClear={clear}
          onClearAll={() => patch({ filters: [] })}
        />
      </div>

      {session.insights.length > 0 && (
        <ul className="insights">
          {session.insights.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      {session.notes.map((note) => (
        <p className="note" key={note}>
          {note}
        </p>
      ))}

      <div className="panels">
        {dashboard.panels.map((panel) => (
          <section className={`panel ${panel.spec.kind}`} key={panel.id}>
            <Chart
              panel={panel}
              zoom={panel.spec.zoom_group ? zooms[panel.spec.zoom_group] : undefined}
              onZoom={onZoom}
            />
            {panel.note && <p className="note">{panel.note}</p>}
          </section>
        ))}
      </div>

      <StepStack
        steps={session.steps}
        busy={busy}
        onDrop={onDropStep}
        onUndo={onUndo}
      />

      <DataTable table={session.table} csvUrl={exportCsvUrl(session.session_id)} />

      {session.sql && (
        <div className="sql">
          <button className="link" onClick={() => setShowSql((v) => !v)}>
            {showSql ? "Скрыть запрос" : "Показать запрос к базе"}
          </button>
          {showSql && <pre>{session.sql}</pre>}
        </div>
      )}
    </div>
  );
}
