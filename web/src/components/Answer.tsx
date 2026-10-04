import { dateTime } from "../format";
import type { ChatTurn } from "../types";

/** Реплика бота. Дашборд живёт в своей панели и обновляется целиком —
 *  в переписке остаётся то, что сказал бот, и чем это закончилось. */
export function Answer({
  turn,
  onOpen,
}: {
  turn: ChatTurn;
  onOpen: (id: string) => void;
}) {
  if (turn.state === "pending") {
    return (
      <div className="bubble bot">
        <span className="thinking">Смотрю данные</span>
      </div>
    );
  }
  if (turn.state === "error") {
    return (
      <div className="bubble bot error">
        <strong>Не получилось.</strong> {turn.error}
      </div>
    );
  }

  const answer = turn.answer!;
  const action = ACTIONS[answer.action ?? ""];

  return (
    <div className="bubble bot">
      <p className="message">{answer.message}</p>

      {answer.clarification?.reason && <p className="note">{answer.clarification.reason}</p>}
      {action && <p className="action">{action}</p>}

      {answer.saved && answer.saved.length > 0 && (
        <ul className="saved-inline">
          {answer.saved.map((item) => (
            <li key={item.id}>
              <button className="link" onClick={() => onOpen(item.id)}>
                {item.title}
              </button>
              <span className="saved-meta">{dateTime(item.updated_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const ACTIONS: Record<string, string> = {
  calculate: "Таблица и графики пересобраны с новой колонкой.",
  undo: "Состояние откатилось на шаг назад.",
  filter: "Фильтр применён ко всем графикам.",
  toggle: "Дашборд перестроен.",
  chart: "График обновлён.",
  table: "Смотрите таблицу под графиками.",
  save: "Дашборд в списке сохранённых.",
  open: "Дашборд восстановлен в том же виде.",
  copy: "Работаем в копии — оригинал не тронут.",
  delete: "Удалено безвозвратно.",
};
