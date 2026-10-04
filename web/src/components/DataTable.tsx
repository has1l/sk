import { useState } from "react";

import { cellValue } from "../format";
import type { Table } from "../types";

const PREVIEW = 12;

/**
 * Таблица — не только удобство. В светлой теме три слота палитры не дотягивают
 * до контраста 3:1, и правило требует страховочного канала: читаемые значения
 * текстом. Эта таблица и есть страховка, поэтому убрать её нельзя.
 */
export function DataTable({ table, csvUrl }: { table: Table; csvUrl?: string }) {
  const [expanded, setExpanded] = useState(false);
  const rows = expanded ? table.rows : table.rows.slice(0, PREVIEW);
  const hidden = table.row_count - rows.length;

  return (
    <div className="table-block">
      <div className="table-head">
        <span>Единая таблица · {table.row_count} строк</span>
        {csvUrl && (
          <a className="link" href={csvUrl} download>
            Скачать CSV
          </a>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th
                  key={column.field}
                  className={column.kind === "dimension" ? undefined : "num"}
                  title={column.kind === "calc" ? "Вычисленная колонка" : undefined}
                >
                  {column.label}
                  {column.kind === "calc" && <span className="calc-mark">ƒ</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {table.columns.map((column) => (
                  <td key={column.field} className={column.kind === "dimension" ? undefined : "num"}>
                    {cellValue(row[column.field], column.unit, column.field)}
                  </td>
                ))}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={table.columns.length}>Под текущие фильтры не попало ни одной строки.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <button className="link" onClick={() => setExpanded(true)}>
          Показать ещё {hidden}
        </button>
      )}
      {expanded && table.row_count > PREVIEW && (
        <button className="link" onClick={() => setExpanded(false)}>
          Свернуть
        </button>
      )}
    </div>
  );
}
