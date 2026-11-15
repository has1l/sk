import { useEffect, useRef, useState } from "react";

import { PetArt, useSkin } from "./Pet";

/** Сколько тянется к цели за кадр: больше — резче, меньше — вальяжнее. */
const EASE = 0.13;
/** Скорость, с которой уже считается, что зверёк идёт, а не стоит. */
const WALKING = 0.35;

type Pose = { x: number; y: number; vx: number; vy: number; t: number };

/** Зверёк, который ходит по дашборду и цепляется за то, что настраивает.
 *
 *  Положение считается здесь, а не отдаётся CSS-переходу: походке нужна
 *  скорость. С переходом тело знало бы только «куда», но не «как быстро», и
 *  лапки не переставлялись бы.
 *
 *  Персонаж свой. Пиксельная манера общая, но конкретного чужого талисмана в
 *  продукте заказчика быть не должно.
 */
export function Crawler({ to, holding }: { to: { x: number; y: number }; holding: boolean }) {
  const skin = useSkin();
  const [pose, setPose] = useState<Pose>({ x: to.x, y: to.y, vx: 0, vy: 0, t: 0 });
  const live = useRef(pose);
  const aim = useRef(to);
  const frame = useRef(0);

  aim.current = to;

  useEffect(() => {
    const tick = () => {
      const p = live.current;
      const dx = (aim.current.x - p.x) * EASE;
      const dy = (aim.current.y - p.y) * EASE;
      const speed = Math.hypot(dx, dy);
      const next: Pose = {
        x: p.x + dx,
        y: p.y + dy,
        vx: p.vx * 0.75 + dx * 0.25,
        vy: p.vy * 0.75 + dy * 0.25,
        // Шаг идёт от пройденного пути, а не от времени: стоящий зверёк не
        // перебирает лапками на месте.
        t: p.t + Math.min(speed * 0.12, 0.6),
      };
      live.current = next;
      setPose(next);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, []);

  const speed = Math.hypot(pose.vx, pose.vy);
  const walking = speed > WALKING && !holding;
  const facing = pose.vx < -0.4 ? -1 : 1;
  const step = (i: number) => (walking && Math.sin(pose.t * 2 + i * 1.6) > 0 ? -1 : 0);
  // Пока идёт — тело покачивается на клетку; в захвате приседает.
  const bob = holding ? 1 : walking && Math.sin(pose.t * 4) > 0 ? -1 : 0;

  return (
    <div
      className={`crawler${holding ? " holding" : ""}`}
      style={{ transform: `translate3d(${pose.x}px, ${pose.y}px, 0) scaleX(${facing})` }}
      aria-hidden="true"
    >
      <PetArt mood={holding ? "hold" : "calm"} step={step} bob={bob} color={skin} />
    </div>
  );
}
