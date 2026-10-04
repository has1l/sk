import { useState } from "react";

import { cellValue } from "../format";
import type { Table } from "../types";

const PREVIEW = 12;

/**
 * Таблица — не только удобство. В светлой теме три слота палитры не дотягивают
 * до контраста 3:1, и правило требует страховочного канала: читаемые значения
 * текстом. Эта таблица и есть страховка, поэтому убрать её нельзя.
 */
export function DataTable({ table }: { table: Table }) {
  const [expanded, setExpanded] = useState(false);
  const rows = expanded ? table.rows : table.rows.slice(0, PREVIEW);
  const hidden = table.row_count - rows.length;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column.field} className={column.kind === "metric" ? "num" : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((column) => (
                <td key={column.field} className={column.kind === "metric" ? "num" : undefined}>
                  {cellValue(row[column.field], column.unit, column.field)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
