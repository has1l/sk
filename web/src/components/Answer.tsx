import { dateTime } from "../format";
import { type Mood, PetAvatar } from "./Pet";
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
  // Пока бот работает, показываются шаги разбора, а не спиннер: спиннер не
  // отличает работу от зависания и ничего не говорит о том, что происходит.
  // Пасхалка: сервера за ней нет, поэтому и данных она не утверждает.
  if (turn.pet) {
    return (
      <div className="bubble bot">
        <PetAvatar mood={turn.pet as Mood} />
        <div className="said">
          <p className="message">{turn.petSay}</p>
        </div>
      </div>
    );
  }

  if (turn.state === "pending") {
    const stages = turn.stages ?? [];
    return (
      <div className="bubble bot">
        <PetAvatar mood="think" />
        <div className="said">
        {stages.length === 0 ? (
          <span className="thinking">Смотрю данные</span>
        ) : (
          <ol className="stages">
            {stages.map((stage, index) => (
              <li key={`${stage.text}-${index}`} className={index === stages.length - 1 ? "live" : ""}>
                <span className="stage-text">{stage.text}</span>
                <span className="stage-detail">{stage.detail}</span>
              </li>
            ))}
          </ol>
        )}
        </div>
      </div>
    );
  }
  if (turn.state === "error") {
    return (
      <div className="bubble bot error">
        <PetAvatar mood="sorry" />
        <div className="said">
          <strong>Не получилось.</strong> {turn.error}
        </div>
      </div>
    );
  }

  const answer = turn.answer!;
  const action = ACTIONS[answer.action ?? ""];

  return (
    <div className="bubble bot">
      <PetAvatar mood={moodOf(answer.action, Boolean(answer.clarification?.reason))} />
      <div className="said">
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
    </div>
  );
}

/** Настроение по тому, чем кончился ответ. Отказ и уточнение — не радость,
 *  и притворяться довольным здесь нечестно. */
function moodOf(action: string | null | undefined, asking: boolean): Mood {
  if (action === "refused" || action === "delete") return "sorry";
  if (asking) return "think";
  return "glad";
}

const ACTIONS: Record<string, string> = {
  calculate: "Таблица и графики пересобраны с новой колонкой.",
  undo: "Состояние откатилось на шаг назад.",
  filter: "Фильтр применён ко всем графикам.",
  toggle: "Дашборд перестроен.",
  chart: "График обновлён.",
  table: "Смотрите таблицу под графиками.",
  why: "Разбор виден на мосту «из чего сложился разрыв».",
  refused: "Ничего не выполнено: под этой ролью запись невозможна.",
  rewind: "Состояние вернулось к выбранной точке.",
  draft: "Черновик восстановлен из браузера.",
  save: "Дашборд в списке сохранённых.",
  open: "Дашборд восстановлен в том же виде.",
  copy: "Работаем в копии — оригинал не тронут.",
  delete: "Удалено безвозвратно.",
};
