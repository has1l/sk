import { Component, type ErrorInfo, type ReactNode } from "react";

/** Падение в отрисовке не должно превращаться в чёрный экран: React снимает
 *  всё дерево, и пользователь остаётся без интерфейса и без объяснения.
 */
export class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Интерфейс упал:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="crash">
        <h2>Интерфейс упал</h2>
        <p>{this.state.error.message}</p>
        <pre>{this.state.error.stack}</pre>
        <button onClick={() => this.setState({ error: null })}>Попробовать снова</button>
      </div>
    );
  }
}
