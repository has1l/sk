"""Раскладка дашборда: какие панели в каких ячейках и в каком порядке.

Место ячейки задаётся её позицией в списке, а не координатами. Строки считает
укладка, поэтому дырок в сетке не бывает по построению: удалили панель —
соседи сомкнулись сами, и чинить нечего.

Набор панелей собирает сервер, и он непостоянен: водопад появляется только
после вопроса «почему». Раскладка же живёт в сохранённом дашборде месяцами.
Расходиться они будут всегда — `reconcile` сводит их обратно так, чтобы
порядок, выбранный человеком, уцелел, а экран не сломался.
"""

from __future__ import annotations

from uuid import uuid4

from app.schema import BoardTab, DashboardConfig, Layout, Slot

FIRST_TAB = "Обзор"


def fresh_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:6]}"


def reconcile(
    config: DashboardConfig, built: list[str], wide: set[str] | None = None
) -> Layout:
    """Сводит сохранённую раскладку с панелями, которые собрались сейчас.

    Каждая собранная панель попадает в раскладку ровно один раз: ссылки на
    исчезнувшие панели выбрасываются, дубликаты схлопываются, новые панели
    дописываются в конец активной вкладки.

    `wide` — панели, которым при первом появлении нужна вся ширина (мост из
    восьми ступеней в половине строки нечитаем). Это только начальное
    значение: сузил руками — так и останется.
    """
    saved = config.layout or Layout()
    columns = saved.columns if saved.columns >= 1 else 2
    known = set(built)
    seen: set[str] = set()

    tabs: list[BoardTab] = []
    # Вкладка, созданная пустой, — намерение человека: он её только что завёл
    # и сейчас перетащит туда панель. Вкладка, у которой панели кончились, —
    # другое дело: там уже ничего нет и не будет.
    blank: set[str] = set()
    for tab in saved.tabs:
        slots: list[Slot] = []
        for slot in tab.slots:
            kept = [p for p in slot.panels if p in known and p not in seen]
            seen.update(kept)
            if not kept:
                continue
            slots.append(
                Slot(
                    id=slot.id or fresh_id("s"),
                    w=min(max(slot.w, 1), columns),
                    panels=kept,
                    # Открытой могла быть вкладка, которой больше нет: без
                    # этого коробка нарисовалась бы пустой.
                    active=slot.active if 0 <= slot.active < len(kept) else 0,
                )
            )
        fresh_tab = BoardTab(id=tab.id or fresh_id("t"), title=tab.title, slots=slots)
        if not tab.slots:
            blank.add(fresh_tab.id)
        tabs.append(fresh_tab)

    # Вкладка, из которой панели исчезли, — пустая страница, на которую человек
    # наткнётся и решит, что всё пропало. Последнюю всё же оставляем: дашборду
    # нужна хотя бы одна, даже если показывать пока нечего.
    alive = [t for t in tabs if t.slots or t.id in blank]
    if not alive:
        alive = [tabs[0]] if tabs else [BoardTab(id=fresh_id("t"), title=FIRST_TAB)]
        alive[0].slots = []

    active = saved.active if any(t.id == saved.active for t in alive) else alive[0].id

    fresh = [p for p in built if p not in seen]
    if fresh:
        target = next(t for t in alive if t.id == active)
        full = wide or set()
        target.slots.extend(
            Slot(id=fresh_id("s"), w=columns if p in full else 1, panels=[p]) for p in fresh
        )

    return Layout(columns=columns, tabs=alive, active=active)


def pack(slots: list[Slot], columns: int) -> list[list[str]]:
    """Раскладывает ячейки по строкам слева направо.

    Ячейка, которой не хватает места в строке, переносится целиком: половина
    графика в одной строке и половина в следующей — не график.
    """
    rows: list[list[str]] = []
    row: list[str] = []
    used = 0
    for slot in slots:
        width = min(max(slot.w, 1), columns)
        if used + width > columns and row:
            rows.append(row)
            row, used = [], 0
        row.append(slot.id)
        used += width
        if used >= columns:
            rows.append(row)
            row, used = [], 0
    if row:
        rows.append(row)
    return rows
