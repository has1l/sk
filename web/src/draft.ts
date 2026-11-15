/** Автосохранение черновика.
 *
 *  Сессия анализа живёт в памяти сервера и не переживает ни перезагрузку
 *  страницы, ни перезапуск uvicorn. Браузер хранит рецепт — заказ выборки,
 *  вид и стек вычислений, — поэтому восстановить можно и то, что не успели
 *  сохранить в базу. Данных в черновике нет: таблица собирается заново.
 */
import type { Draft, SessionView } from "./types";

const KEY = "puzzle.draft";
const LIFETIME = 7 * 24 * 60 * 60 * 1000;

export function remember(session: SessionView) {
  // Сохранённый дашборд уже лежит в базе — дублировать его черновиком незачем.
  if (session.saved_id && !session.dirty) return forget();
  const draft: Draft = {
    title: session.title,
    question: session.question,
    recipe: session.recipe,
    at: Date.now(),
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(draft));
  } catch {
    // Приватный режим или переполненное хранилище — черновик не главная функция.
  }
}

export function recall(): Draft | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (!draft.recipe || Date.now() - draft.at > LIFETIME) return null;
    return draft;
  } catch {
    return null;
  }
}

export function forget() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // см. выше
  }
}
