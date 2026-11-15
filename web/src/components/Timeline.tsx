import type { TimelineEntry } from "../types";

/** Машина времени: каждая правка оставила состояние, к которому можно
 *  вернуться одним щелчком. Кейс требует, чтобы пользователь понимал, что
 *  добавлено и что можно отменить — список шагов это говорит, а лента
 *  позволяет ещё и вернуться не на шаг, а в любую точку. */
export function Timeline({
  entries,
  busy,
  onRewind,
}: {
  entries: TimelineEntry[];
  busy: boolean;
  onRewind: (id: string) => void;
}) {
  if (entries.length < 2) return null;

  return (
    <section className="timeline">
      <h3>Машина времени</h3>
      <ol>
        {entries.map((entry) => (
          <li key={entry.id} className={entry.current ? "now" : ""}>
            <span className="tick" aria-hidden />
            <div className="entry">
              <span className="entry-label">{entry.label}</span>
              <span className="entry-summary">{entry.summary}</span>
            </div>
            {!entry.current && (
              <button className="link" disabled={busy} onClick={() => onRewind(entry.id)}>
                вернуться
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
