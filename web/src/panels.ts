import type { BoardTab, Layout, Slot } from "./types";

/** Тот же вид, что у сервера (`layout.fresh_id`): префикс и шесть знаков.
 *  Идентификатор живёт до ближайшей пересборки, когда согласование либо
 *  примет его, либо заменит своим. */
const fresh = (prefix: string) => `${prefix}${Math.random().toString(36).slice(2, 8)}`;

/** Куда ложится перетаскиваемая ячейка. Край целевой коробки означает
 *  «встань рядом», середина — «склейся с ней в одну». */
export type Drop =
  | { kind: "before" | "after"; slot: string }
  | { kind: "merge"; slot: string };

export function moveSlot(slots: Slot[], dragged: string, drop: Drop): Slot[] {
  if (dragged === drop.slot) return slots;
  const from = slots.find((s) => s.id === dragged);
  if (!from) return slots;

  const rest = slots.filter((s) => s.id !== dragged);
  const at = rest.findIndex((s) => s.id === drop.slot);
  if (at < 0) return slots;

  if (drop.kind === "merge") {
    const target = rest[at];
    return rest.map((s) =>
      s.id === target.id ? { ...s, panels: [...s.panels, ...from.panels] } : s,
    );
  }
  const next = [...rest];
  next.splice(drop.kind === "before" ? at : at + 1, 0, from);
  return next;
}

/** Вынимает панель из склеенной коробки обратно в свою. Последнюю панель
 *  вынуть нельзя — коробка осталась бы пустой. */
export function splitSlot(slots: Slot[], slotId: string, panelId: string): Slot[] {
  const at = slots.findIndex((s) => s.id === slotId);
  if (at < 0) return slots;
  const slot = slots[at];
  if (slot.panels.length < 2) return slots;

  const kept = slot.panels.filter((p) => p !== panelId);
  const next = [...slots];
  next[at] = { ...slot, panels: kept, active: Math.min(slot.active, kept.length - 1) };
  next.splice(at + 1, 0, { id: fresh("s"), w: 1, panels: [panelId], active: 0 });
  return next;
}

export function resizeSlot(slots: Slot[], slotId: string, w: number): Slot[] {
  return slots.map((s) => (s.id === slotId ? { ...s, w } : s));
}

export function showTab(slots: Slot[], slotId: string, active: number): Slot[] {
  return slots.map((s) => (s.id === slotId ? { ...s, active } : s));
}

/** Заменяет ячейки активной вкладки, остальные оставляет как были. */
export function withSlots(layout: Layout, slots: Slot[]): Layout {
  return {
    ...layout,
    tabs: layout.tabs.map((t) => (t.id === layout.active ? { ...t, slots } : t)),
  };
}

export function activeSlots(layout: Layout): Slot[] {
  return layout.tabs.find((t) => t.id === layout.active)?.slots ?? [];
}

// ─── вкладки дашборда ────────────────────────────────────────────────────────

/** Новая вкладка — пустая и сразу открытая. Сервер пустую вкладку не
 *  выбрасывает именно потому, что её только что завели руками: панель
 *  приедет следующим движением. */
export function addTab(layout: Layout, title: string): Layout {
  const tab: BoardTab = { id: fresh("t"), title, slots: [] };
  return { ...layout, tabs: [...layout.tabs, tab], active: tab.id };
}

export function openTab(layout: Layout, tabId: string): Layout {
  return { ...layout, active: tabId };
}

export function renameTab(layout: Layout, tabId: string, title: string): Layout {
  return {
    ...layout,
    tabs: layout.tabs.map((t) => (t.id === tabId ? { ...t, title } : t)),
  };
}

/** Вкладка уходит, её ячейки — нет. Панели продолжают собираться, и
 *  согласование вернуло бы их в любом случае; лучше сделать это осознанно и
 *  рядом с тем местом, где человек смотрит. Последнюю вкладку убрать нельзя:
 *  дашборду нужна хотя бы одна. */
export function removeTab(layout: Layout, tabId: string): Layout {
  if (layout.tabs.length < 2) return layout;
  const going = layout.tabs.find((t) => t.id === tabId);
  if (!going) return layout;

  const rest = layout.tabs.filter((t) => t.id !== tabId);
  const landing = layout.active === tabId ? rest[0].id : layout.active;
  return {
    ...layout,
    tabs: rest.map((t) =>
      t.id === landing ? { ...t, slots: [...t.slots, ...going.slots] } : t,
    ),
    active: landing,
  };
}

/** Перенос ячейки на другую вкладку. Открытой остаётся та, с которой
 *  переносили: человек продолжает разбирать её, а не уезжает следом. */
export function moveSlotToTab(layout: Layout, slotId: string, tabId: string): Layout {
  const from = layout.tabs.find((t) => t.slots.some((s) => s.id === slotId));
  if (!from || from.id === tabId) return layout;
  const slot = from.slots.find((s) => s.id === slotId)!;
  return {
    ...layout,
    tabs: layout.tabs.map((t) => {
      if (t.id === from.id) return { ...t, slots: t.slots.filter((s) => s.id !== slotId) };
      if (t.id === tabId) return { ...t, slots: [...t.slots, slot] };
      return t;
    }),
  };
}
