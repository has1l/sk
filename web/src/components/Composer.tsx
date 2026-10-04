import { useEffect, useMemo, useState } from "react";

import * as api from "../api";
import type { QueryTemplate } from "../types";

const FALLBACK: QueryTemplate[] = [
  { group: "Дашборды", question: "Собери дашборд по продажам: план-факт по регионам за последний год" },
  { group: "Вычисления", question: "Добавь колонку с процентом выполнения плана" },
  { group: "Интерактив", question: "Покажи только Центральный регион" },
];

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

  useEffect(() => {
    api.listTemplates().then(setTemplates).catch(() => undefined);
  }, []);

  const groups = useMemo(() => [...new Set(templates.map((t) => t.group))], [templates]);
  const shown = useMemo(() => {
    const picked = group ?? (hasSession ? groups[1] ?? groups[0] : groups[0]);
    return templates.filter((t) => t.group === picked).slice(0, 6);
  }, [templates, group, groups, hasSession]);

  const send = (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    onSend(question);
    setValue("");
  };

  return (
    <div className="composer">
      <div className="template-groups">
        {groups.map((name) => (
          <button
            key={name}
            className={name === (group ?? (hasSession ? groups[1] ?? groups[0] : groups[0])) ? "on" : ""}
            onClick={() => setGroup(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="examples">
        {shown.map((template) => (
          <button key={template.question} disabled={busy} onClick={() => send(template.question)}>
            {template.question}
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
          placeholder="Спросите про продажи или попросите вычисление"
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
