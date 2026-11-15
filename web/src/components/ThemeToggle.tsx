import { useEffect, useState } from "react";

import { THEME_EVENT, applyTheme, currentMode, storedTheme, type ThemeChoice } from "../theme";

/** Переключатель темы на три положения. «Авто» — состояние по умолчанию и
 *  честное: тема следует за системой, пока её не трогали. */
const ORDER: ThemeChoice[] = ["system", "light", "dark"];

const TITLE: Record<ThemeChoice, string> = {
  system: "Тема: как в системе",
  light: "Тема: светлая",
  dark: "Тема: тёмная",
};

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme);
  const [mode, setMode] = useState(currentMode);

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

  const next = () => {
    const picked = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
    setChoice(picked);
    applyTheme(picked);
  };

  return (
    <button className="theme-toggle" onClick={next} title={TITLE[choice]} aria-label={TITLE[choice]}>
      {choice === "system" ? <Auto /> : mode === "dark" ? <Moon /> : <Sun />}
    </button>
  );
}

function Sun() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M8 1.4v1.5M8 13.1v1.5M14.6 8h-1.5M2.9 8H1.4M12.67 3.33l-1.06 1.06M4.39 11.61l-1.06 1.06M12.67 12.67l-1.06-1.06M4.39 4.39 3.33 3.33"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
      <path
        d="M13.5 9.6A5.8 5.8 0 0 1 6.4 2.5a5.8 5.8 0 1 0 7.1 7.1Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Auto() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="5.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 2.4A5.6 5.6 0 0 1 8 13.6Z" fill="currentColor" />
    </svg>
  );
}
