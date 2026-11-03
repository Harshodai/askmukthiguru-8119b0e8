// DORMANT (2026-11-01 wiring audit, plan §12): no component imports this; not shipped.
/**
 * ResilientStreamTransport.ts
 * SSE client with automatic exponential-backoff reconnect, passing Last-Event-ID header.
 * Handles network glitches transparently without losing already streamed tokens.
 */

export interface StreamMessage {
  id?: string;
  event?: string;
  data: string;
}

export interface ResilientTransportOptions {
  url: string;
  headers?: Record<string, string>;
  onMessage: (msg: StreamMessage) => void;
  onError?: (error: Event | Error) => void;
  onReconnect?: (attempt: number) => void;
  maxRetries?: number;
}

export class ResilientStreamTransport {
  private url: string;
  private headers: Record<string, string>;
  private onMessage: (msg: StreamMessage) => void;
  private onError?: (error: Event | Error) => void;
  private onReconnect?: (attempt: number) => void;
  private maxRetries: number;
  private lastEventId: string = "";
  private retryCount: number = 0;
  private isConnected: boolean = false;
  private abortController: AbortController | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: ResilientTransportOptions) {
    this.url = options.url;
    this.headers = options.headers || {};
    this.onMessage = options.onMessage;
    this.onError = options.onError;
    this.onReconnect = options.onReconnect;
    this.maxRetries = options.maxRetries ?? 10;
  }

  public async connect(): Promise<void> {
    this.abortController = new AbortController();
    this.isConnected = true;

    const reqHeaders: Record<string, string> = {
      ...this.headers,
      'Accept': 'text/event-stream',
    };

    if (this.lastEventId) {
      reqHeaders['Last-Event-ID'] = this.lastEventId;
    }

    try {
      const response = await fetch(this.url, {
        method: 'GET',
        headers: reqHeaders,
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('ReadableStream not supported on response.');
      }

      this.retryCount = 0; // Reset retry count upon successful connection
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (this.isConnected) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || ''; // Keep incomplete trailing line in buffer

        let currentEvent: Partial<StreamMessage> = {};

        for (const line of lines) {
          if (line.trim() === '') {
            // Dispatch event
            if (currentEvent.data !== undefined) {
              if (currentEvent.id) {
                this.lastEventId = currentEvent.id;
              }
              this.onMessage({
                id: currentEvent.id,
                event: currentEvent.event || 'message',
                data: currentEvent.data,
              });
            }
            currentEvent = {};
            continue;
          }

          if (line.startsWith(':')) {
            // Comment / heartbeat
            continue;
          }

          const colonIdx = line.indexOf(':');
          let field = line;
          let val = '';
          if (colonIdx !== -1) {
            field = line.slice(0, colonIdx);
            val = line.slice(colonIdx + 1);
            if (val.startsWith(' ')) {
              val = val.slice(1);
            }
          }

          if (field === 'id') {
            currentEvent.id = val;
          } else if (field === 'event') {
            currentEvent.event = val;
          } else if (field === 'data') {
            currentEvent.data = currentEvent.data ? currentEvent.data + '\n' + val : val;
          }
        }
      }
    } catch (err: unknown) {
      const error = err instanceof Error ? err : new Error(String(err));
      if (error.name === 'AbortError') {
        return; // intentional disconnect
      }
      if (this.onError) {
        this.onError(error);
      }
      this.handleReconnect();
    }
  }

  private handleReconnect(): void {
    if (!this.isConnected) return;

    if (this.retryCount >= this.maxRetries) {
      if (this.onError) {
        this.onError(new Error(`Max reconnection attempts (${this.maxRetries}) reached.`));
      }
      return;
    }

    this.retryCount++;
    const backoffMs = Math.min(1000 * Math.pow(2, this.retryCount - 1), 30000);

    if (this.onReconnect) {
      this.onReconnect(this.retryCount);
    }

    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
    }

    this.retryTimer = setTimeout(() => {
      if (this.isConnected) {
        this.connect();
      }
    }, backoffMs);
  }

  public disconnect(): void {
    this.isConnected = false;
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }

  public getLastEventId(): string {
    return this.lastEventId;
  }
}
