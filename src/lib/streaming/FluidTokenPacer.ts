/**
 * FluidTokenPacer.ts
 * 60fps typewriter animation queue using requestAnimationFrame with dynamic character-rate interpolation
 * (target 25-40 chars/sec for readable spiritual guidance).
 * Eliminates visual stutter and chunk bursts, handling cancellation, completion, and punctuation pacing.
 */

export interface PacerOptions {
  targetCharsPerSec?: number;
  onEmit: (char: string) => void;
  onComplete?: () => void;
}

export class FluidTokenPacer {
  private queue: string[] = [];
  private rafId: number | null = null;
  private lastTime: number = 0;
  private charsPerSec: number;
  private charIntervalMs: number;
  private accumulatedTime: number = 0;
  private onEmit: (char: string) => void;
  private onComplete?: () => void;
  private isRunning: boolean = false;

  constructor(options: PacerOptions) {
    this.charsPerSec = options.targetCharsPerSec ?? 32; // ~32 chars/sec optimal for reading cadence
    this.charIntervalMs = 1000 / this.charsPerSec;
    this.onEmit = options.onEmit;
    this.onComplete = options.onComplete;
  }

  public push(text: string): void {
    for (let i = 0; i < text.length; i++) {
      this.queue.push(text[i]);
    }
    if (!this.isRunning && this.queue.length > 0) {
      this.start();
    }
  }

  public start(): void {
    if (this.isRunning) return;
    this.isRunning = true;
    this.lastTime = performance.now();
    this.tick = this.tick.bind(this);
    this.rafId = requestAnimationFrame(this.tick);
  }

  private tick(currentTime: number): void {
    if (!this.isRunning) return;

    const delta = currentTime - this.lastTime;
    this.lastTime = currentTime;
    this.accumulatedTime += delta;

    while (this.accumulatedTime >= this.charIntervalMs && this.queue.length > 0) {
      const char = this.queue.shift()!;
      this.onEmit(char);
      this.accumulatedTime -= this.charIntervalMs;

      // Natural pause on punctuation (. , ! ?)
      if (['.', '!', '?', '،'].includes(char)) {
        this.accumulatedTime -= 120; // Extra 120ms pause for reflective pacing
      } else if ([',', ';', ':'].includes(char)) {
        this.accumulatedTime -= 60; // Extra 60ms pause
      }
    }

    if (this.queue.length === 0 && this.accumulatedTime <= 0) {
      this.stop();
      if (this.onComplete) {
        this.onComplete();
      }
    } else {
      this.rafId = requestAnimationFrame(this.tick);
    }
  }

  public stop(): void {
    this.isRunning = false;
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.accumulatedTime = 0;
  }

  public flush(): void {
    if (this.queue.length > 0) {
      const remaining = this.queue.join('');
      this.queue = [];
      this.onEmit(remaining);
    }
    this.stop();
    if (this.onComplete) {
      this.onComplete();
    }
  }

  public getQueueLength(): number {
    return this.queue.length;
  }
}
