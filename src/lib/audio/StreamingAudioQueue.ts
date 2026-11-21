/**
 * StreamingAudioQueue: Gapless, low-latency audio queue for pipelined TTS.
 *
 * Designed to eliminate turnaround latency in voice mode. As soon as the first
 * sentence is synthesized, it starts playing while subsequent sentences are preloaded
 * and chained seamlessly.
 */

export interface AudioQueueItem {
  id: string;
  audioUrl: string;
  sentenceText: string;
}

export interface StreamingAudioQueueOptions {
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
  onSentenceChange?: (sentence: string) => void;
  onError?: (error: Error) => void;
}

export class StreamingAudioQueue {
  private queue: AudioQueueItem[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioItem: AudioQueueItem | null = null;
  private nextAudio: HTMLAudioElement | null = null;
  private nextAudioItem: AudioQueueItem | null = null;
  private isStreamFinished = false;
  private _isPlaying = false;
  private _isPaused = false;
  private _currentSentence: string | null = null;
  private options: StreamingAudioQueueOptions;
  private generation = 0;

  constructor(options: StreamingAudioQueueOptions = {}) {
    this.options = options;
  }

  public get isPlaying(): boolean {
    return this._isPlaying;
  }

  public get isPaused(): boolean {
    return this._isPaused;
  }

  public get currentSentence(): string | null {
    return this._currentSentence;
  }

  public get length(): number {
    return this.queue.length + (this.currentAudio ? 1 : 0);
  }

  /**
   * Enqueues an audio chunk (base64 data URL or blob URL) with its corresponding sentence.
   * Begins playback immediately if idle or if current playback was starved.
   */
  public enqueue(audioUrl: string, sentenceText: string): void {
    const id = `chunk_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const item: AudioQueueItem = { id, audioUrl, sentenceText };
    this.queue.push(item);

    // If no audio is currently playing and not paused, begin playback immediately
    if (!this.currentAudio && !this._isPaused) {
      this.playNext();
    } else if (this.currentAudio && !this.nextAudio && this.queue.length > 0) {
      // Preload the next audio for gapless playback
      this.preloadNext();
    }
  }

  /**
   * Signals that all sentences for this turn have been dispatched.
   * Allows queue to end playback when the final chunk finishes.
   */
  public markStreamComplete(): void {
    this.isStreamFinished = true;
    if (!this.currentAudio && this.queue.length === 0) {
      this.handlePlaybackComplete();
    }
  }

  /**
   * Preloads the next audio element in background so it's ready instantaneously.
   */
  private preloadNext(): void {
    if (this.queue.length === 0 || typeof Audio === 'undefined') return;
    const nextItem = this.queue[0];
    try {
      const audio = new Audio(nextItem.audioUrl);
      audio.preload = 'auto';
      this.nextAudio = audio;
      this.nextAudioItem = nextItem;
    } catch {
      // Ignore preload errors; will handle on actual play
    }
  }

  /**
   * Plays the next item in the queue.
   */
  private playNext(): void {
    if (this.queue.length === 0) {
      this.currentAudio = null;
      this.currentAudioItem = null;
      this.nextAudio = null;
      this.nextAudioItem = null;
      this._currentSentence = null;
      if (this.isStreamFinished) {
        this.handlePlaybackComplete();
      }
      return;
    }

    const currentItem = this.queue.shift()!;
    const currentGen = this.generation;

    this._currentSentence = currentItem.sentenceText;
    this.options.onSentenceChange?.(currentItem.sentenceText);

    try {
      let audio: HTMLAudioElement;
      if (this.nextAudio && this.nextAudioItem?.id === currentItem.id) {
        audio = this.nextAudio;
        this.nextAudio = null;
        this.nextAudioItem = null;
      } else {
        audio = new Audio(currentItem.audioUrl);
      }

      this.currentAudio = audio;
      this.currentAudioItem = currentItem;

      const onEnded = () => {
        if (this.generation !== currentGen) return;
        audio.removeEventListener('ended', onEnded);
        audio.removeEventListener('error', onError);
        this.playNext();
      };

      const onError = () => {
        if (this.generation !== currentGen) return;
        audio.removeEventListener('ended', onEnded);
        audio.removeEventListener('error', onError);
        const err = new Error('Audio element playback error');
        this.options.onError?.(err);
        this.playNext();
      };

      audio.addEventListener('ended', onEnded);
      audio.addEventListener('error', onError);

      const playPromise = audio.play();
      if (!this._isPlaying) {
        this._isPlaying = true;
        this._isPaused = false;
        this.options.onPlaybackStart?.();
      }

      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          if (this.generation !== currentGen) return;
          console.warn('[StreamingAudioQueue] play() rejected:', err);
          // If browser blocked autoplay, report error and try next
          this.options.onError?.(err instanceof Error ? err : new Error(String(err)));
          this.playNext();
        });
      }

      // Preload subsequent item while this one plays
      this.preloadNext();
    } catch (err) {
      console.warn('[StreamingAudioQueue] audio init failed:', err);
      this.options.onError?.(err instanceof Error ? err : new Error(String(err)));
      this.playNext();
    }
  }

  private handlePlaybackComplete(): void {
    if (this._isPlaying) {
      this._isPlaying = false;
      this._isPaused = false;
      this._currentSentence = null;
      this.options.onPlaybackEnd?.();
    }
  }

  /**
   * Pauses the currently playing audio.
   */
  public pause(): void {
    if (this.currentAudio && this._isPlaying && !this._isPaused) {
      this.currentAudio.pause();
      this._isPaused = true;
    }
  }

  /**
   * Resumes playback of paused audio.
   */
  public resume(): void {
    if (this.currentAudio && this._isPaused) {
      this.currentAudio.play().catch(() => {});
      this._isPaused = false;
    } else if (!this.currentAudio && this.queue.length > 0) {
      this.playNext();
    }
  }

  /**
   * Immediately stops playback, purges the queue, aborts pending items,
   * and resets all state. (Instant barge-in / cancellation).
   */
  public stop(): void {
    this.generation += 1;
    this.queue = [];
    this.isStreamFinished = false;

    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = '';
      } catch {
        // Safe ignore
      }
      this.currentAudio = null;
      this.currentAudioItem = null;
    }

    if (this.nextAudio) {
      try {
        this.nextAudio.src = '';
      } catch {
        // Safe ignore
      }
      this.nextAudio = null;
      this.nextAudioItem = null;
    }

    if (this._isPlaying || this._isPaused) {
      this._isPlaying = false;
      this._isPaused = false;
      this._currentSentence = null;
      this.options.onPlaybackEnd?.();
    }
  }
}
