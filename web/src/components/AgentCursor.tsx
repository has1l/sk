import { useEffect, useRef, useState } from "react";

import type { Move } from "../agent";
import { Crawler } from "./Crawler";

/** Сколько курсор летит до цели и сколько «нажимает». */
const FLY = 620;
const PRESS = 260;

/** Куда по высоте видимой области ставить цель. Не середина: низ закрывает
 *  пристыкованный чат, и центрированная цель оказывается под ним. */
const EYE = 0.38;

/** Сколько ждём, пока цель вообще появится в разметке. Слой дашборда
 *  открывается с анимацией, и в первые кадры искать нечего. */
const WAIT_FOR_TARGET = 4000;

type Spot = { x: number; y: number; say: string };
/** Рамка вокруг цели. Рисуется курсором поверх, а не классом на самом
 *  элементе: шаг меняет состояние, React перерисовывает узел и переписывает
 *  className — подсветка, поставленная руками, исчезала бы сразу. */
type Ring = { x: number; y: number; w: number; h: number };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const frame = () => new Promise((r) => requestAnimationFrame(() => r(null)));

export function AgentCursor({ moves, onDone }: { moves: Move[]; onDone: () => void }) {
  const [spot, setSpot] = useState<Spot | null>(null);
  const [ring, setRing] = useState<Ring | null>(null);
  const [pressing, setPressing] = useState(false);
  // Долгий переход — только на подлёте. Дальше курсор держится за целью, и
  // те же 620 мс превратились бы в волочение следом за ней.
  const [flying, setFlying] = useState(false);
  const alive = useRef(true);
  const watching = useRef(0);

  /** Показ прерывается щелчком или Escape. Демонстрация, которую нельзя
   *  остановить, на защите превращается в заложничество: вопрос из зала
   *  приходит не вовремя. Признак на body — чтобы слой дашборда не закрылся
   *  той же клавишей; порядок обработчиков тут ненадёжен, все слушают окно. */
  useEffect(() => {
    document.body.dataset.showing = "1";
    const stop = () => {
      alive.current = false;
      onDone();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    window.addEventListener("pointerdown", stop);
    window.addEventListener("keydown", onKey);
    return () => {
      delete document.body.dataset.showing;
      window.removeEventListener("pointerdown", stop);
      window.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    alive.current = true;

    const pane = () => document.querySelector<HTMLElement>(".layer-body");

    /** Ждём появления цели: слой открывается с анимацией, и в первые кадры
     *  искать нечего. Раньше здесь стояла пауза на глаз — если дашборд не
     *  успевал, шаг молча пропускался, и курсора не было вовсе. */
    const find = async (selector: string): Promise<HTMLElement | null> => {
      const until = Date.now() + WAIT_FOR_TARGET;
      while (Date.now() < until) {
        if (!alive.current) return null;
        const node = document.querySelector<HTMLElement>(selector);
        if (node && node.getBoundingClientRect().height > 0) return node;
        await sleep(90);
      }
      return null;
    };

    /** Подводим цель к глазам: считаем сами, а не scrollIntoView, — нужно
     *  место под пристыкованный чат. */
    const bring = (node: HTMLElement) => {
      const box = node.getBoundingClientRect();
      const scroller = pane();
      if (!scroller) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      const view = scroller.getBoundingClientRect();
      const want = view.top + view.height * EYE;
      const shift = box.top + Math.min(box.height, 160) / 2 - want;
      if (Math.abs(shift) < 8) return;
      scroller.scrollTo({ top: scroller.scrollTop + shift, behavior: "smooth" });
    };

    /** Ждём, пока прокрутка встанет. Это и была вторая причина, по которой
     *  курсор улетал мимо: координаты замерялись на ходу, пока плавная
     *  прокрутка ещё шла. */
    const still = async () => {
      const scroller = pane();
      let last = NaN;
      let same = 0;
      for (let i = 0; i < 90; i++) {
        if (!alive.current) return;
        await frame();
        const now = scroller ? scroller.scrollTop : window.scrollY;
        if (now === last) {
          if (++same >= 3) return;
        } else {
          same = 0;
          last = now;
        }
      }
    };

    /** Курсор держится за цель, а не ставится один раз. Шаг меняет состояние,
     *  разметка перестраивается, элемент уезжает — без слежения подпись
     *  повисала бы в пустоте. */
    const watch = (selector: string, say: string) => {
      const tick = () => {
        if (!alive.current) return;
        const node = document.querySelector<HTMLElement>(selector);
        if (node) {
          const box = node.getBoundingClientRect();
          setRing({ x: box.left, y: box.top, w: box.width, h: box.height });
          setSpot({
            // Зверёк встаёт на верхнюю кромку у левого края, а не посреди
            // цели: сидя сверху он её не закрывает, и видно, что именно он
            // держит.
            x: box.left + Math.min(box.width * 0.22, 70),
            y: box.top,
            say,
          });
        }
        watching.current = requestAnimationFrame(tick);
      };
      cancelAnimationFrame(watching.current);
      tick();
    };

    const walk = async () => {
      for (const move of moves) {
        if (!alive.current) return;
        const node = await find(move.at);
        if (!node) continue;

        bring(node);
        await still();
        if (!alive.current) return;

        setFlying(true);
        watch(move.at, move.say);
        await sleep(FLY);
        setFlying(false);
        if (!alive.current) return;

        setPressing(true);
        await sleep(PRESS);
        setPressing(false);
        if (!alive.current) return;

        move.run?.();
        await sleep(move.hold ?? 700);
      }
      cancelAnimationFrame(watching.current);
      setRing(null);
      if (alive.current) onDone();
    };

    void walk();
    return () => {
      alive.current = false;
      cancelAnimationFrame(watching.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moves]);

  if (!spot) return null;

  return (
    <>
      {ring && (
        <div
          className={`agent-ring${flying ? " flying" : ""}`}
          aria-hidden="true"
          style={{
            transform: `translate3d(${ring.x}px, ${ring.y}px, 0)`,
            width: ring.w,
            height: ring.h,
          }}
        />
      )}
      <Crawler to={{ x: spot.x, y: spot.y }} holding={pressing || !flying} />
      {/* Подпись — строкой субтитров над пристыкованным чатом, а не пузырём у
          цели. Рядом с целью она закрывала соседние крутилки, над ней —
          заголовок и итоговые цифры: место у цели всегда чьё-то. */}
      <div className="agent-bubble" aria-live="polite">
        <span key={spot.say} className="agent-say">
          {spot.say}
        </span>
      </div>
    </>
  );
}
