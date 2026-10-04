import type { StepView } from "../types";

/** История вычислений. Кейс требует, чтобы пользователь видел, что уже
 *  добавлено и что можно отменить — поэтому формула показана текстом,
 *  а не спрятана. */
export function StepStack({
  steps,
  busy,
  onDrop,
  onUndo,
}: {
  steps: StepView[];
  busy: boolean;
  onDrop: (id: string) => void;
  onUndo: () => void;
}) {
  if (!steps.length) return null;
  return (
    <div className="steps">
      <div className="steps-head">
        <span>Вычисления · {steps.length}</span>
        <button className="link" disabled={busy} onClick={onUndo}>
          Отменить последнее
        </button>
      </div>
      <ol>
        {steps.map((step) => (
          <li key={step.id}>
            <div>
              <strong>{step.title}</strong>
              <span className="formula">{step.formula}</span>
            </div>
            <button
              className="drop"
              disabled={busy}
              title="Убрать это вычисление"
              onClick={() => onDrop(step.id)}
            >
              ×
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
