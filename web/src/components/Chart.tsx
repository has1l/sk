import Plotly from "plotly.js-dist-min";
import { useEffect, useRef, useState } from "react";

import { compactMoney, count, money, periodLabel } from "../format";
import { CATEGORICAL, CHROME, currentMode, metricColor, type Mode } from "../theme";
import type { ChartSpec, Table } from "../types";

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

export function Chart({ spec, table }: { spec: ChartSpec; table: Table }) {
  const node = useRef<HTMLDivElement>(null);
  const mode = useMode();

  useEffect(() => {
    const element = node.current;
    if (!element) return;

    const chrome = CHROME[mode];
    const temporal = TEMPORAL.has(spec.x_field);
    const unit = table.columns.find((c) => c.kind === "metric")?.unit ?? "none";
    const asMoney = unit === "rub";

    const labels = table.rows.map((row) => {
      const raw = row[spec.x_field];
      if (typeof raw === "string" && temporal) return periodLabel(raw, spec.x_field);
      return String(raw ?? "—");
    });

    // Одна серия не нуждается в легенде: заголовок её уже называет.
    const showLegend = spec.series.length >= 2;

    const data = spec.series.map((series, index) => {
      const colour = metricColor(series.field, mode, index);
      const values = table.rows.map((row) => Number(row[series.field] ?? 0));
      const formatted = values.map((v) => (asMoney ? money(v) : count(v)));
      const hover =
        `<b>%{x}</b><br>${series.label}: %{customdata}<extra></extra>`;

      if (spec.kind === "line") {
        return {
          type: "scatter",
          mode: "lines+markers",
          name: series.label,
          x: labels,
          y: values,
          customdata: formatted,
          hovertemplate: hover,
          line: { color: colour, width: 2, shape: "linear" },
          marker: { color: colour, size: 8, line: { color: chrome.surface, width: 2 } },
        };
      }
      return {
        type: "bar",
        name: series.label,
        x: labels,
        y: values,
        customdata: formatted,
        hovertemplate: hover,
        marker: {
          color: colour,
          cornerradius: 4,
          line: { color: chrome.surface, width: 2 },
        },
      };
    });

    const layout = {
      title: {
        text: spec.title,
        font: { size: 15, color: chrome.inkPrimary, family: "system-ui, -apple-system, sans-serif" },
        x: 0,
        xanchor: "left",
        pad: { b: 12 },
      },
      font: { family: "system-ui, -apple-system, sans-serif", size: 12, color: chrome.inkSecondary },
      paper_bgcolor: chrome.surface,
      plot_bgcolor: chrome.surface,
      margin: { l: 64, r: 16, t: 48, b: labels.some((l) => l.length > 12) ? 110 : 56 },
      barmode: spec.stacked ? "stack" : "group",
      bargap: 0.3,
      bargroupgap: 0.08,
      showlegend: showLegend,
      legend: {
        orientation: "h",
        y: -0.22,
        x: 0,
        font: { color: chrome.inkSecondary },
        bgcolor: "rgba(0,0,0,0)",
      },
      xaxis: {
        title: { text: spec.x_label, font: { color: chrome.inkMuted, size: 11 }, standoff: 12 },
        tickfont: { color: chrome.inkMuted, size: 11 },
        tickangle: labels.some((l) => l.length > 12) ? -35 : 0,
        showgrid: false,
        zeroline: false,
        linecolor: chrome.baseline,
        automargin: true,
      },
      yaxis: {
        title: { text: spec.y_label, font: { color: chrome.inkMuted, size: 11 }, standoff: 12 },
        tickfont: { color: chrome.inkMuted, size: 11 },
        tickformat: asMoney ? undefined : ",d",
        tickprefix: "",
        gridcolor: chrome.grid,
        gridwidth: 1,
        zerolinecolor: chrome.baseline,
        separatethousands: true,
        rangemode: "tozero",
        automargin: true,
        ...(asMoney
          ? {
              tickmode: "auto" as const,
              nticks: 6,
            }
          : {}),
      },
      hoverlabel: {
        bgcolor: chrome.surface,
        bordercolor: chrome.border,
        font: { color: chrome.inkPrimary, size: 12 },
      },
      hovermode: spec.kind === "line" ? "x unified" : "closest",
      colorway: CATEGORICAL[mode],
    };

    if (asMoney) {
      const all = spec.series.flatMap((s) => table.rows.map((r) => Number(r[s.field] ?? 0)));
      const top = Math.max(...all, 0);
      const ticks = 5;
      const step = top / ticks;
      const vals = Array.from({ length: ticks + 1 }, (_, i) => i * step);
      Object.assign(layout.yaxis, {
        tickmode: "array",
        tickvals: vals,
        ticktext: vals.map((v) => compactMoney(v)),
      });
    }

    Plotly.react(element, data, layout, {
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toImage"],
      scrollZoom: false,
    });

    const observer = new ResizeObserver(() => Plotly.Plots.resize(element));
    observer.observe(element);
    return () => {
      observer.disconnect();
      Plotly.purge(element);
    };
  }, [spec, table, mode]);

  return <div className="chart" ref={node} />;
}
