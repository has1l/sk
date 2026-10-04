import Plotly from "plotly.js-dist-min";
import { useEffect, useRef, useState } from "react";

import { compactMoney, count, money, percent, periodLabel, shortLabel } from "../format";
import { CATEGORICAL, CHROME, STATUS, currentMode, entityColor, metricColor, type Mode } from "../theme";
import type { ChartPanel, Row } from "../types";

const TEMPORAL = new Set(["month", "quarter", "year"]);

function useMode(): Mode {
  const [mode, setMode] = useState<Mode>(currentMode);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setMode(currentMode());
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  return mode;
}

/** Синхронный зум: панели с одинаковым zoom_group делят диапазон оси времени. */
type ZoomRange = [string, string] | null;

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
        : seriesPayload(rows, labels, fullLabels, spec, mode, chrome);

    // У круговой осей нет вовсе. Ключ со значением undefined — не то же самое,
    // что отсутствующий: Plotly лезет в layout.xaxis.anchor и падает.
    const layout = baseLayout(spec, chrome, mode, labels, height);
    if (spec.kind === "pie") {
      layout.showlegend = true;
    } else {
      applyScales(layout, spec, rows, unit, zoom);
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
    Plotly.react(element, data, layout, {
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "toImage"],
      scrollZoom: false,
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
            v === null ? colour : v >= (spec.reference as number) ? STATUS.good : STATUS.critical,
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
          size: byStatus ? 8 : 7,
          line: { color: chrome.surface, width: 2 },
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
      customdata: fullLabels.map((name, i) => [name, shown[i]]),
      hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]} · %{percent}<extra></extra>",
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

function baseLayout(
  spec: ChartPanel["spec"],
  chrome: Record<string, string>,
  mode: Mode,
  labels: string[],
  height: number,
) {
  const long = labels.some((l) => l.length > 12);
  const horizontal = spec.kind === "hbar";
  return {
    title: {
      text: spec.title,
      font: { size: 14, color: chrome.inkPrimary, family: "system-ui, -apple-system, sans-serif" },
      x: 0,
      xanchor: "left",
      pad: { b: 10 },
    },
    font: { family: "system-ui, -apple-system, sans-serif", size: 11.5, color: chrome.inkSecondary },
    paper_bgcolor: chrome.surface,
    plot_bgcolor: chrome.surface,
    margin: {
      l: horizontal ? Math.min(180, 8 * Math.max(...labels.map((l) => l.length), 8)) : 58,
      r: 14,
      t: 42,
      b: !horizontal && long ? 96 : 44,
    },
    height,
    barmode: spec.stacked ? "stack" : "group",
    bargap: 0.28,
    bargroupgap: 0.08,
    // Одна серия не нуждается в легенде: заголовок её уже называет.
    showlegend: spec.series.length >= 2,
    legend: {
      orientation: "h",
      y: -0.2,
      x: 0,
      font: { color: chrome.inkSecondary },
      bgcolor: "rgba(0,0,0,0)",
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
  zoom?: ZoomRange,
) {
  const horizontal = spec.kind === "hbar";
  const long = rows.length > 0 && spec.kind !== "hbar";

  const valueAxis: Record<string, unknown> = {
    title: { text: spec.y_label, font: { size: 10.5 }, standoff: 10 },
    gridwidth: 1,
    separatethousands: true,
    rangemode: unit === "percent" ? "normal" : "tozero",
    automargin: true,
    zeroline: true,
  };
  const categoryAxis: Record<string, unknown> = {
    title: { text: horizontal ? "" : spec.x_label, font: { size: 10.5 }, standoff: 10 },
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
