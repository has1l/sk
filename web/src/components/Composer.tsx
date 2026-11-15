import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import * as api from "../api";
import type { QueryTemplate } from "../types";

const FALLBACK: QueryTemplate[] = [
  { group: "Дашборды", question: "Собери дашборд по продажам: план-факт по регионам за последний год" },
  { group: "Вычисления", question: "Добавь колонку с процентом выполнения плана" },
  { group: "Интерактив", question: "Покажи только Центральный регион" },
];

const MAX_HEIGHT = 180;

export function Composer({
  busy,
  hasSession,
  onSend,
}: {
  busy: boolean;
  hasSession: boolean;
  onSend: (question: string) => void;
}) {
  const [value, setValue] = useState("");
  const [templates, setTemplates] = useState<QueryTemplate[]>(FALLBACK);
  const [group, setGroup] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.listTemplates().then(setTemplates).catch(() => undefined);
  }, []);

  /** Поле растёт под текст: сначала сбрасываем высоту, иначе scrollHeight
   *  запомнит прежний размер и поле никогда не сожмётся обратно. */
  useLayoutEffect(() => {
    const node = field.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const groups = useMemo(() => [...new Set(templates.map((t) => t.group))], [templates]);
  const active = group ?? (hasSession ? groups[1] ?? groups[0] : groups[0]);
  const shown = useMemo(
    () => templates.filter((t) => t.group === active).slice(0, 4),
    [templates, active],
  );

  const send = (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    onSend(question);
    setValue("");
  };

  return (
    <div className="composer">
      {!hasSession && (
        <>
          <div className="template-groups">
            {groups.map((name) => (
              <button key={name} className={name === active ? "on" : ""} onClick={() => setGroup(name)}>
                {name}
              </button>
            ))}
          </div>
          <div className="examples">
            {shown.map((template, index) => (
              <button
                key={template.question}
                disabled={busy}
                style={{ animationDelay: `${120 + index * 45}ms` }}
                onClick={() => send(template.question)}
              >
                {template.question}
              </button>
            ))}
          </div>
        </>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          send(value);
        }}
      >
        <textarea
          ref={field}
          rows={1}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          /** Enter отправляет, Shift+Enter переносит строку — как в любом чате.
           *  Во время набора иероглифов Enter принадлежит IME, не нам. */
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send(value);
            }
          }}
          placeholder={hasSession ? "Уточните, посчитайте, спросите «почему»" : "Спросите про продажи на обычном русском"}
          disabled={busy}
          autoFocus
          aria-label="Вопрос"
        />
        <button className="send" type="submit" disabled={busy || !value.trim()} aria-label="Отправить">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M8 13V3m0 0L3.5 7.5M8 3l4.5 4.5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </form>
      {!hasSession && <p className="hint">Enter — отправить, Shift + Enter — новая строка</p>}
    </div>
  );
}
