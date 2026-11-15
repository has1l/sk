"""Согласование сохранённой раскладки с набором панелей, который собрал сервер.

Набор не постоянен: водопад появляется только после вопроса «почему», а
вычисление может добавить панель. Раскладка при этом живёт в сохранённом
дашборде месяцами. Значит, расходиться они будут всегда, и вопрос только в
том, чинится это молча или ломает экран.
"""

from app import layout
from app.schema import BoardTab, DashboardConfig, Layout, Slot


def conf(*tabs: BoardTab, active: str = "", columns: int = 2) -> DashboardConfig:
    return DashboardConfig(
        layout=Layout(columns=columns, tabs=list(tabs), active=active or (tabs[0].id if tabs else ""))
    )


def ids_of(result: Layout) -> list[list[str]]:
    return [slot.panels for tab in result.tabs for slot in tab.slots]


def test_empty_config_lays_panels_out_in_server_order():
    result = layout.reconcile(DashboardConfig(), ["p1", "p2", "p3"])
    assert ids_of(result) == [["p1"], ["p2"], ["p3"]]
    assert result.active == result.tabs[0].id


def test_panel_that_disappeared_is_dropped_and_leaves_no_hole():
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", panels=["p1"]),
        Slot(id="s2", panels=["p5"]),
        Slot(id="s3", panels=["p2"]),
    ]))
    # Водопад p5 пропал: вопроса «почему» в этой сессии не было.
    result = layout.reconcile(saved, ["p1", "p2"])
    assert ids_of(result) == [["p1"], ["p2"]]


def test_new_panel_is_appended_not_lost():
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]))
    result = layout.reconcile(saved, ["p1", "p5"])
    assert ids_of(result) == [["p1"], ["p5"]]


def test_user_order_survives_reconcile():
    """Главное свойство: человек разложил панели — согласование это уважает."""
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", panels=["p3"]),
        Slot(id="s2", panels=["p1"]),
        Slot(id="s3", panels=["p2"]),
    ]))
    result = layout.reconcile(saved, ["p1", "p2", "p3"])
    assert ids_of(result) == [["p3"], ["p1"], ["p2"]]


def test_merged_slot_keeps_both_panels_and_width():
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", w=2, panels=["p1", "p4"], active=1),
    ]))
    result = layout.reconcile(saved, ["p1", "p4"])
    slot = result.tabs[0].slots[0]
    assert slot.panels == ["p1", "p4"]
    assert slot.w == 2
    assert slot.active == 1


def test_merged_slot_survives_losing_one_of_its_panels():
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", panels=["p1", "p5"], active=1),
    ]))
    result = layout.reconcile(saved, ["p1"])
    slot = result.tabs[0].slots[0]
    assert slot.panels == ["p1"]
    # Открытой была вторая вкладка, её больше нет — иначе коробка нарисуется пустой.
    assert slot.active == 0


def test_duplicate_reference_is_kept_once():
    """Панель не может стоять в двух местах: иначе Plotly рисует её дважды в
    один и тот же контейнер и второй график остаётся пустым."""
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", panels=["p1"]),
        Slot(id="s2", panels=["p1", "p2"]),
    ]))
    result = layout.reconcile(saved, ["p1", "p2"])
    assert ids_of(result) == [["p1"], ["p2"]]


def test_width_is_clamped_to_the_grid():
    saved = conf(BoardTab(id="t1", title="Обзор", slots=[
        Slot(id="s1", w=9, panels=["p1"]),
        Slot(id="s2", w=0, panels=["p2"]),
    ]))
    result = layout.reconcile(saved, ["p1", "p2"])
    assert [s.w for s in result.tabs[0].slots] == [2, 1]


def test_new_panel_lands_on_the_active_tab():
    saved = conf(
        BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]),
        BoardTab(id="t2", title="Регионы", slots=[Slot(id="s2", panels=["p2"])]),
        active="t2",
    )
    result = layout.reconcile(saved, ["p1", "p2", "p5"])
    assert [s.panels for s in result.tabs[1].slots] == [["p2"], ["p5"]]


def test_tab_emptied_by_vanished_panels_is_removed_but_never_the_last_one():
    saved = conf(
        BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]),
        BoardTab(id="t2", title="Пусто", slots=[Slot(id="s2", panels=["p5"])]),
    )
    result = layout.reconcile(saved, ["p1"])
    assert [t.id for t in result.tabs] == ["t1"]

    everything_gone = layout.reconcile(saved, [])
    assert len(everything_gone.tabs) == 1
    assert everything_gone.tabs[0].slots == []


def test_active_tab_that_vanished_falls_back_to_the_first():
    saved = conf(
        BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]),
        BoardTab(id="t2", title="Пусто", slots=[Slot(id="s2", panels=["p5"])]),
        active="t2",
    )
    result = layout.reconcile(saved, ["p1"])
    assert result.active == "t1"


def test_reconcile_is_idempotent():
    once = layout.reconcile(DashboardConfig(), ["p1", "p2", "p5"])
    twice = layout.reconcile(DashboardConfig(layout=once), ["p1", "p2", "p5"])
    assert twice.model_dump() == once.model_dump()


def test_rows_pack_without_holes():
    """Укладка: ячейки шириной 1 и 2 раскладываются по строкам без дырок."""
    rows = layout.pack([Slot(id="a", w=1), Slot(id="b", w=2), Slot(id="c", w=1)], columns=2)
    assert rows == [["a"], ["b"], ["c"]]

    rows = layout.pack([Slot(id="a", w=1), Slot(id="b", w=1), Slot(id="c", w=2)], columns=2)
    assert rows == [["a", "b"], ["c"]]


def test_wide_panel_appears_full_width_but_only_the_first_time():
    """Мост из восьми ступеней в половине строки нечитаем, поэтому при
    появлении он занимает всю ширину. Но если его сузили руками — это выбор
    человека, и согласование его не отменяет."""
    first = layout.reconcile(DashboardConfig(), ["p1", "p5"], wide={"p5"})
    assert [s.w for s in first.tabs[0].slots] == [1, 2]

    narrowed = first.model_copy(deep=True)
    narrowed.tabs[0].slots[1].w = 1
    again = layout.reconcile(DashboardConfig(layout=narrowed), ["p1", "p5"], wide={"p5"})
    assert [s.w for s in again.tabs[0].slots] == [1, 1]


def test_tab_created_empty_survives_but_one_that_lost_its_panels_does_not():
    """Пустая вкладка бывает двух разных родов, и путать их нельзя.

    Человек завёл вкладку и ещё не перетащил в неё панель — выбросить её
    значит выдернуть страницу из-под рук. У вкладки кончились панели —
    оставить её значит показать пустой экран там, где раньше были графики.
    """
    saved = conf(
        BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]),
        BoardTab(id="t2", title="Новая", slots=[]),
        BoardTab(id="t3", title="Осиротела", slots=[Slot(id="s2", panels=["p5"])]),
    )
    result = layout.reconcile(saved, ["p1"])
    assert [t.id for t in result.tabs] == ["t1", "t2"]


def test_new_panel_lands_on_the_open_tab_even_when_it_is_empty():
    """Иначе «добавить панель», стоя на свежей вкладке, кладёт её на соседнюю,
    и человек решает, что кнопка не сработала."""
    saved = conf(
        BoardTab(id="t1", title="Обзор", slots=[Slot(id="s1", panels=["p1"])]),
        BoardTab(id="t2", title="Новая", slots=[]),
        active="t2",
    )
    result = layout.reconcile(saved, ["p1", "c7"])
    assert [s.panels for s in result.tabs[1].slots] == [["c7"]]
    assert result.active == "t2"
