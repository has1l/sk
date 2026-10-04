import { useState } from "react";

const EXAMPLES = [
  "Покажи план-факт продаж по регионам за последний квартал",
  "Динамика продаж по месяцам за последний год",
  "Структура продаж по категориям за последний месяц",
];

export function Composer({ busy, onSend }: { busy: boolean; onSend: (q: string) => void }) {
  const [value, setValue] = useState("");

  const send = (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    onSend(question);
    setValue("");
  };

  return (
    <div className="composer">
      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} disabled={busy} onClick={() => send(example)}>
            {example}
          </button>
        ))}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          send(value);
        }}
      >
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Спросите про продажи — например, «план-факт по регионам за квартал»"
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || !value.trim()}>
          Спросить
        </button>
      </form>
    </div>
  );
}
