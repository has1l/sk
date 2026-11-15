import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "./api";
import { type Move, edits, tour } from "./agent";
import { plural } from "./format";
import { AgentCursor } from "./components/AgentCursor";
import { Answer } from "./components/Answer";
import { BoardCard } from "./components/BoardCard";
import { BoardLayer } from "./components/BoardLayer";
import { Composer } from "./components/Composer";
import { Dashboard } from "./components/Dashboard";
import { DockedChat } from "./components/DockedChat";
import { PET_NAME } from "./components/Pet";
import { SavedList } from "./components/SavedList";
import { ShowOffer } from "./components/ShowOffer";
import { ThemeToggle } from "./components/ThemeToggle";
import { Timeline } from "./components/Timeline";
import * as draft from "./draft";
import type { AskResponse, ChatTurn, Draft, Layout, SessionView, Stage, ViewState } from "./types";

/** Сохранённый дашборд должен быть ссылкой: её можно переслать коллеге. */
function stampUrl(savedId: string | null | undefined) {
  const url = new URL(window.location.href);
  url.searchParams.delete("q");
  if (savedId) url.searchParams.set("dashboard", savedId);
  else url.searchParams.delete("dashboard");
  window.history.replaceState(null, "", url.toString());
}

/** Пасхалка. Срабатывает только на точное совпадение: перехватывать что-то
 *  похожее нельзя — чужой вопрос молча не дойдёт до бота, и человек решит,
 *  что сломалось. В модель такая реплика не уходит вовсе, значит и не стоит
 *  ничего. */
const SIX_SEVEN = /^\s*(6\s*7|67|six[\s-]*seven|сикс[\s-]*севен|шесть[\s-]*семь)\s*[!?.]*\s*$/i;

export default function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [session, setSession] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [pending, setPending] = useState<Draft | null>(null);
  const [boardOpen, setBoardOpen] = useState(false);
  /** Показ работы: курсор проходит по дашборду и называет, что откуда взялось.
   *  Выключен по умолчанию — он намеренно медленный. */
  const [showing, setShowing] = useState(() => {
    try {
      return localStorage.getItem("puzzle.showing") === "1";
    } catch {
      return false;
    }
  });
  const [moves, setMoves] = useState<Move[] | null>(null);
  /** Предложение показать разбор на дашборде. Сам он больше не запускается:
   *  человек сначала читает ответ в чате и только потом идёт смотреть. */
  const [offer, setOffer] = useState<{ turn: string; wasId: string | null; wasView: ViewState | null } | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  /** Название в шапке ведёт на главную — стартовый экран с шаблонами. Без
   *  перезагрузки: страница уже здесь. Текущая работа не теряется — она в
   *  черновике, и стартовый экран предложит её продолжить. */
  function goHome() {
    if (session) draft.remember(session);
    setTurns([]);
    setSession(null);
    setBoardOpen(false);
    setShowSaved(false);
    setMoves(null);
    setOffer(null);
    stampUrl(null);
    setPending(draft.recall());
  }

  /** Черновик пишется на каждое изменение сессии: падение вкладки не должно
   *  стоить получаса работы. */
  useEffect(() => {
    if (session) draft.remember(session);
  }, [session]);

  /** Открытие по ссылке: ?dashboard=<id> делится сохранённым дашбордом,
   *  ?q=<вопрос> открывает чат с готовым запросом. Черновик предлагается
   *  только когда не просили ничего конкретного. */
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("dashboard");
    const question = params.get("q");
    if (id) void openSaved(id);
    else if (question) void send(question);
    else setPending(draft.recall());
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

    if (SIX_SEVEN.test(question)) {
      setTurns((prev) => [
        ...prev,
        { id, question, state: "done", pet: "sixseven", petSay: "Шесть… семь." },
      ]);
      return;
    }

    setPending(null);
    setOffer(null);
    setTurns((prev) => [...prev, { id, question, state: "pending", stages: [] }]);
    setBusy(true);

    const note = (stage: Stage) =>
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === id ? { ...turn, stages: [...(turn.stages ?? []), stage] } : turn,
        ),
      );

    const wasId = session?.session_id ?? null;
    const wasView = session?.view ?? null;

    try {
      const answer = await api.askStream(question, wasId, note);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "done", answer } : t)));
      if (answer.session) {
        setSession(answer.session);
        stampUrl(answer.session.saved_id);
        if (showing) setOffer({ turn: id, wasId, wasView });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, state: "error", error: message } : t)),
      );
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

  /** Перестановка панелей. Как и фильтры, идёт мимо модели: меняется только
   *  раскладка. Оптимистично — иначе коробка возвращалась бы на место на
   *  время запроса и перетаскивание дёргалось бы. */
  const changeLayout = async (next: Layout) => {
    if (!session) return;
    const before = session;
    setSession({ ...session, dashboard: { ...session.dashboard, layout: next } });
    try {
      setSession(await api.setLayout(session.session_id, next));
    } catch {
      setSession(before);
    }
  };

  /** Правка состава панелей: добавить свою, убрать ненужную.
   *
   *  Идёт тем же путём, что фильтры и перестановка, — мимо модели и мимо
   *  переписки. Реплика «добавил панель» в чате пересказывала бы то, что
   *  человек видит своими глазами, и отматывалась бы машиной времени как
   *  сказанное, хотя сказано ничего не было. Ошибку показываем: кнопка,
   *  которая молча ничего не сделала, хуже кнопки, которая объяснилась.
   */
  const changeBoard = async (run: () => Promise<SessionView>, what: string) => {
    setBusy(true);
    try {
      setSession(await run());
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) => [
        ...prev,
        { id: crypto.randomUUID(), question: what, state: "error", error: message },
      ]);
    } finally {
      setBusy(false);
    }
  };

  /** Разбор ответа курсором.
   *
   *  Правка готового дашборда показывается **по-настоящему**: вид отматывается
   *  к тому, что было, и собирается обратно шаг за шагом — каждый шаг идёт на
   *  сервер тем же путём, что и ручное переключение. Новый дашборд отматывать
   *  некуда, поэтому там курсор идёт обзором и объясняет, не трогая.
   */
  const showWork = async (
    fresh: SessionView,
    wasId: string | null,
    wasView: ViewState | null,
  ) => {
    setOffer(null);
    setBoardOpen(true);
    // Слой появляется с анимацией; дальше курсор сам ждёт свою цель в
    // разметке (до четырёх секунд), поэтому угадывать длительность здесь не
    // нужно — раньше именно это и подводило: дашборд не успевал, цели не
    // находились, и показ молча пропускал все шаги.
    await new Promise((r) => setTimeout(r, 200));

    const sameSession = wasId !== null && wasId === fresh.session_id;
    if (sameSession && wasView) {
      const plan = edits(wasView, fresh.view, fresh, (view) => void changeView(view));
      if (plan.length) {
        setSession(await api.setView(fresh.session_id, wasView));
        setMoves(plan);
        return;
      }
    }
    setMoves(tour(fresh));
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
    setPending(null);
    return guard(
      () => (version ? api.openVersion(id, version) : api.openDashboard(id)),
      version ? `Открыть версию ${version}` : "Открыть дашборд",
    );
  };

  const resume = (saved: Draft) => {
    setPending(null);
    return guard(() => api.restoreDraft(saved), "Продолжить черновик");
  };

  /** Пусто — пока нет ни одной реплики. Предложение вернуться к черновику
   *  разговором не считается: оно часть приветствия и центрируется вместе с
   *  ним. Список сохранённых — другое дело, он длинный и центру не рад. */
  const blank = turns.length === 0 && !showSaved;
  const answering = turns[turns.length - 1]?.state === "pending";

  return (
    <>
      <div id="shell" className={`app ${blank ? "blank" : ""}`}>
        <div className="topbar">
          <a
            className="wordmark"
            href="/"
            aria-label={`${PET_NAME} — на главную`}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
              event.preventDefault();
              goHome();
            }}
          >
            {/* Значок — тот же зверёк, что отвечает в чате: название продукта
                и лицо бота одно и то же существо. */}
            <span className="glyph" aria-hidden="true">
              <svg viewBox="10 16 36 24" width="16" height="11" shapeRendering="crispEdges" fill="currentColor">
                <rect x="16" y="18" width="24" height="15" />
                <rect x="12" y="24" width="4" height="5" />
                <rect x="40" y="24" width="4" height="5" />
                <rect x="17" y="33" width="3" height="5" />
                <rect x="23" y="33" width="3" height="5" />
                <rect x="30" y="33" width="3" height="5" />
                <rect x="36" y="33" width="3" height="5" />
                <rect x="21" y="23" width="3" height="4" fill="var(--accent-fill)" />
                <rect x="32" y="23" width="3" height="4" fill="var(--accent-fill)" />
              </svg>
            </span>
            <span className="wordmark-text">{PET_NAME}</span>
          </a>
          <div className="topbar-right">
            {session && (
              <button className="board-open" onClick={() => setBoardOpen(true)}>
                Дашборд
                <span className="count">
                  {session.dashboard.panels.length}{" "}
                  {plural(session.dashboard.panels.length, "панель", "панели", "панелей")}
                </span>
                <svg className="chev" viewBox="0 0 16 16" width="11" height="11" fill="none" aria-hidden="true">
                  <path d="m6 3 5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
            <button className="link" onClick={() => setShowSaved((v) => !v)}>
              Мои дашборды
            </button>
            <button
              className={`show-toggle${showing ? " on" : ""}`}
              onClick={() => {
                const next = !showing;
                setShowing(next);
                try {
                  localStorage.setItem("puzzle.showing", next ? "1" : "0");
                } catch {
                  /* приватный режим — режим живёт до перезагрузки */
                }
              }}
              title={
                showing
                  ? "Показ работы включён: курсор пройдёт по дашборду и объяснит"
                  : "Показать работу: курсор пройдёт по дашборду и объяснит, что откуда"
              }
            >
              <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
                <path d="M3 1.8 12.4 8l-4.3.9-2 4.6L3 1.8Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              </svg>
              Показ
            </button>
            <ThemeToggle />
          </div>
        </div>

        <div className="stream">
          {blank && (
            <div className="hero">
              <h1>Что посчитаем?</h1>
              <p>
                Спросите про продажи на обычном русском — соберу живой дашборд прямо здесь.
                Его можно дорабатывать словами, крутить фильтрами и сохранять.
              </p>
              <p className="facts">
                300 торговых точек · 8 регионов · план и факт за 2023–2026
              </p>
            </div>
          )}

          <SavedList
            open={showSaved}
            busy={busy}
            onOpen={openSaved}
            onClose={() => setShowSaved(false)}
          />

          {pending && (
            <div className="resume">
              <div>
                <strong>Остался черновик</strong>
                <p>{pending.title || pending.question}</p>
              </div>
              <div className="resume-actions">
                <button disabled={busy} onClick={() => resume(pending)}>
                  Продолжить
                </button>
                <button
                  className="link"
                  onClick={() => {
                    draft.forget();
                    setPending(null);
                  }}
                >
                  Начать заново
                </button>
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <div className="turn" key={turn.id}>
              {turn.question && <div className="bubble user">{turn.question}</div>}
              <Answer turn={turn} onOpen={(id) => openSaved(id)} />
              {offer?.turn === turn.id && session && (
                <ShowOffer onShow={() => void showWork(session, offer.wasId, offer.wasView)} />
              )}
            </div>
          ))}

          {session && !answering && (
            <BoardCard session={session} onOpen={() => setBoardOpen(true)} />
          )}

          {session && (
            <Timeline
              entries={session.timeline}
              busy={busy}
              onRewind={(id) =>
                guard(() => api.rewind(session.session_id, id), "Вернуться к точке")
              }
            />
          )}
          <div ref={bottom} />
        </div>

        <Composer busy={busy} hasSession={Boolean(session)} onSend={send} />
      </div>

      {moves && <AgentCursor moves={moves} onDone={() => setMoves(null)} />}

      {session && boardOpen && (
        <BoardLayer title={session.title} onClose={() => setBoardOpen(false)}>
          <Dashboard
            session={session}
            busy={busy}
            onView={changeView}
            onLayout={changeLayout}
            onAddPanel={(panel) =>
              changeBoard(() => api.addPanel(session.session_id, panel), "Добавить панель")
            }
            onRemovePanel={(panelId) =>
              changeBoard(() => api.removePanel(session.session_id, panelId), "Убрать панель")
            }
            onDropStep={(stepId) =>
              guard(() => api.dropStep(session.session_id, stepId), "Убрать вычисление")
            }
            onUndo={() => guard(() => api.undo(session.session_id), "Отменить")}
            onSave={(title, asNew) =>
              guard(() => api.saveDashboard(session.session_id, title, asNew), "Сохранить дашборд")
            }
          />
          <DockedChat
            turns={turns}
            busy={busy}
            onSend={send}
            onFull={() => setBoardOpen(false)}
            offerFor={offer?.turn ?? null}
            onShow={() =>
              session && offer && void showWork(session, offer.wasId, offer.wasView)
            }
          />
        </BoardLayer>
      )}
    </>
  );
}
