/** Дашборд картинкой.
 *
 *  Кейс просит скачивание изображением. Собирается на клиенте: графики уже
 *  нарисованы Plotly, и просить сервер рисовать их заново — это второй
 *  рисовальщик, который разойдётся с первым.
 */
import Plotly from "plotly.js-dist-min";

import { kpiValue } from "./format";
import { CHROME, currentMode } from "./theme";
import type { Kpi } from "./types";

const GAP = 28;
const PAD = 32;

export async function downloadPicture(title: string, question: string, kpis: Kpi[]) {
  // Берём то, что на экране: у склеенной коробки нарисована только открытая
  // вкладка, и в картинку попадает именно она. Заголовок панели живёт в шапке
  // ячейки, а не внутри графика, — поэтому его подписываем сами.
  const boxes = Array.from(document.querySelectorAll<HTMLElement>(".grid .slot"))
    .map((slot) => ({
      node: slot.querySelector<HTMLDivElement>(".chart"),
      caption:
        slot.querySelector(".slot-tabs button.on")?.textContent?.trim() ||
        slot.querySelector(".slot-title")?.textContent?.trim() ||
        "",
    }))
    .filter((box): box is { node: HTMLDivElement; caption: string } => box.node !== null);
  if (boxes.length === 0) return;

  const chrome = CHROME[currentMode()];
  const shots = await Promise.all(
    boxes.map((box) =>
      Plotly.toImage(box.node, {
        format: "png",
        width: box.node.clientWidth,
        height: box.node.clientHeight,
        scale: 2,
      }),
    ),
  );
  const images = await Promise.all(shots.map(load));

  const CAPTION = 42;
  const width = Math.max(...images.map((image) => image.width)) + PAD * 2;
  const head = 150;
  const height =
    head + images.reduce((sum, image) => sum + image.height + CAPTION + GAP, 0) + PAD;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.fillStyle = chrome.plane;
  ctx.fillRect(0, 0, width, height);

  // Те же шрифты, что в интерфейсе: картинка уходит в переписку и в отчёт,
  // и набранная чужой гарнитурой она выглядит скриншотом другого продукта.
  const family = '"Inter", system-ui, -apple-system, sans-serif';
  const serif = '"Source Serif", Georgia, serif';
  ctx.fillStyle = chrome.inkPrimary;
  ctx.font = `600 34px ${serif}`;
  ctx.fillText(title, PAD, 58);

  ctx.fillStyle = chrome.inkSecondary;
  ctx.font = `22px ${family}`;
  ctx.fillText(clip(ctx, question, width - PAD * 2), PAD, 94);

  const line = kpis
    .map((kpi) => `${kpi.label}: ${kpiValue(kpi.value, kpi.unit, kpi.kind)}`)
    .join("   ·   ");
  ctx.fillStyle = chrome.inkPrimary;
  ctx.font = `550 20px ${family}`;
  ctx.fillText(clip(ctx, line, width - PAD * 2), PAD, 130);

  let y = head;
  images.forEach((image, index) => {
    ctx.fillStyle = chrome.inkPrimary;
    ctx.font = `600 26px ${serif}`;
    ctx.fillText(clip(ctx, boxes[index].caption, width - PAD * 2), PAD, y + 26);
    y += CAPTION;
    ctx.drawImage(image, PAD, y, image.width, image.height);
    y += image.height + GAP;
  });

  const link = document.createElement("a");
  link.download = `${safe(title)}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function load(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
}

function clip(ctx: CanvasRenderingContext2D, text: string, limit: number): string {
  if (ctx.measureText(text).width <= limit) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > limit) cut = cut.slice(0, -1);
  return `${cut}…`;
}

/** Имя файла. Неразрывные пробелы из русских чисел и запятые из заголовка
 *  превращались в частокол подчёркиваний — сначала приводим к обычным
 *  пробелам, и только потом выбрасываем то, что файловой системе не нравится. */
function safe(title: string): string {
  return (
    title
      .replace(/[\u00a0\u202f]/g, " ")
      .replace(/[^\p{L}\p{N} _-]/gu, " ")
      .replace(/\s+/g, " ")
      .trim() || "dashboard"
  );
}
