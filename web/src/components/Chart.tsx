import Plotly from "plotly.js-dist-min";
import { useEffect, useRef, useState } from "react";

import { compactMoney, count, money, percent, periodLabel, shortLabel, signedMoney } from "../format";
import {
  CATEGORICAL,
  CHROME,
  STATUS_BY_MODE,
  THEME_EVENT,
  currentMode,
  entityColor,
  metricColor,
  type Mode,
} from "../theme";
import type { ChartPanel, Row } from "../types";

const TEMPORAL = new Set(["month", "quarter", "year"]);

/** Те же шрифты, что и в интерфейсе. Plotly рисует в SVG и системный шрифт
 *  оттуда не наследует — семейство приходится называть явно, иначе график
 *  набран не тем, чем страница вокруг. */
const CHART_FONT = '"Inter", system-ui, -apple-system, sans-serif';

/** Сколько точек ряд несёт, не сливаясь. Дальше маркеры жмутся и обводка
 *  снимается: на тридцати трёх точках белые ободки превращают линию в
 *  пунктир из бусин. */
const DENSE_POINTS = 16;

function useMode(): Mode {
  const [mode, setMode] = useState<Mode>(currentMode);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setMode(currentMode());
    media.addEventListener("change", sync);
    window.addEventListener(THEME_EVENT, sync);
    return () => {
      media.removeEventListener("change", sync);
      window.removeEventListener(THEME_EVENT, sync);
    };
  }, []);
  return mode;
}

/** Синхронный зум: панели с одинаковым zoom_group делят диапазон оси времени. */
type ZoomRange = [string, string] | null;

/** Все значения пустые — рисовать нечего. Голые оси без единого столбца
 *  читаются как поломка, поэтому вместо графика показывается объяснение. Текст
 *  приходит с сервера: там же, где решают, что считать.
 *
 *  Признак нужен и дашборду — чтобы не напечатать то же примечание второй раз
 *  под панелью. */
export function isBlank(panel: ChartPanel): boolean {
  return (
    panel.spec.kind !== "pie" &&
    panel.table.rows.length > 0 &&
    panel.spec.series.every((series) =>
      panel.table.rows.every(
        (row) => row[series.field] === null || row[series.field] === undefined,
      ),
    )
  );
}

export function Chart({
  panel,
  zoom,
  onZoom,
  height = 320,
}: {
  panel: ChartPanel;
  zoom?: ZoomRange;
  onZoom?: (group: string, range: ZoomRange) => void;
  height?: number;
}) {
  const node = useRef<HTMLDivElement>(null);
  const mode = useMode();
  const { spec, table } = panel;

  useEffect(() => {
    const element = node.current;
    if (!element) return;

    const chrome = CHROME[mode];
    const temporal = TEMPORAL.has(spec.x_field);
    const rows = spec.kind === "hbar" ? [...table.rows].reverse() : table.rows;

    const labels = rows.map((row) => {
      const raw = row[spec.x_field];
      if (typeof raw === "string" && temporal) return periodLabel(raw, spec.x_field);
      return shortLabel(String(raw ?? "—"));
    });
    const fullLabels = rows.map((row) => String(row[spec.x_field] ?? "—"));

    const unit = spec.series[0]?.unit ?? "none";
    const data =
      spec.kind === "pie"
        ? piePayload(rows, labels, fullLabels, spec, mode, chrome)
        : spec.kind === "waterfall"
          ? waterfallPayload(rows, labels, fullLabels, spec, mode, chrome)
          : seriesPayload(rows, labels, fullLabels, spec, mode, chrome);

    // У круговой осей нет вовсе. Ключ со значением undefined — не то же самое,
    // что отсутствующий: Plotly лезет в layout.xaxis.anchor и падает.
    const layout = baseLayout(spec, chrome, mode, labels, height);
    if (spec.kind === "pie") {
      layout.showlegend = true;
    } else if (spec.kind === "waterfall") {
      applyBridgeScales(layout, spec, rows, labels);
    } else {
      applyScales(layout, spec, rows, unit, temporal, zoom);
    }

    const group = spec.zoom_group;
    const handler = (event: Record<string, unknown>) => {
      if (!group || !onZoom) return;
      const from = event["xaxis.range[0]"];
      const to = event["xaxis.range[1]"];
      if (typeof from === "string" && typeof to === "string") onZoom(group, [from, to]);
      if (event["xaxis.autorange"]) onZoom(group, null);
    };

    let alive = true;
    // Подписка только после того, как Plotly создал график: метод .on
    // появляется на элементе вместе с ним, а не до него.
    // Панель Plotly убрана целиком. Её подписи приходят из библиотеки на
    // английском («Pan», «Reset axes»), а русская локаль в `dist-min` не
    // входит — в русском интерфейсе это чужая деталь. Из восьми её кнопок
    // руководителю нужен только зум, а он и так работает: выделить мышью —
    // приблизить, двойной щелчок — вернуть.
    Plotly.react(element, data, layout, {
      displaylogo: false,
      displayModeBar: false,
      responsive: true,
      scrollZoom: false,
      doubleClick: "reset",
    }).then((graph) => {
      if (!alive || !group || !onZoom) return;
      (graph as unknown as { on?: (e: string, h: typeof handler) => void }).on?.(
        "plotly_relayout",
        handler,
      );
    });

    const observer = new ResizeObserver(() => Plotly.Plots.resize(element));
    observer.observe(element);
    return () => {
      alive = false;
      observer.disconnect();
      Plotly.purge(element);
    };
  }, [spec, table, mode, zoom, height, onZoom]);

  if (isBlank(panel)) {
    return (
      <div className="chart chart-blank" style={{ height: Math.min(height, 200) }}>
        <p>{panel.note ?? "Для этой панели пока нечего показать."}</p>
      </div>
    );
  }

  return <div className="chart" style={{ height }} ref={node} />;
}

function formatter(unit: string) {
  if (unit === "rub") return money;
  if (unit === "percent") return (v: number) => percent(v);
  if (unit === "rank") return (v: number) => String(Math.round(v));
  return count;
}

function seriesPayload(
  rows: Row[],
  labels: string[],
  fullLabels: string[],
  spec: ChartPanel["spec"],
  mode: Mode,
  chrome: Record<string, string>,
) {
  const horizontal = spec.kind === "hbar";
  const status = STATUS_BY_MODE[mode];
  const dense = rows.length > DENSE_POINTS;
  return spec.series.map((series, index) => {
    const colour = metricColor(series.field, mode, index);
    const values = rows.map((row) => {
      const raw = row[series.field];
      return raw === null || raw === undefined ? null : Number(raw);
    });
    const shown = values.map((v) => (v === null ? "—" : formatter(series.unit)(v)));
    const hover = `<b>%{customdata[0]}</b><br>${series.label}: %{customdata[1]}<extra></extra>`;
    const customdata = fullLabels.map((name, i) => [name, shown[i]]);

    // Зоны пере- и недовыполнения кодируются цветом самой точки относительно
    // черты, а не заливкой фона: при сплошном недовыполнении фоновая зона
    // закрашивает весь график и перестаёт что-либо означать.
    const byStatus =
      spec.reference === null
        ? null
        : values.map((v) =>
            v === null ? colour : v >= (spec.reference as number) ? status.good : status.critical,
          );

    if (spec.kind === "line" || spec.kind === "area") {
      return {
        type: "scatter",
        mode: "lines+markers",
        name: series.label,
        x: labels,
        y: values,
        customdata,
        hovertemplate: hover,
        connectgaps: false,
        fill: spec.kind === "area" ? "tozeroy" : undefined,
        line: { color: colour, width: 2, shape: "linear" },
        marker: {
          color: byStatus ?? colour,
          size: dense ? 5 : byStatus ? 8 : 7,
          line: { color: chrome.surface, width: dense ? 0 : 2 },
        },
      };
    }
    return {
      type: "bar",
      name: series.label,
      orientation: horizontal ? "h" : "v",
      x: horizontal ? values : labels,
      y: horizontal ? labels : values,
      customdata,
      hovertemplate: hover,
      marker: {
        color: byStatus ?? colour,
        cornerradius: 4,
        line: { color: chrome.surface, width: 1.5 },
      },
    };
  });
}

function piePayload(
  rows: Row[],
  labels: string[],
  fullLabels: string[],
  spec: ChartPanel["spec"],
  mode: Mode,
  chrome: Record<string, string>,
) {
  const series = spec.series[0];
  const values = rows.map((row) => Number(row[series.field] ?? 0));
  const shown = values.map((v) => formatter(series.unit)(v));
  return [
    {
      type: "pie",
      labels,
      values,
      // Круговая не разбирает двумерный customdata: %{customdata[1]} уходит в
      // подсказку сырым шаблоном. Имя — одномерным customdata, сумма — в text.
      customdata: fullLabels,
      text: shown,
      hovertemplate: "<b>%{customdata}</b><br>%{text} · %{percent}<extra></extra>",
      textinfo: "percent",
      texttemplate: "%{percent:.0%}",
      textposition: "inside",
      insidetextorientation: "horizontal",
      hole: 0.52,
      sort: false,
      direction: "clockwise",
      marker: {
        colors: fullLabels.map((name) => entityColor(name, mode, fullLabels)),
        line: { color: chrome.surface, width: 2 },
      },
    },
  ];
}

/** Мост от плана к факту.
 *
 *  Ступенька вниз красная, вверх зелёная, опоры — план и факт. Ось намеренно
 *  не начинается с нуля: на шкале в миллиард вклад в двадцать миллионов
 *  становится невидимой чертой, и мост перестаёт что-либо объяснять. */
function waterfallPayload(
  rows: Row[],
  labels: string[],
  fullLabels: string[],
  spec: ChartPanel["spec"],
  mode: Mode,
  chrome: Record<string, string>,
) {
  const status = STATUS_BY_MODE[mode];
  const values = rows.map((row) => Number(row.value ?? 0));
  const measures = rows.map((row) => String(row.measure ?? "relative"));
  const shown = values.map((value, index) =>
    measures[index] === "relative" ? signedMoney(value) : money(value),
  );
  return [
    {
      type: "waterfall",
      orientation: "v",
      measure: measures,
      x: labels,
      y: values,
      text: shown,
      textposition: "outside",
      textfont: { size: 10.5, color: chrome.inkSecondary },
      customdata: fullLabels.map((name, index) => [name, shown[index]]),
      hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
      cliponaxis: false,
      decreasing: { marker: { color: status.critical } },
      increasing: { marker: { color: status.good } },
      totals: { marker: { color: chrome.inkMuted } },
      connector: { line: { color: chrome.grid, width: 1, dash: "dot" } },
    },
  ];
}

function applyBridgeScales(
  layout: Record<string, any>,
  spec: ChartPanel["spec"],
  rows: Row[],
  labels: string[],
) {
  const values = rows.map((row) => Number(row.value ?? 0));
  const measures = rows.map((row) => String(row.measure ?? "relative"));

  // Видимый диапазон — по накопленным уровням моста, а не по величине ступенек.
  const levels: number[] = [];
  let running = 0;
  values.forEach((value, index) => {
    running = measures[index] === "relative" ? running + value : value;
    levels.push(running);
  });

  const low = Math.min(...levels);
  const high = Math.max(...levels);
  const pad = Math.max((high - low) * 0.25, 1);
  const from = low - pad;
  const to = high + pad;
  const ticks = Array.from({ length: 5 }, (_, i) => from + ((to - from) * i) / 4);

  layout.xaxis = {
    title: { text: spec.x_label, font: { size: 10.5 }, standoff: 10 },
    showgrid: false,
    zeroline: false,
    automargin: true,
    tickangle: labels.some((l) => l.length > 10) ? -35 : 0,
    type: "category",
  };
  layout.yaxis = {
    title: { text: spec.y_label, font: { size: 10.5 }, standoff: 10 },
    gridwidth: 1,
    range: [from, to],
    tickmode: "array",
    tickvals: ticks,
    ticktext: ticks.map((value) => compactMoney(value)),
    automargin: true,
    zeroline: false,
  };
  layout.showlegend = false;
}

function baseLayout(
  spec: ChartPanel["spec"],
  chrome: Record<string, string>,
  mode: Mode,
  labels: string[],
  height: number,
) {
  const long = labels.some((l) => l.length > 12);
  const horizontal = spec.kind === "hbar";
  const pie = spec.kind === "pie";
  const legend = pie || spec.series.length >= 2;
  // Подписи категорий на вертикальных графиках всегда наклонены (см.
  // applyScales), и низ занят ими. Поэтому легенда уходит наверх, под
  // заголовок, — внизу ей места нет ни при каком отступе. У круговой наоборот:
  // подписей оси нет, и низ свободен.
  const bottom = pie ? 118 : !horizontal && long ? 96 : 56;
  // Заголовка внутри графика нет: его несёт шапка ячейки, за которую панель и
  // таскают. Два одинаковых заголовка друг под другом — это не акцент, это
  // потерянная строка и лишние шестьдесят пикселей высоты.
  return {
    font: { family: CHART_FONT, size: 12, color: chrome.inkSecondary },
    separators: ", ",
    paper_bgcolor: chrome.surface,
    plot_bgcolor: chrome.surface,
    margin: {
      l: pie ? 14 : horizontal ? Math.min(180, 8 * Math.max(...labels.map((l) => l.length), 8)) : 58,
      r: 14,
      t: legend && !pie ? 34 : 12,
      b: bottom,
    },
    height,
    barmode: spec.stacked ? "stack" : "group",
    bargap: 0.28,
    bargroupgap: 0.08,
    // Одна серия не нуждается в легенде: заголовок её уже называет.
    showlegend: legend,
    legend: {
      orientation: "h",
      y: pie ? -0.04 : 1.04,
      yanchor: pie ? "top" : "bottom",
      x: 0,
      font: { color: chrome.inkSecondary, size: 11 },
      bgcolor: "rgba(0,0,0,0)",
      itemclick: "toggle",
    },
    hoverlabel: {
      bgcolor: chrome.surface,
      bordercolor: chrome.border,
      font: { color: chrome.inkPrimary, size: 12 },
    },
    hovermode: spec.kind === "line" ? ("x unified" as const) : ("closest" as const),
    colorway: CATEGORICAL[mode],
    shapes: [] as Record<string, unknown>[],
  };
}

function applyScales(
  layout: Record<string, any>,
  spec: ChartPanel["spec"],
  rows: Row[],
  unit: string,
  temporal: boolean,
  zoom?: ZoomRange,
) {
  const horizontal = spec.kind === "hbar";
  const long = rows.length > 0 && spec.kind !== "hbar";

  // Столбец обязан начинаться с нуля: его длина и есть величина, обрезанная ось
  // врёт о соотношении. У линии величину несёт положение точки, а не длина, и
  // ноль ей не нужен: на шкале от нуля до 25 млн разрыв плана и факта в два
  // миллиона схлопывается в толщину линии — пропадает ровно то, ради чего
  // график рисуют. Заливка исключена: она тянется к нулю и без него разъедется.
  const breathes = spec.kind === "line" && unit !== "percent";
  const valueAxis: Record<string, unknown> = {
    title: { text: spec.y_label, font: { size: 10.5 }, standoff: 10 },
    gridwidth: 1,
    separatethousands: true,
    rangemode: unit === "percent" || breathes ? "normal" : "tozero",
    automargin: true,
    zeroline: !breathes,
  };
  const categoryAxis: Record<string, unknown> = {
    // Подпись «Месяц» под делениями «янв 2024» ничего не добавляет, а место
    // отнимает. У осей с названиями регионов или точек подпись остаётся.
    title: { text: horizontal || temporal ? "" : spec.x_label, font: { size: 10.5 }, standoff: 10 },
    showgrid: false,
    zeroline: false,
    automargin: true,
    tickangle: long && !horizontal ? -35 : 0,
    type: "category",
  };

  const numbers = spec.series.flatMap((s) =>
    rows.map((r) => Number(r[s.field] ?? Number.NaN)).filter((v) => !Number.isNaN(v)),
  );
  if (unit === "rub" && numbers.length) {
    const top = Math.max(...numbers, 0);
    const step = top / 5;
    const vals = Array.from({ length: 6 }, (_, i) => i * step);
    Object.assign(valueAxis, {
      tickmode: "array",
      tickvals: vals,
      ticktext: vals.map((v) => compactMoney(v)),
    });
  } else if (unit === "percent") {
    Object.assign(valueAxis, { ticksuffix: "%" });
  } else {
    Object.assign(valueAxis, { tickformat: ",d" });
  }

  if (breathes && numbers.length && spec.reference === null) {
    const low = Math.min(...numbers);
    const high = Math.max(...numbers);
    const pad = Math.max((high - low) * 0.18, Math.abs(high) * 0.02, 1);
    Object.assign(valueAxis, { range: [low - pad, high + pad] });
    const step = (high + pad - (low - pad)) / 5;
    const vals = Array.from({ length: 6 }, (_, i) => low - pad + i * step);
    Object.assign(valueAxis, {
      tickmode: "array",
      tickvals: vals,
      ticktext: vals.map((v) => (unit === "rub" ? compactMoney(v) : String(Math.round(v)))),
    });
  }

  layout.xaxis = horizontal ? valueAxis : categoryAxis;
  layout.yaxis = horizontal ? categoryAxis : valueAxis;

  // Отметка 100% и зоны пере/недовыполнения — прямое требование кейса.
  // Диапазон оси раздвигается за черту: иначе при сплошном недовыполнении
  // красная зона занимает весь график и читается как сбой, а не как смысл.
  if (spec.reference !== null && numbers.length) {
    const low = Math.min(...numbers, spec.reference);
    const high = Math.max(...numbers, spec.reference);
    const pad = Math.max((high - low) * 0.12, Math.abs(spec.reference) * 0.01, 1);
    Object.assign(valueAxis, { range: [low - pad, high + pad], rangemode: "normal" });
    layout.shapes = [
      {
        type: "line",
        xref: horizontal ? "x" : "paper",
        yref: horizontal ? "paper" : "y",
        x0: horizontal ? spec.reference : 0,
        x1: horizontal ? spec.reference : 1,
        y0: horizontal ? 0 : spec.reference,
        y1: horizontal ? 1 : spec.reference,
        line: { color: "rgba(137,135,129,0.9)", width: 1, dash: "dash" },
        layer: "above",
      },
    ];
  }

  if (spec.zoom_group && zoom) {
    (layout.xaxis as Record<string, unknown>).range = zoom;
  }
}
