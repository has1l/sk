import { useEffect, useRef, useState } from "react";

import { ask } from "./api";
import { Answer } from "./components/Answer";
import { Composer } from "./components/Composer";
import type { ChatTurn } from "./types";

export default function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const busy = turns.some((t) => t.state === "pending");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const send = async (question: string) => {
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, question, state: "pending" }]);
    try {
      const answer = await ask(question);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "done", answer } : t)));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "error", error: message } : t)));
    }
  };

  return (
    <div className="app">
      <header>
        <h1>Аналитика в чате</h1>
        <p>Спросите про продажи на обычном русском — покажу цифры и график.</p>
      </header>

      <main>
        {turns.length === 0 && (
          <div className="empty">
            <p>
              Данные: продажи по 300 торговым точкам в 8 регионах, план и факт за 2023–2026 годы.
            </p>
          </div>
        )}
        {turns.map((turn) => (
          <div className="turn" key={turn.id}>
            <div className="bubble user">{turn.question}</div>
            <Answer turn={turn} />
          </div>
        ))}
        <div ref={bottom} />
      </main>

      <Composer busy={busy} onSend={send} />
    </div>
  );
}
