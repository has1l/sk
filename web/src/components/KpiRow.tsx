import { kpiValue } from "../format";
import type { Kpi } from "../types";

/** Итоговые цифры сверху. Крупно, с цветовой индикацией, обновляются вместе
 *  с фильтрами — всё как требует кейс. Цвет берётся только из статуса. */
export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  if (!kpis.length) return null;
  return (
    <div className="kpis">
      {kpis.map((card) => (
        <div className={`kpi ${card.status}`} key={card.key}>
          <div className="kpi-label">{card.label}</div>
          <div className="kpi-value">{kpiValue(card.value, card.unit, card.kind)}</div>
          <div className="kpi-hint">{card.hint ?? ""}</div>
        </div>
      ))}
    </div>
  );
}
