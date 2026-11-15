declare module "plotly.js-dist-min" {
  const Plotly: {
    react(el: HTMLElement, data: unknown[], layout: unknown, config?: unknown): Promise<unknown>;
    purge(el: HTMLElement): void;
  toImage(
    el: HTMLElement,
    opts: { format: "png" | "jpeg" | "webp" | "svg"; width: number; height: number; scale?: number },
  ): Promise<string>;
    Plots: { resize(el: HTMLElement): void };
  };
  export default Plotly;
}
