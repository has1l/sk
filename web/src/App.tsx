import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "./api";
import { Answer } from "./components/Answer";
import { Composer } from "./components/Composer";
import { Dashboard } from "./components/Dashboard";
import { SavedList } from "./components/SavedList";
import type { AskResponse, ChatTurn, SessionView, ViewState } from "./types";

/** Сохранённый дашборд должен быть ссылкой: её можно переслать коллеге. */
function stampUrl(savedId: string | null | undefined) {
  const url = new URL(window.location.href);
  url.searchParams.delete("q");
  if (savedId) url.searchParams.set("dashboard", savedId);
  else url.searchParams.delete("dashboard");
  window.history.replaceState(null, "", url.toString());
}

export default function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [session, setSession] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  /** Открытие по ссылке: ?dashboard=<id> делится сохранённым дашбордом,
   *  ?q=<вопрос> открывает чат с готовым запросом. */
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("dashboard");
    const question = params.get("q");
    if (id) void openSaved(id);
    else if (question) void send(question);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const absorb = useCallback((answer: AskResponse, question: string | null) => {
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, question, state: "done", answer }]);
    if (answer.session) {
      setSession(answer.session);
      stampUrl(answer.session.saved_id);
    }
  }, []);

  const send = async (question: string) => {
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, question, state: "pending" }]);
    setBusy(true);
    try {
      const answer = await api.ask(question, session?.session_id ?? null);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "done", answer } : t)));
      if (answer.session) {
        setSession(answer.session);
        stampUrl(answer.session.saved_id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "error", error: message } : t)));
    } finally {
      setBusy(false);
    }
  };

  /** Фильтры и переключатели. Отдельный путь: ни модели, ни новой выборки —
   *  поэтому в переписке он следов не оставляет. */
  const changeView = async (view: ViewState) => {
    if (!session) return;
    setBusy(true);
    const optimistic = { ...session, view };
    setSession(optimistic);
    try {
      setSession(await api.setView(session.session_id, view));
    } catch {
      setSession(session);
    } finally {
      setBusy(false);
    }
  };

  const guard = async (run: () => Promise<AskResponse>, question: string | null) => {
    setBusy(true);
    try {
      absorb(await run(), question);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) => [
        ...prev,
        { id: crypto.randomUUID(), question, state: "error", error: message },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const openSaved = (id: string, version?: number) => {
    setShowSaved(false);
    return guard(
      () => (version ? api.openVersion(id, version) : api.openDashboard(id)),
      version ? `Открыть версию ${version}` : "Открыть дашборд",
    );
  };

  return (
    <div className={`app ${session ? "with-board" : ""}`}>
      <div className="chat">
        <header>
          <div>
            <h1>Аналитика в чате</h1>
            <p>Спросите про продажи на обычном русском — соберу дашборд.</p>
          </div>
          <button className="link" onClick={() => setShowSaved((v) => !v)}>
            Мои дашборды
          </button>
        </header>

        <SavedList
          open={showSaved}
          busy={busy}
          onOpen={openSaved}
          onClose={() => setShowSaved(false)}
        />

        <main>
          {turns.length === 0 && !showSaved && (
            <div className="empty">
              <p>
                Данные: продажи по 300 торговым точкам в 8 регионах, план и факт за 2023–2026 годы.
              </p>
              <p>
                Можно просить вычисления («добавь процент выполнения»), крутить фильтры и
                переключатели, сохранять дашборд и возвращаться к нему.
              </p>
            </div>
          )}
          {turns.map((turn) => (
            <div className="turn" key={turn.id}>
              {turn.question && <div className="bubble user">{turn.question}</div>}
              <Answer turn={turn} onOpen={(id) => openSaved(id)} />
            </div>
          ))}
          <div ref={bottom} />
        </main>

        <Composer busy={busy} hasSession={Boolean(session)} onSend={send} />
      </div>

      {session && (
        <div className="board-pane">
          <Dashboard
            session={session}
            busy={busy}
            onView={changeView}
            onDropStep={(stepId) =>
              guard(() => api.dropStep(session.session_id, stepId), "Убрать вычисление")
            }
            onUndo={() => guard(() => api.undo(session.session_id), "Отменить")}
            onSave={(title, asNew) =>
              guard(() => api.saveDashboard(session.session_id, title, asNew), "Сохранить дашборд")
            }
          />
        </div>
      )}
    </div>
  );
}
