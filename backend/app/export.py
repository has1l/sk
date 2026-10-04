"""Выгрузка: таблица в CSV и дашборд в самодостаточный HTML.

CSV собирается с разделителем «;» и BOM — иначе Excel на русской локали
открывает файл одной колонкой и ломает кириллицу. Это не придирка: кейс
ориентирован на руководителей, которые откроют файл двойным щелчком.

HTML собирается на сервере и содержит цифры, а не картинку: страницу можно
отправить в мессенджер, и она останется читаемой без нашего бэкенда.
"""

from __future__ import annotations

import csv
import html
import io
from datetime import datetime

from app import numbers
from app.schema import Dashboard, SessionView, Table

BOM = "﻿"


def _format(value: object, unit: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if unit == "percent":
            return f"{value:.2f}".replace(".", ",")
        if unit in ("rub", "qty", "count", "rank"):
            return f"{value:.2f}".replace(".", ",") if unit == "rub" else str(int(value))
    return str(value)


def to_csv(table: Table) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow([c.label for c in table.columns])
    for row in table.rows:
        writer.writerow([_format(row.get(c.field), c.unit) for c in table.columns])
    return BOM + buffer.getvalue()


def _kpi_html(dashboard: Dashboard) -> str:
    cards = []
    for card in dashboard.kpis:
        if card.value is None:
            text = "—"
        elif card.unit == "percent":
            text = numbers.signed_percent(card.value) if card.kind == "delta" else numbers.percent(card.value)
        elif card.unit == "rub":
            text = numbers.signed_money(card.value) if card.kind == "delta" else numbers.money(card.value)
        else:
            text = numbers.grouped(card.value)
        cards.append(
            f'<div class="kpi {html.escape(card.status)}">'
            f'<div class="kpi-label">{html.escape(card.label)}</div>'
            f'<div class="kpi-value">{html.escape(text)}</div>'
            f'<div class="kpi-hint">{html.escape(card.hint or "")}</div>'
            f"</div>"
        )
    return "".join(cards)


def _table_html(table: Table, limit: int = 200) -> str:
    head = "".join(
        f'<th class="{"num" if c.kind != "dimension" else ""}">{html.escape(c.label)}</th>'
        for c in table.columns
    )
    body = []
    for row in table.rows[:limit]:
        cells = "".join(
            f'<td class="{"num" if c.kind != "dimension" else ""}">'
            f"{html.escape(_display(row.get(c.field), c.unit))}</td>"
            for c in table.columns
        )
        body.append(f"<tr>{cells}</tr>")
    more = ""
    if table.row_count > limit:
        more = f'<p class="note">Показано {limit} строк из {table.row_count}.</p>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>{more}"


def _display(value: object, unit: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if unit == "percent":
            return numbers.percent(float(value))
        if unit == "rub":
            return numbers.money(float(value))
        return numbers.grouped(float(value))
    return str(value)


def to_html(view: SessionView) -> str:
    """Дашборд одной страницей: KPI, выводы, таблицы всех панелей.

    Графиков здесь нет намеренно — страница должна открываться без интернета
    и без нашего JS. Цифры в таблицах те же, что на графиках.
    """
    panels = []
    for panel in view.dashboard.panels:
        note = f'<p class="note">{html.escape(panel.note)}</p>' if panel.note else ""
        panels.append(
            f"<section><h3>{html.escape(panel.spec.title)}</h3>{note}"
            f"{_table_html(panel.table, 60)}</section>"
        )

    insights = "".join(f"<li>{html.escape(line)}</li>" for line in view.insights)
    notes = "".join(f'<p class="note">{html.escape(line)}</p>' for line in view.notes)
    filters = ", ".join(
        f"{option.label}: {', '.join(option.selected)}"
        for option in view.dashboard.filters
        if option.selected
    )

    return f"""<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(view.title)}</title>
<style>
  :root {{ color-scheme: light dark; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
           --surface:#fcfcfb; --plane:#f9f9f7; --grid:#e1e0d9; --border:rgba(11,11,11,.1);
           --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ink:#fff; --ink2:#c3c2b7; --muted:#898781; --surface:#1a1a19; --plane:#0d0d0d;
             --grid:#2c2c2a; --border:rgba(255,255,255,.1); }}
  }}
  body {{ margin:0; padding:24px 16px 48px; background:var(--plane); color:var(--ink);
          font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ font-size:22px; margin:0 0 4px; letter-spacing:-.01em; }}
  h3 {{ font-size:15px; margin:0 0 8px; }}
  .sub {{ color:var(--ink2); margin:0 0 20px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:24px; }}
  .kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:12px 14px; }}
  .kpi-label {{ color:var(--muted); font-size:12px; }}
  .kpi-value {{ font-size:20px; font-weight:650; font-variant-numeric:tabular-nums; margin-top:2px; }}
  .kpi-hint {{ color:var(--muted); font-size:11.5px; margin-top:2px; min-height:1em; }}
  .kpi.good .kpi-value {{ color:var(--good); }}
  .kpi.warning .kpi-value {{ color:var(--warning); }}
  .kpi.serious .kpi-value {{ color:var(--serious); }}
  .kpi.critical .kpi-value {{ color:var(--critical); }}
  section {{ background:var(--surface); border:1px solid var(--border); border-radius:12px;
             padding:14px 16px; margin-bottom:14px; overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ padding:7px 10px; text-align:left; border-bottom:1px solid var(--grid); white-space:nowrap; }}
  th {{ color:var(--muted); font-size:12px; font-weight:550; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .note {{ color:var(--ink2); font-size:12.5px; border-left:2px solid var(--grid);
           padding-left:10px; margin:8px 0 0; }}
  ul {{ margin:0 0 24px; padding-left:20px; color:var(--ink2); }}
  li {{ margin-bottom:6px; }}
</style>
<div class="wrap">
  <h1>{html.escape(view.title)}</h1>
  <p class="sub">{html.escape(view.question)}</p>
  <div class="kpis">{_kpi_html(view.dashboard)}</div>
  {f"<ul>{insights}</ul>" if insights else ""}
  {notes}
  {f'<p class="note">Фильтры: {html.escape(filters)}</p>' if filters else ""}
  {"".join(panels)}
  <p class="note">Выгружено {datetime.now():%d.%m.%Y %H:%M}. Данные — тестовый датасет кейса Puzzle RPA.</p>
</div>
</html>"""
