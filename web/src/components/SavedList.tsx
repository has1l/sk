import { useEffect, useState } from "react";

import * as api from "../api";
import { dateTime } from "../format";
import type { SavedDashboard, SavedVersion } from "../types";

/** Список сохранённых дашбордов: поиск по названию и по тексту запроса,
 *  сортировка, открытие, копия, переименование, удаление и история версий. */
export function SavedList({
  open,
  busy,
  onOpen,
  onClose,
}: {
  open: boolean;
  busy: boolean;
  onOpen: (id: string, version?: number) => void;
  onClose: () => void;
}) {
  const [items, setItems] = useState<SavedDashboard[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("updated");
  const [versions, setVersions] = useState<Record<string, SavedVersion[]>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api.listDashboards(query, sort).then(setItems).catch((e) => setError(String(e)));
  }, [open, query, sort]);

  if (!open) return null;

  const reload = () => api.listDashboards(query, sort).then(setItems);

  const showVersions = async (id: string) => {
    if (versions[id]) {
      setVersions(({ [id]: _drop, ...rest }) => rest);
      return;
    }
    const list = await api.listVersions(id);
    setVersions((prev) => ({ ...prev, [id]: list }));
  };

  return (
    <div className="saved">
      <div className="saved-head">
        <h3>Мои дашборды</h3>
        <button className="link" onClick={onClose}>
          Закрыть
        </button>
      </div>

      <div className="saved-tools">
        <input
          value={query}
          placeholder="Поиск по названию или запросу…"
          onChange={(event) => setQuery(event.target.value)}
        />
        <select value={sort} onChange={(event) => setSort(event.target.value)}>
          <option value="updated">По изменению</option>
          <option value="created">По созданию</option>
          <option value="title">По названию</option>
        </select>
      </div>

      {error && <p className="note">{error}</p>}
      {!items.length && <p className="note">Пока ничего не сохранено.</p>}

      <ul className="saved-list">
        {items.map((item) => (
          <li key={item.id}>
            <div className="saved-row">
              <button className="saved-title" disabled={busy} onClick={() => onOpen(item.id)}>
                {item.title}
                {item.version > 1 && <span className="badge">v{item.version}</span>}
              </button>
              <div className="saved-row-actions">
                <button
                  className="link"
                  disabled={busy}
                  onClick={() => api.copyDashboard(item.id).then(reload)}
                >
                  Копия
                </button>
                <button className="link" disabled={busy} onClick={() => showVersions(item.id)}>
                  Версии
                </button>
                <button
                  className="link"
                  disabled={busy}
                  onClick={() => {
                    const title = window.prompt("Новое название", item.title);
                    if (title?.trim()) api.renameDashboard(item.id, title.trim()).then(setItems);
                  }}
                >
                  Переименовать
                </button>
                {confirming === item.id ? (
                  <>
                    <button
                      className="link danger"
                      disabled={busy}
                      onClick={() => {
                        api.deleteDashboard(item.id).then(setItems);
                        setConfirming(null);
                      }}
                    >
                      Удалить навсегда
                    </button>
                    <button className="link" onClick={() => setConfirming(null)}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <button className="link danger" disabled={busy} onClick={() => setConfirming(item.id)}>
                    Удалить
                  </button>
                )}
              </div>
            </div>
            <p className="saved-meta">
              {item.question} · изменён {dateTime(item.updated_at)}
            </p>
            {versions[item.id] && (
              <ul className="versions">
                {versions[item.id].length === 0 && <li className="note">Версий пока нет.</li>}
                {versions[item.id].map((version) => (
                  <li key={version.version}>
                    <button
                      className="link"
                      disabled={busy}
                      onClick={() => onOpen(item.id, version.version)}
                    >
                      Версия {version.version} · {dateTime(version.created_at)}
                    </button>
                    <span className="saved-meta">{version.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
