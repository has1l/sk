import { useEffect, useRef, useState } from "react";

const CLOSE_MS = 200;

/** Дашборд поверх переписки. Чат остаётся по центру и не сжимается, дашборду
 *  достаётся вся ширина окна. Слой — модальный: пока он открыт, фон получает
 *  inert, иначе Tab уводит фокус под него и человек печатает вслепую. */
export function BoardLayer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const [closing, setClosing] = useState(false);
  const back = useRef<HTMLButtonElement>(null);
  const timer = useRef<number>();

  const leave = () => {
    if (closing) return;
    setClosing(true);
    timer.current = window.setTimeout(onClose, CLOSE_MS);
  };

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const shell = document.getElementById("shell");
    const scroll = document.body.style.overflow;

    shell?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    back.current?.focus();

    return () => {
      shell?.removeAttribute("inert");
      document.body.style.overflow = scroll;
      window.clearTimeout(timer.current);
      opener?.focus?.();
    };
  }, []);

  useEffect(() => {
    // Пока панель несут, Escape принадлежит переносу: он его отменяет. Закрыть
    // весь дашборд на полпути — не то, чего ждёшь от этой клавиши.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Клавишу могли забрать: перенос панели отменяется ею же, раскрытая
      // переписка ею же сворачивается. Закрывать весь дашборд в этот момент —
      // не то, чего ждёшь. Признаки на body, а не порядок обработчиков: все
      // трое слушают одно окно, и порядок зависит от того, куда пришло
      // событие.
      if (
        document.body.dataset.dragging ||
        document.body.dataset.chatOpen ||
        document.body.dataset.showing ||
        // Переименование вкладки и выбор своей панели — тоже «самое
        // внутреннее»: Escape им принадлежит раньше, чем слою.
        document.body.dataset.inner
      )
        return;
      leave();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <>
      <div className="scrim" onClick={leave} />
      <div
        className={`layer ${closing ? "closing" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="layer-bar">
          <button ref={back} className="layer-back" onClick={leave}>
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="13" height="13">
              <path
                d="M10 13 5 8l5-5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Назад к чату
          </button>
          <span className="layer-esc">
            <kbd>Esc</kbd> — свернуть
          </span>
        </div>
        <div className="layer-body">{children}</div>
      </div>
    </>
  );
}
