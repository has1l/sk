import type { Anomaly } from "../types";

/** То, о чём не спрашивали. Самое ценное на дашборде: общий рост прячет
 *  локальный провал, и увидеть его глазами в таблице из трёхсот строк нельзя. */
export function Anomalies({ items }: { items: Anomaly[] }) {
  if (items.length === 0) return null;
  return (
    <section className="anomalies">
      <h3>На что обратить внимание</h3>
      <ul>
        {items.map((item) => (
          <li key={`${item.label}-${item.text}`} className={item.severity}>
            {item.text}
          </li>
        ))}
      </ul>
      <p className="note">
        Найдено без запроса — по отклонению от медианы группы и по движению против общего тренда.
      </p>
    </section>
  );
}
