import { useEffect, useState } from "react";

/** Имя зверька — одной константой: поменять надо будет в одном месте. */
export const PET_NAME = "Клодик";

/** Пиксельная сетка: рисуем целыми клетками, иначе манера рассыпается. */
const U = 3;
const px = (x: number, y: number, w: number, h: number) => ({
  x: x * U,
  y: y * U,
  width: w * U,
  height: h * U,
});

export type Mood = "calm" | "think" | "glad" | "hold" | "sorry" | "sixseven";

/** Цифры клетками, 3×5. Рисуем сами: шрифт рядом с пиксельным зверем выглядит
 *  чужеродно, да и полклетки в подпиксель всё равно не лягут. */
const DIGITS: Record<string, [number, number][]> = {
  "6": [[1,0],[2,0],[0,1],[0,2],[1,2],[2,2],[0,3],[2,3],[0,4],[1,4],[2,4]],
  "7": [[0,0],[1,0],[2,0],[2,1],[1,2],[1,3],[1,4]],
};

function digit(char: string, ox: number, oy: number) {
  return (DIGITS[char] ?? []).map(([x, y], i) => (
    <rect key={`${char}${i}`} {...px(ox + x * 0.9, oy + y * 0.9, 0.9, 0.9)} />
  ));
}

const SKIN_KEY = "puzzle.skin";

/** Шкурки. Каждая проверена на обеих темах: зверёк живёт и на кремовой
 *  бумаге, и на тёмном графите, поэтому крайние светлоты сюда не годятся. */
export const SKINS: { id: string; name: string; color: string }[] = [
  { id: "clay", name: "Терракота", color: "var(--accent-fill)" },
  { id: "indigo", name: "Индиго", color: "#5a56c4" },
  { id: "pine", name: "Хвоя", color: "#2f7a52" },
  { id: "plum", name: "Слива", color: "#9a4f9e" },
  { id: "graphite", name: "Графит", color: "#6b6760" },
];

export function storedSkin(): string {
  try {
    const raw = localStorage.getItem(SKIN_KEY);
    if (raw && SKINS.some((s) => s.id === raw)) return raw;
  } catch {
    /* приватный режим — берём обычную */
  }
  return SKINS[0].id;
}

export function saveSkin(id: string): void {
  try {
    localStorage.setItem(SKIN_KEY, id);
  } catch {
    /* не сохранилось — шкурка живёт до перезагрузки */
  }
  window.dispatchEvent(new CustomEvent("puzzle:skin"));
}

export function useSkin(): string {
  const [id, setId] = useState(storedSkin);
  useEffect(() => {
    const sync = () => setId(storedSkin());
    window.addEventListener("puzzle:skin", sync);
    return () => window.removeEventListener("puzzle:skin", sync);
  }, []);
  return SKINS.find((s) => s.id === id)?.color ?? SKINS[0].color;
}

/** Глаза задают настроение: тело одно и то же, меняется только лицо.
 *  Клетки, а не кривые — иначе выражение «плывёт» и перестаёт читаться. */
function face(mood: Mood) {
  switch (mood) {
    case "hold":
      // зажмурился от усилия: ><
      return [
        [4, 3.5], [5, 4.5], [4, 5.5],
        [11, 3.5], [10, 4.5], [11, 5.5],
      ];
    case "glad":
      // довольные дуги: ^ ^
      return [
        [4, 5], [5, 4], [6, 5],
        [10, 5], [11, 4], [12, 5],
      ];
    case "sorry":
      // ровные чёрточки: не получилось
      return [[4, 4.5], [5, 4.5], [10.5, 4.5], [11.5, 4.5]];
    case "think":
      // один глаз прищурен — думает
      return [[4, 3.5], [4, 4.5], [4, 5.5], [10, 4.5], [11, 4.5]];
    case "sixseven":
      // довольная морда: раз уж руками машет, пусть и радуется
      return [
        [4, 5], [5, 4], [6, 5],
        [10, 5], [11, 4], [12, 5],
      ];
    default:
      return null;
  }
}

/** Сам рисунок. Ни движения, ни положения — только поза и настроение, чтобы
 *  одного зверька можно было и водить по дашборду, и ставить аватаркой в
 *  переписку. */
export function PetArt({
  mood = "calm",
  step = () => 0,
  bob = 0,
  wave = 0,
  size = U,
  color,
}: {
  mood?: Mood;
  step?: (i: number) => number;
  bob?: number;
  /** Фаза маха руками: 0 и 1 чередуются. */
  wave?: number;
  size?: number;
  color?: string;
}) {
  const k = size / U;
  const eyes = face(mood);
  const crouch = mood === "hold";
  const swinging = mood === "sixseven";
  // Руки ходят навстречу друг другу, как весы.
  const leftArm = swinging ? (wave ? -2 : 1) : 0;
  const rightArm = swinging ? (wave ? 1 : -2) : 0;

  return (
    <svg
      width={16 * U * k}
      height={13 * U * k}
      viewBox={`0 0 ${16 * U} ${13 * U}`}
      shapeRendering="crispEdges"
      overflow="visible"
      aria-hidden="true"
    >
      <g transform={`translate(0 ${bob * U})`} fill={color ?? "var(--accent-fill)"}>
        {[2, 5.5, 9, 12.5].map((x, i) => (
          <rect key={x} {...px(x, 8 + step(i) * 0.5, 1.5, crouch ? 2.5 : 3)} />
        ))}
        {crouch && (
          <>
            <rect {...px(0.5, 9.5, 1.5, 1.5)} />
            <rect {...px(14, 9.5, 1.5, 1.5)} />
          </>
        )}
        <rect {...px(0.5, 4 + leftArm, 1.5, 2)} />
        <rect {...px(14, 4 + rightArm, 1.5, 2)} />
        <rect {...px(2, 1, 12, 7.5)} />
        {/* Цифры висят над руками и ездят вместе с ними. Нарисованы за
            пределами viewBox — отсюда overflow: visible. */}
        {swinging && digit("6", -3.2, 1.2 + leftArm)}
        {swinging && digit("7", 16.6, 1.2 + rightArm)}
      </g>

      <g transform={`translate(0 ${bob * U})`} fill="var(--paper)">
        {eyes ? (
          eyes.map(([x, y], i) => <rect key={i} {...px(x, y, 1, 1)} />)
        ) : (
          <>
            <rect {...px(4, 3.5, 2, 2.5)} />
            <rect {...px(10, 3.5, 2, 2.5)} />
          </>
        )}
      </g>
    </svg>
  );
}

/** Зверёк рядом с репликой бота. Щелчок перебирает шкурки — мелочь, но она
 *  делает его «своим», а узнать про неё можно из подсказки. */
export function PetAvatar({ mood = "calm" }: { mood?: Mood }) {
  const color = useSkin();
  const [beat, setBeat] = useState(0);

  // Думающий зверёк покачивается, машущий — машет. Статичная картинка рядом с
  // «смотрю данные» выглядит как зависший интерфейс.
  useEffect(() => {
    if (mood !== "think" && mood !== "sixseven") {
      setBeat(0);
      return;
    }
    const id = setInterval(() => setBeat((v) => (v === 0 ? 1 : 0)), mood === "sixseven" ? 320 : 420);
    return () => clearInterval(id);
  }, [mood]);

  const next = () => {
    const at = SKINS.findIndex((s) => s.id === storedSkin());
    const picked = SKINS[(at + 1) % SKINS.length];
    saveSkin(picked.id);
  };

  return (
    <button
      className="pet"
      onClick={next}
      title={`${PET_NAME} — щёлкните, чтобы сменить цвет`}
      aria-label={`Сменить цвет: ${PET_NAME}`}
    >
      <PetArt
        mood={mood}
        bob={mood === "think" ? -beat : 0}
        wave={beat}
        size={1.6}
        color={color}
      />
    </button>
  );
}
