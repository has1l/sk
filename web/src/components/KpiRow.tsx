import { useEffect, useRef, useState } from "react";

import { kpiValue } from "../format";
import type { Kpi } from "../types";

/** Сколько цифра перетекает к новому значению. Дольше — фильтр ощущается
 *  тормозом, короче — смена снова выглядит как подмена. */
const TWEEN_MS = 520;

const calm = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Значение, которое плавно догоняет новое. Пересчёт по фильтру — главное
 *  действие дашборда, и перетекающая цифра показывает, что пересчиталось и
 *  куда сдвинулось, а не просто мигнуло. Первое появление не анимируется:
 *  счёт от нуля на каждом открытии был бы фокусом, а не информацией. */
function useTween(target: number | null): number | null {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  const frame = useRef(0);

  useEffect(() => {
    const start = from.current;
    cancelAnimationFrame(frame.current);
    if (target === null || start === null || start === target || calm()) {
      from.current = target;
      setShown(target);
      return;
    }
    const began = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - began) / TWEEN_MS, 1);
      const eased = 1 - (1 - t) ** 3;
      const value = start + (target - start) * eased;
      from.current = value;
      setShown(value);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [target]);

  return shown;
}

function KpiCard({ card, order }: { card: Kpi; order: number }) {
  const value = useTween(card.value);
  return (
    <div className={`kpi ${card.status}`} style={{ ["--i" as string]: order }}>
      <div className="kpi-label">{card.label}</div>
      <div className="kpi-value">{kpiValue(value, card.unit, card.kind)}</div>
      <div className="kpi-hint">{card.hint ?? ""}</div>
    </div>
  );
}

/** Итоговые цифры сверху. Крупно, с цветовой индикацией, обновляются вместе
 *  с фильтрами — всё как требует кейс. Цвет берётся только из статуса. */
export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  if (!kpis.length) return null;
  return (
    <div className="kpis">
      {kpis.map((card, order) => (
        <KpiCard card={card} order={order} key={card.key} />
      ))}
    </div>
  );
}
