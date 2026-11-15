import { kpiValue, plural } from "../format";
import type { SessionView } from "../types";

const MAX_SHOWN = 4;

/** Вход в дашборд прямо из переписки. Карточка одна и показывает текущее
 *  состояние сессии, а не снимок на момент реплики: дашборд живой, и четыре
 *  карточки с разными цифрами под разными репликами означали бы, что три из
 *  них врут. */
export function BoardCard({
  session,
  onOpen,
}: {
  session: SessionView;
  onOpen: () => void;
}) {
  const kpis = session.dashboard.kpis.slice(0, MAX_SHOWN);
  const panels = session.dashboard.panels.length;

  return (
    <div className="board-card">
      <div className="board-card-head">
        <div>
          <h3>{session.title}</h3>
          <p>
            {panels} {plural(panels, "панель", "панели", "панелей")} · {session.table.row_count}{" "}
            {plural(session.table.row_count, "строка", "строки", "строк")}
            {session.steps.length > 0 &&
              ` · ${session.steps.length} ${plural(session.steps.length, "вычисление", "вычисления", "вычислений")}`}
          </p>
        </div>
        <button className="board-card-open" onClick={onOpen}>
          Открыть дашборд
        </button>
      </div>
      {kpis.length > 0 && (
        <div className="mini-kpis">
          {kpis.map((card, index) => (
            <div
              className={`mini-kpi ${card.status}`}
              key={card.key}
              style={{ animationDelay: `${90 + index * 55}ms` }}
            >
              <div className="k">{card.label}</div>
              <div className="v">{kpiValue(card.value, card.unit, card.kind)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
