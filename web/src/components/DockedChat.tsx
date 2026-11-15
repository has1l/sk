import { useEffect, useRef, useState } from "react";

import { Answer } from "./Answer";
import { Composer } from "./Composer";
import { ShowOffer } from "./ShowOffer";
import type { ChatTurn } from "../types";

/** Чат, пристыкованный к слою дашборда.
 *
 *  Слой закрывает переписку целиком, и без этого диалог с дашбордом
 *  превращается в беготню туда-обратно. Свёрнут — только строка ввода и
 *  последняя реплика бота; развёрнут — переписка над ней; дальше — полный чат.
 *
 *  Главное ради чего всё: спросил «а почему Уральский просел» — и дашборд
 *  перестраивается прямо за спиной у этой панели, не закрываясь.
 */
export function DockedChat({
  turns,
  busy,
  onSend,
  onFull,
  offerFor,
  onShow,
}: {
  turns: ChatTurn[];
  busy: boolean;
  onSend: (question: string) => void;
  onFull: () => void;
  offerFor: string | null;
  onShow: () => void;
}) {
  const [open, setOpen] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const last = turns[turns.length - 1];
  const stage = last?.state === "pending" ? last.stages?.[last.stages.length - 1] : null;
  const said = last?.state === "done" ? last.answer?.message : null;

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, open]);

  /** Пока переписка раскрыта, Escape принадлежит ей: сворачивает панель, а не
   *  закрывает весь дашборд. Признак на body, а не порядок обработчиков —
   *  слой слушает ту же клавишу на том же окне, и порядок зависит от того,
   *  куда пришло событие. */
  useEffect(() => {
    if (!open) return;
    document.body.dataset.chatOpen = "1";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      delete document.body.dataset.chatOpen;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={`dock ${open ? "open" : ""}`}>
      <div className="dock-bar">
        <button
          className="dock-toggle"
          onClick={() => setOpen((v) => !v)}
          title={open ? "Свернуть переписку" : "Показать переписку"}
          aria-expanded={open}
        >
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
            <path
              d={open ? "m4 10 4-4 4 4" : "m4 6 4 4 4-4"}
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Чат</span>
          {turns.length > 0 && <span className="dock-count">{turns.length}</span>}
        </button>

        {/* Свёрнутая строка говорит, чем кончился последний вопрос: иначе
            непонятно, отработал бот или нет, и приходится раскрывать. */}
        {!open && (stage || said) && (
          <button className="dock-echo" onClick={() => setOpen(true)} title="Показать переписку">
            {stage ? <span className="thinking">{stage.text}</span> : said}
          </button>
        )}

        <button className="dock-full" onClick={onFull} title="Открыть чат на весь экран">
          Весь экран
        </button>
      </div>

      {open && (
        <div className="dock-log">
          {turns.length === 0 && (
            <p className="dock-empty">
              Спросите отсюда — дашборд перестроится за этой панелью, не закрываясь.
            </p>
          )}
          {turns.map((turn) => (
            <div className="turn" key={turn.id}>
              {turn.question && <div className="bubble user">{turn.question}</div>}
              <Answer turn={turn} onOpen={() => undefined} />
              {offerFor === turn.id && <ShowOffer onShow={onShow} />}
            </div>
          ))}
          <div ref={bottom} />
        </div>
      )}

      <Composer busy={busy} hasSession onSend={onSend} />
    </div>
  );
}
