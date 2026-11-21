import { describe, it, expect, vi, beforeEach } from 'vitest';
import { StreamingAudioQueue } from '@/lib/audio/StreamingAudioQueue';

// Mock HTMLAudioElement
class MockAudioElement {
  src = '';
  preload = '';
  currentTime = 0;
  private listeners: Record<string, ((e?: unknown) => void)[]> = {};

  addEventListener(event: string, listener: (e?: unknown) => void) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(listener);
  }

  removeEventListener(event: string, listener: (e?: unknown) => void) {
    if (!this.listeners[event]) return;
    this.listeners[event] = this.listeners[event].filter((l) => l !== listener);
  }

  dispatchEvent(event: string) {
    const list = this.listeners[event] || [];
    list.forEach((l) => l());
  }

  play() {
    return Promise.resolve();
  }

  pause() {
    this.dispatchEvent('pause');
  }

  triggerEnded() {
    this.dispatchEvent('ended');
  }

  triggerError() {
    this.dispatchEvent('error');
  }
}

describe('StreamingAudioQueue', () => {
  let createdAudios: MockAudioElement[] = [];

  beforeEach(() => {
    createdAudios = [];
    vi.stubGlobal('Audio', vi.fn(function MockAudio(src?: string) {
      const audio = new MockAudioElement();
      if (src) audio.src = src;
      createdAudios.push(audio);
      return audio;
    }));
  });

  it('starts playback when first chunk is enqueued', () => {
    const onStart = vi.fn();
    const onSentence = vi.fn();
    const queue = new StreamingAudioQueue({
      onPlaybackStart: onStart,
      onSentenceChange: onSentence,
    });

    queue.enqueue('audio1.mp3', 'First sentence.');

    expect(queue.isPlaying).toBe(true);
    expect(queue.currentSentence).toBe('First sentence.');
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onSentence).toHaveBeenCalledWith('First sentence.');
    expect(createdAudios.length).toBe(1);
    expect(createdAudios[0].src).toBe('audio1.mp3');
  });

  it('preloads the next chunk when enqueued while playing', () => {
    const queue = new StreamingAudioQueue();
    queue.enqueue('audio1.mp3', 'First.');
    queue.enqueue('audio2.mp3', 'Second.');

    expect(createdAudios.length).toBe(2);
    expect(createdAudios[1].src).toBe('audio2.mp3');
    expect(createdAudios[1].preload).toBe('auto');
  });

  it('chains seamlessly to the next chunk upon ended event', () => {
    const onSentence = vi.fn();
    const onEnd = vi.fn();
    const queue = new StreamingAudioQueue({
      onSentenceChange: onSentence,
      onPlaybackEnd: onEnd,
    });

    queue.enqueue('audio1.mp3', 'First.');
    queue.enqueue('audio2.mp3', 'Second.');
    queue.markStreamComplete();

    expect(queue.currentSentence).toBe('First.');

    // Simulate first audio finishing
    createdAudios[0].triggerEnded();

    expect(queue.currentSentence).toBe('Second.');
    expect(onSentence).toHaveBeenCalledWith('Second.');
    expect(onEnd).not.toHaveBeenCalled();

    // Simulate second audio finishing
    createdAudios[1].triggerEnded();

    expect(queue.isPlaying).toBe(false);
    expect(queue.currentSentence).toBeNull();
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('instantly stops and clears queue when stop() is called', () => {
    const onEnd = vi.fn();
    const queue = new StreamingAudioQueue({ onPlaybackEnd: onEnd });

    queue.enqueue('audio1.mp3', 'First.');
    queue.enqueue('audio2.mp3', 'Second.');

    expect(queue.isPlaying).toBe(true);

    queue.stop();

    expect(queue.isPlaying).toBe(false);
    expect(queue.currentSentence).toBeNull();
    expect(queue.length).toBe(0);
    expect(onEnd).toHaveBeenCalledTimes(1);

    // Later ended triggers should not restart or crash
    createdAudios[0].triggerEnded();
    expect(queue.isPlaying).toBe(false);
  });

  it('resumes playback seamlessly when a new chunk arrives after the queue was briefly starved', () => {
    const onSentence = vi.fn();
    const onEnd = vi.fn();
    const queue = new StreamingAudioQueue({
      onSentenceChange: onSentence,
      onPlaybackEnd: onEnd,
    });

    queue.enqueue('audio1.mp3', 'First.');
    expect(queue.isPlaying).toBe(true);
    expect(queue.currentSentence).toBe('First.');

    // Audio 1 finishes before Audio 2 arrives over network
    createdAudios[0].triggerEnded();

    // Now Audio 2 arrives
    queue.enqueue('audio2.mp3', 'Second.');

    expect(queue.isPlaying).toBe(true);
    expect(queue.currentSentence).toBe('Second.');
    expect(onSentence).toHaveBeenCalledWith('Second.');

    // Complete stream and end Audio 2
    queue.markStreamComplete();
    createdAudios[1].triggerEnded();

    expect(queue.isPlaying).toBe(false);
    expect(queue.currentSentence).toBeNull();
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('handles pause and resume', () => {
    const queue = new StreamingAudioQueue();
    queue.enqueue('audio1.mp3', 'Sentence.');

    queue.pause();
    expect(queue.isPaused).toBe(true);

    queue.resume();
    expect(queue.isPaused).toBe(false);
  });
});
