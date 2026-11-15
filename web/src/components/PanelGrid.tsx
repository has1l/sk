import { useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  activeSlots,
  addTab,
  moveSlot,
  moveSlotToTab,
  openTab,
  removeTab,
  renameTab,
  resizeSlot,
  showTab,
  splitSlot,
  withSlots,
} from "../panels";
import type { ChartPanel, Layout, Slot } from "../types";

/** Порог, после которого нажатие считается переносом. Без него щелчок по
 *  вкладке внутри коробки уезжал бы вместе с коробкой. */
const DRAG_START = 5;

/** Ширина карточки, которая едет за курсором. */
const CARD_W = 260;

/** Полоса у края прокрутки, в которой список едет сам. Без неё панель с
 *  восьмой позиции на первую не перенести: цель за экраном. */
const SCROLL_EDGE = 90;
const SCROLL_SPEED = 14;

/** Сколько соседи расступаются. */
const SHIFT_MS = 240;

/** Сколько держать курсор на шапке, чтобы склеить. Без выдержки шапка соседа,
 *  съехавшая под курсор после перестановки, склеивала панели случайно. */
const MERGE_DWELL = 350;

/** Куда целится перенос сверх перестановки: склеиться с панелью (курсор на
 *  её шапке) или уехать на другую вкладку дашборда (курсор на ярлыке). */
type Aim = { to: "merge"; slot: string } | { to: "tab"; tab: string } | null;

const inside = (r: DOMRect, x: number, y: number) =>
  x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;

const calm = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function PanelGrid({
  layout,
  panels,
  busy,
  onLayout,
  onRemovePanel,
  tools,
  render,
}: {
  layout: Layout;
  panels: ChartPanel[];
  busy: boolean;
  onLayout: (next: Layout) => void;
  onRemovePanel: (panelId: string) => void;
  tools?: React.ReactNode;
  render: (panel: ChartPanel, slot: Slot) => React.ReactNode;
}) {
  const [held, setHeld] = useState<string | null>(null);
  const [aim, setAim] = useState<Aim>(null);
  const [card, setCard] = useState<{ x: number; y: number } | null>(null);
  // Порядок на время переноса. Соседи расступаются по нему вживую, а на
  // сервер уходит только итог — один раз, при отпускании.
  const [preview, setPreview] = useState<Slot[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const box = useRef<HTMLDivElement>(null);
  const grab = useRef<{ dx: number; dy: number }>({ dx: 0, dy: 0 });
  const start = useRef<{ x: number; y: number; id: string } | null>(null);
  const order = useRef<Slot[] | null>(null);
  const target = useRef<Aim>(null);
  // Коробка, с которой только что поменялись местами. Пока курсор над ней,
  // второй обмен запрещён: иначе после перестановки она снова оказывается под
  // курсором, и пара начинает меняться туда-обратно.
  const swapped = useRef<string | null>(null);
  const scroller = useRef<HTMLElement | null>(null);
  const roll = useRef(0);
  const frame = useRef(0);
  const spots = useRef(new Map<string, { x: number; y: number }>());
  const lastOrder = useRef("");
  const dwell = useRef<{ id: string; timer: number } | null>(null);

  const slots = activeSlots(layout);
  const shown = preview ?? slots;
  const byId = new Map(panels.map((p) => [p.id, p]));
  const apply = (next: Slot[]) => onLayout(withSlots(layout, next));

  /** Соседи переезжают плавно (FLIP): после перестановки каждая коробка
   *  стартует со своего прежнего места и доезжает до нового. Места меряются
   *  относительно сетки, а не окна, — иначе прокрутка выглядела бы как
   *  перестановка и дёргала всё разом. */
  useLayoutEffect(() => {
    const grid = box.current;
    if (!grid) return;
    const origin = grid.getBoundingClientRect();
    const key = shown.map((s) => s.id).join("|");
    const moved = key !== lastOrder.current && lastOrder.current !== "";
    const next = new Map<string, { x: number; y: number }>();
    grid.querySelectorAll<HTMLElement>("[data-slot]").forEach((el) => {
      const r = el.getBoundingClientRect();
      const at = { x: r.left - origin.left, y: r.top - origin.top };
      const was = spots.current.get(el.dataset.slot!);
      next.set(el.dataset.slot!, at);
      if (!moved || !was || calm()) return;
      const dx = was.x - at.x;
      const dy = was.y - at.y;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      el.animate(
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
        { duration: SHIFT_MS, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
      );
    });
    spots.current = next;
    lastOrder.current = key;
  });

  /** Движение и отпускание слушает окно, а не захваченный элемент. Захват
   *  указателя система отбирает когда хочет, и перенос обрывался на полпути. */
  useEffect(() => {
    if (!held) return;
    // Признак для всех, кто слушает Escape на том же окне: слой дашборда
    // иначе закрылся бы вместе с отменой переноса.
    document.body.dataset.dragging = "1";
    scroller.current = box.current?.closest<HTMLElement>(".layer-body") ?? null;

    const aimAt = (next: Aim) => {
      if (dwell.current && !(next?.to === "merge" && next.slot === dwell.current.id)) {
        clearTimeout(dwell.current.timer);
        dwell.current = null;
      }
      target.current = next;
      setAim(next);
    };

    /** Склейка — только после выдержки на шапке. */
    const hover = (id: string) => {
      if (target.current?.to === "merge" && target.current.slot === id) return;
      if (dwell.current?.id === id) return;
      aimAt(null);
      dwell.current = {
        id,
        timer: window.setTimeout(() => {
          if (dwell.current?.id !== id) return;
          target.current = { to: "merge", slot: id };
          setAim(target.current);
        }, MERGE_DWELL),
      };
    };

    /** Цель считается по живым прямоугольникам на каждом движении. Раньше они
     *  замораживались при захвате — и после самоезда прокрутки устаревали:
     *  бросок уходил не туда, куда показывал курсор. */
    const place = (x: number, y: number) => {
      const now = order.current ?? slots;

      const tab = Array.from(document.querySelectorAll<HTMLElement>("[data-tab]")).find(
        (el) => el.dataset.tab !== layout.active && inside(el.getBoundingClientRect(), x, y),
      );
      if (tab) return aimAt({ to: "tab", tab: tab.dataset.tab! });

      const boxes = Array.from(box.current?.querySelectorAll<HTMLElement>("[data-slot]") ?? []);
      for (const el of boxes) {
        const id = el.dataset.slot!;
        if (!inside(el.getBoundingClientRect(), x, y)) continue;
        if (id === held) {
          swapped.current = null;
          return aimAt(null);
        }
        // Шапка чужой панели — склеить. Тело — встать на её место. Раньше
        // склейкой была вся середина коробки, и панели слипались случайно.
        const bar = el.querySelector(".slot-bar")?.getBoundingClientRect();
        if (bar && y <= bar.bottom + 4) return hover(id);
        aimAt(null);
        if (swapped.current === id) return;
        const from = now.findIndex((s) => s.id === held);
        const to = now.findIndex((s) => s.id === id);
        const next = moveSlot(now, held, { kind: from < to ? "after" : "before", slot: id });
        swapped.current = id;
        order.current = next;
        setPreview(next);
        return;
      }

      // Ниже всех коробок — в конец.
      aimAt(null);
      swapped.current = null;
      const lowest = Math.max(...boxes.map((el) => el.getBoundingClientRect().bottom));
      if (y > lowest && now[now.length - 1]?.id !== held) {
        const rest = now.filter((s) => s.id !== held);
        const next = [...rest, now.find((s) => s.id === held)!];
        order.current = next;
        setPreview(next);
      }
    };

    const onMove = (event: PointerEvent) => {
      event.preventDefault();
      const { clientX: x, clientY: y } = event;
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => setCard({ x, y }));
      place(x, y);

      const pane = scroller.current;
      if (!pane) return;
      const r = pane.getBoundingClientRect();
      const step = y - r.top < SCROLL_EDGE ? -SCROLL_SPEED : r.bottom - y < SCROLL_EDGE ? SCROLL_SPEED : 0;
      cancelAnimationFrame(roll.current);
      if (step) {
        const go = () => {
          pane.scrollTop += step;
          place(x, y);
          roll.current = requestAnimationFrame(go);
        };
        roll.current = requestAnimationFrame(go);
      }
    };

    const finish = (commit: boolean) => {
      if (dwell.current) clearTimeout(dwell.current.timer);
      dwell.current = null;
      cancelAnimationFrame(frame.current);
      cancelAnimationFrame(roll.current);
      const landed = target.current;
      const next = order.current;
      const dragged = held;
      target.current = null;
      order.current = null;
      swapped.current = null;
      start.current = null;
      setHeld(null);
      setAim(null);
      setCard(null);
      setPreview(null);
      if (!commit || !dragged) return;
      if (landed?.to === "tab") {
        onLayout(moveSlotToTab(layout, dragged, landed.tab));
      } else if (landed?.to === "merge") {
        apply(moveSlot(next ?? slots, dragged, { kind: "merge", slot: landed.slot }));
      } else if (next && next.map((s) => s.id).join() !== slots.map((s) => s.id).join()) {
        apply(next);
      }
    };

    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopImmediatePropagation();
      finish(false);
    };

    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    window.addEventListener("keydown", onKey, { capture: true });
    return () => {
      delete document.body.dataset.dragging;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      window.removeEventListener("keydown", onKey, { capture: true });
      cancelAnimationFrame(frame.current);
      cancelAnimationFrame(roll.current);
    };
  });

  /** Пока переименовывают вкладку, Escape принадлежит полю ввода: он
   *  отменяет правку, а не закрывает дашборд. Признак, а не порядок
   *  обработчиков, — см. «Escape принадлежит самому внутреннему». */
  useEffect(() => {
    if (!editing) return;
    document.body.dataset.inner = "1";
    return () => {
      delete document.body.dataset.inner;
    };
  }, [editing]);

  /** До порога ничего не происходит: нажатие может оказаться щелчком. */
  const press = (slot: Slot) => (event: React.PointerEvent) => {
    if (busy || event.button !== 0) return;
    const r = (event.currentTarget as HTMLElement).getBoundingClientRect();
    grab.current = {
      dx: Math.min(event.clientX - r.left, CARD_W - 44),
      dy: Math.min(event.clientY - r.top, 20),
    };
    start.current = { x: event.clientX, y: event.clientY, id: slot.id };
  };

  const maybeStart = (event: React.PointerEvent) => {
    const from = start.current;
    if (!from || held) return;
    if (Math.hypot(event.clientX - from.x, event.clientY - from.y) <= DRAG_START) return;
    setCard({ x: event.clientX, y: event.clientY });
    setHeld(from.id);
  };

  const release = () => {
    if (!held) start.current = null;
  };

  return (
    <>
      {/* Полоса вкладок. Одна вкладка — всё равно показываем: иначе кнопку
          «ещё вкладка» негде держать, а дашборд из двух страниц так и не
          случится. */}
      <div className="board-tabs">
        <div className="tab-strip">
          {layout.tabs.map((tab) =>
            editing === tab.id ? (
              <input
                key={tab.id}
                className="tab-name"
                autoFocus
                defaultValue={tab.title}
                onFocus={(e) => e.currentTarget.select()}
                onBlur={(e) => {
                  onLayout(renameTab(layout, tab.id, e.target.value.trim() || tab.title));
                  setEditing(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                  if (e.key === "Escape") setEditing(null);
                }}
              />
            ) : (
              <button
                key={tab.id}
                data-tab={tab.id}
                className={`tab${tab.id === layout.active ? " on" : ""}${
                  aim?.to === "tab" && aim.tab === tab.id ? " aiming" : ""
                }`}
                title={
                  tab.id === layout.active
                    ? "Двойной щелчок — переименовать"
                    : "Открыть вкладку. Панель можно принести сюда переносом"
                }
                onClick={() => onLayout(openTab(layout, tab.id))}
                onDoubleClick={() => setEditing(tab.id)}
              >
                {tab.title}
                {tab.id === layout.active && layout.tabs.length > 1 && (
                  <span
                    className="tab-x"
                    role="button"
                    aria-label="Убрать вкладку"
                    title="Убрать вкладку — её панели переедут на соседнюю"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      onLayout(removeTab(layout, tab.id));
                    }}
                  >
                    <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
                      <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                    </svg>
                  </span>
                )}
              </button>
            ),
          )}
          <button
            className="tab-add"
            title="Ещё вкладка — своя страница дашборда"
            onClick={() => onLayout(addTab(layout, `Вкладка ${layout.tabs.length + 1}`))}
          >
            <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">
              <path d="M6 2v8M2 6h8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        {tools && <div className="tab-tools">{tools}</div>}
      </div>

      <div
        ref={box}
        className={`grid${held ? " moving" : ""}`}
        style={{ ["--columns" as string]: layout.columns }}
      >
      {shown.map((slot, place) => {
        const shown = byId.get(slot.panels[slot.active] ?? slot.panels[0]);
        if (!shown) return null;
        const merged = slot.panels.length > 1;
        const carried = held === slot.id;
        const merging = aim?.to === "merge" && aim.slot === slot.id;

        return (
          <section
            key={slot.id}
            data-slot={slot.id}
            // Схваченная панель остаётся в сетке пустым местом своего размера:
            // раньше она сжималась в карточку, сетка схлопывалась, и всё
            // прыгало под курсором.
            className={`slot${carried ? " held" : ""}${merging ? " drop-merge" : ""}`}
            style={{
              gridColumn: `span ${Math.min(slot.w, layout.columns)}`,
              // Порядок появления: панели выезжают лесенкой, а не разом.
              ["--i" as string]: place,
            }}
          >
            <header
              className="slot-bar"
              onPointerDown={press(slot)}
              onPointerMove={maybeStart}
              onPointerUp={release}
            >
              <span className="grip" aria-hidden="true">
                <svg viewBox="0 0 10 16" width="10" height="16" fill="currentColor">
                  <circle cx="2.5" cy="3" r="1.3" /><circle cx="7.5" cy="3" r="1.3" />
                  <circle cx="2.5" cy="8" r="1.3" /><circle cx="7.5" cy="8" r="1.3" />
                  <circle cx="2.5" cy="13" r="1.3" /><circle cx="7.5" cy="13" r="1.3" />
                </svg>
              </span>

              {merged ? (
                <div className="slot-tabs">
                  {slot.panels.map((id, index) => (
                    <button
                      key={id}
                      className={index === slot.active ? "on" : ""}
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={() => apply(showTab(slots, slot.id, index))}
                    >
                      {byId.get(id)?.spec.title ?? "Панель"}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="slot-title">{shown.spec.title}</span>
              )}

              <div className="slot-tools">
                {merged && (
                  <button
                    title="Разъединить — панель выйдет в свою коробку"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => apply(splitSlot(slots, slot.id, shown.id))}
                  >
                    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
                      <path d="M6.5 2.5h-4v4M9.5 13.5h4v-4M13.5 2.5l-11 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                )}
                <button
                  title="Убрать панель с дашборда"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => onRemovePanel(shown.id)}
                >
                  <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
                    <path d="M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.6 8h4.8l.6-8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <button
                  title={slot.w > 1 ? "Сузить до половины" : "Растянуть на всю ширину"}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => apply(resizeSlot(slots, slot.id, slot.w > 1 ? 1 : layout.columns))}
                >
                  <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
                    {slot.w > 1 ? (
                      <path d="M6.5 4 3.5 8l3 4M9.5 4l3 4-3 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    ) : (
                      <path d="M3 8h10M6 5 3 8l3 3M10 5l3 3-3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    )}
                  </svg>
                </button>
              </div>
            </header>

            {/* График прячется, но не размонтируется: Plotly пересоздаёт его
                заново полсекунды, и панель мигала бы на каждый захват. */}
            <div className="slot-body">{render(shown, slot)}</div>
          </section>
        );
      })}

      {/* Пустая вкладка объясняет свою пустоту ровно по той же причине, по
          какой это делает панель без данных: молчащий экран читается как
          поломка. */}
      {!slots.length && (
        <p className="tab-empty">
          Вкладка пустая. Перенесите сюда панель — возьмите её за шапку на
          соседней вкладке и доведите до ярлыка этой.
        </p>
      )}

      {/* За курсором едет лёгкая карточка с названием, а не сама панель с
          графиком: она не дёргает раскладку и видна поверх всего. */}
      {held && card && (
        <div
          className={`drag-card${aim ? " aiming" : ""}`}
          aria-hidden="true"
          style={{
            width: CARD_W,
            transform: `translate3d(${card.x - grab.current.dx}px, ${card.y - grab.current.dy}px, 0)`,
          }}
        >
          <span className="drag-card-title">
            {byId.get(slots.find((s) => s.id === held)?.panels[0] ?? "")?.spec.title ?? "Панель"}
          </span>
          <span className="drag-card-hint">
            {aim?.to === "merge"
              ? "отпустите — склеится вкладками"
              : aim?.to === "tab"
                ? "отпустите — уедет на вкладку"
                : "подержите на шапке другой панели — склеить"}
          </span>
        </div>
      )}
      </div>
    </>
  );
}
