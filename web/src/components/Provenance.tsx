import { useState } from "react";

import { count } from "../format";
import type { Provenance as Origin } from "../types";

/** Как получена каждая цифра на экране.
 *
 *  Нужна не для отладки. Кейс первым пунктом требует не дать генерируемому
 *  коду сделать лишнее — а выполненное требование, которого не видно, на
 *  защите неотличимо от невыполненного. */
export function Provenance({ origin }: { origin: Origin | null }) {
  const [open, setOpen] = useState(false);
  if (!origin) return null;

  return (
    <section className="provenance">
      <button className="link" onClick={() => setOpen((v) => !v)}>
        {open ? "Скрыть" : "Как это посчитано"}
      </button>

      {open && (
        <div className="provenance-body">
          <div className="facts">
            <Fact label="Роль в базе" value={origin.role} />
            <Fact label="Транзакция" value={origin.read_only ? "только чтение" : "запись"} />
            <Fact label="Таймаут запроса" value={origin.statement_timeout} />
            <Fact label="Строк выгружено" value={count(origin.row_count)} />
            <Fact label="Время выгрузки" value={`${origin.load_ms} мс`} />
            <Fact label="Модель" value={origin.model} />
            <Fact
              label="Обращений к модели"
              value={
                origin.llm_calls === 0
                  ? "0 — собрано без модели"
                  : `${origin.llm_calls} — по одному на реплику`
              }
            />
          </div>

          <ul className="guarantees">
            {origin.guarantees.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>

          {origin.formulas.length > 0 && (
            <>
              <h4>Формулы</h4>
              <table className="formulas">
                <tbody>
                  {origin.formulas.map((formula) => (
                    <tr key={formula.field}>
                      <td>{formula.title}</td>
                      <td className="expr">{formula.expression}</td>
                      <td className="origin">{formula.kind}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {origin.sql && (
            <>
              <h4>Запрос к базе</h4>
              <pre>{origin.sql}</pre>
              <p className="note">
                Собран кодом из закрытого списка полей. Значения из реплики ушли параметрами —
                в текст запроса они не попадают никогда.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <span className="fact-label">{label}</span>
      <span className="fact-value">{value}</span>
    </div>
  );
}
