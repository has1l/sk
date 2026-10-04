import { useState } from "react";

import type { ChatTurn } from "../types";
import { Chart } from "./Chart";
import { DataTable } from "./DataTable";

export function Answer({ turn }: { turn: ChatTurn }) {
  const [showSql, setShowSql] = useState(false);

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
  return (
    <div className="bubble bot">
      <p className="message">{answer.message}</p>

      {answer.notes.map((note) => (
        <p className="note" key={note}>
          {note}
        </p>
      ))}

      {answer.chart && answer.table && <Chart spec={answer.chart} table={answer.table} />}
      {answer.table && answer.table.row_count > 0 && <DataTable table={answer.table} />}

      {answer.sql && (
        <div className="sql">
          <button className="link" onClick={() => setShowSql((v) => !v)}>
            {showSql ? "Скрыть запрос" : "Показать запрос"}
          </button>
          {showSql && <pre>{answer.sql}</pre>}
        </div>
      )}
    </div>
  );
}
