"""Клиентская ветка: факт на зерне клиента, плана в ней нет.

План ставится на «месяц × точка × продукт», клиента в нём нет. Поэтому
главное, что здесь проверяется, — что нигде не появляется «план ноль» и
«выполнение 0 %»: такие числа правдоподобны и полностью ложны.
"""

from datetime import date

import pandas as pd

from app import aggregate, dashboard, insights, sql_builder
from app.schema import (
    DashboardConfig,
    Dimension,
    Filter,
    Metric,
    Period,
    QuerySpec,
    ViewState,
)

HORIZON = date(2026, 9, 1)


def spec(**over) -> QuerySpec:
    base = dict(metrics=[Metric.FACT_AMOUNT], period=Period(date_from=date(2026, 1, 1), date_to=date(2026, 9, 1)))
    base.update(over)
    return QuerySpec(**base)


def test_client_filter_switches_the_source_to_the_client_view():
    built = sql_builder.build_detail(
        spec(filters=[Filter(dimension=Dimension.CLIENT, values=["ООО «Ромашка»"])]), HORIZON
    )
    assert "FROM client_fact_flat" in built.sql
    assert "client_name = ANY(%s)" in built.sql
    assert "client_segment" in built.sql and "discount_reason" in built.sql
    assert any("Плана по клиентам" in n for n in built.notes)


def test_ordinary_query_stays_on_the_plan_fact_view():
    built = sql_builder.build_detail(spec(dimensions=[Dimension.REGION]), HORIZON)
    assert "FROM plan_fact_flat" in built.sql
    assert "client_name" not in built.sql


def test_client_value_goes_as_parameter_never_into_sql_text():
    evil = "x'; DROP TABLE sales; --"
    built = sql_builder.build_detail(
        spec(filters=[Filter(dimension=Dimension.CLIENT, values=[evil])]), HORIZON
    )
    assert evil not in built.sql
    assert [evil] in built.params


def client_frame() -> pd.DataFrame:
    rows = []
    for month, reason, fact, discount in [
        (date(2026, 8, 1), "Без скидки", 1000.0, 0.0),
        (date(2026, 8, 1), "Промо-акция", 500.0, 50.0),
        (date(2026, 9, 1), "Лояльность клиента", 800.0, 120.0),
        (date(2026, 9, 1), "Без скидки", 700.0, 0.0),
    ]:
        rows.append(
            {
                "month": month,
                "region_name": "Центральный",
                "outlet_name": "Точка 1",
                "city": "Москва",
                "outlet_type": "Магазин",
                "product_name": "Продукт 1",
                "category": "Напитки",
                "client_name": "ООО «Ромашка»",
                "client_segment": "Сеть",
                "discount_reason": reason,
                "plan_amount": 0.0,
                "plan_qty": 0.0,
                "fact_amount": fact,
                "fact_qty": 1.0,
                "sales_count": 1.0,
                "discount_amount": discount,
            }
        )
    return aggregate.prepare(pd.DataFrame(rows))


def client_view() -> ViewState:
    return ViewState(
        primary=Dimension.DISCOUNT_REASON,
        table_dimensions=[Dimension.DISCOUNT_REASON],
        date_from=date(2026, 8, 1),
        date_to=date(2026, 9, 1),
    )


def test_client_dashboard_has_no_plan_cards_and_no_plan_series():
    view = client_view()
    board, _ = dashboard.build(client_frame(), view, [], dashboard.default_config(view))
    keys = [k.key for k in board.kpis]
    assert "plan" not in keys and "completion" not in keys and "deviation" not in keys
    share = next(k for k in board.kpis if k.key == "discount_share")
    assert abs(share.value - 170 / 3000 * 100) < 0.01
    for panel in board.panels:
        assert all(s.field != Metric.PLAN_AMOUNT.value for s in panel.spec.series), panel.spec.title
        assert "Выполнение" not in panel.spec.title
    assert not any(p.spec.kind == "waterfall" for p in board.panels), "мосту не от чего строиться"


def test_client_dashboard_offers_client_toggles_and_filters():
    view = client_view()
    board, _ = dashboard.build(client_frame(), view, [], dashboard.default_config(view))
    primary = next(t for t in board.toggles if t.key == "primary")
    assert "discount_reason" in [o["value"] for o in primary.options]
    metric = next(t for t in board.toggles if t.key == "metric")
    assert "plan_amount" not in [o["value"] for o in metric.options]
    assert "client" in [f.dimension for f in board.filters]


def test_client_summary_names_the_main_discount_reason_and_says_there_is_no_plan():
    lines = insights.build(client_frame(), client_view(), HORIZON)
    text = " ".join(lines)
    assert "Плана по клиентам" in text
    assert "лояльность клиента" in text
    assert "план выполнен" not in text
