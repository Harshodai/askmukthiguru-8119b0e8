type TelemetryFailureHandler = (title: string, summary: string) => void;

const subscribers = new Set<TelemetryFailureHandler>();

export const telemetryEvents = {
  subscribe(fn: TelemetryFailureHandler): () => void {
    subscribers.add(fn);
    return () => subscribers.delete(fn);
  },
  emitFailure(title: string, summary: string): void {
    subscribers.forEach((fn) => fn(title, summary));
  },
};
