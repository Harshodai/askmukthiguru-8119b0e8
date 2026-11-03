import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

// Mock framer-motion AnimatePresence to avoid animation timer noise in step transitions
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

import { GUIDED_STEPS, TOTAL_DURATION_SECONDS, PREETHAJI_AUDIO_SRC } from '@/components/meditation/meditationSteps';
import { GuidedMeditationFlow } from '@/components/meditation/GuidedMeditationFlow';
import { SereneMindModal } from '@/components/chat/SereneMindModal';

// controllable FakeAudio for HTMLAudioElement
class FakeAudio {
  src = '';
  currentTime = 0;
  volume = 1;
  muted = false;
  preload = '';
  error: { code: number } | null = null;
  networkState = 0;
  readyState = 0;
  onerror: (() => void) | null = null;
  ontimeupdate: (() => void) | null = null;
  onended: (() => void) | null = null;
  play = vi.fn(() => Promise.resolve());
  pause = vi.fn();
  removeAttribute(name: string) {
    if (name === 'src') this.src = '';
  }
}

describe('Serene Mind Audio & Timer Synchronization', () => {
  let instances: FakeAudio[] = [];

  beforeEach(() => {
    instances = [];
    vi.stubGlobal(
      'Audio',
      function AudioMock() {
        const el = new FakeAudio();
        instances.push(el);
        return el;
      },
    );
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('Audio Asset & Steps Contract', () => {
    it('uses the normalized authentic Preethaji audio URL', () => {
      expect(PREETHAJI_AUDIO_SRC).toBe('/audio/meditation/preethaji-serene-mind.mp3');
      expect(GUIDED_STEPS.every((s) => s.audioSrc === '/audio/meditation/preethaji-serene-mind.mp3')).toBe(true);
    });

    it('has exactly 6 steps matching the 236s recording timeline', () => {
      expect(GUIDED_STEPS).toHaveLength(6);
      expect(GUIDED_STEPS.map((s) => s.durationSeconds)).toEqual([21, 47, 63, 47, 47, 11]);
      expect(TOTAL_DURATION_SECONDS).toBe(236);
    });

    it('defines the 4-0-6 breath pattern on Step 2 (Observe the Breath)', () => {
      const breathStep = GUIDED_STEPS[2];
      expect(breathStep.id).toBe('observe-breath');
      expect(breathStep.breathPattern).toEqual({ inhale: 4, hold: 0, exhale: 6 });
    });
  });

  describe('GuidedMeditationFlow Audio & Visual Synchronization', () => {
    it('renders the "Guided by Sri Preethaji\'s Voice" header badge', () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      expect(screen.getByText("Guided by Sri Preethaji's Voice")).toBeInTheDocument();
    });

    it('loads the Preethaji audio src on mount into the Audio element', () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      expect(instances.length).toBeGreaterThanOrEqual(1);
      const audio = instances[0];
      expect(audio.src).toBe('/audio/meditation/preethaji-serene-mind.mp3');
    });

    it('starts audio playback when play button is clicked', async () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      const audio = instances[0];
      const playButton = screen.getByRole('button', { name: '' });

      await act(async () => {
        fireEvent.click(playButton);
      });

      expect(audio.play).toHaveBeenCalled();
    });

    it('updates step index and countdown synchronously as audio time progresses', async () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      const audio = instances[0];

      // Step 0: Arrive (21s duration)
      expect(screen.getByText('Arrive')).toBeInTheDocument();
      expect(screen.getByText(/21s remaining/i)).toBeInTheDocument();

      // Progress 10s into Step 0
      await act(async () => {
        audio.currentTime = 10;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText('Arrive')).toBeInTheDocument();
      expect(screen.getByText(/11s remaining/i)).toBeInTheDocument();

      // Progress to 21.5s -> Step 1: Observe the Body (starts at 21s, duration 47s)
      await act(async () => {
        audio.currentTime = 21.5;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText('Observe the Body')).toBeInTheDocument();
      // 47 - 0.5 = 46.5 -> ceil to 47s remaining
      expect(screen.getByText(/47s remaining/i)).toBeInTheDocument();

      // Progress to 68s -> Step 2: Observe the Breath (starts at 68s, duration 63s)
      await act(async () => {
        audio.currentTime = 68;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText('Observe the Breath')).toBeInTheDocument();
      expect(screen.getByText(/63s remaining/i)).toBeInTheDocument();
    });

    it('synchronizes the breath cycle (inhale 4s, exhale 6s) with elapsed audio time in Step 2', async () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      const audio = instances[0];

      // Jump to step 2 (starts at 68s)
      await act(async () => {
        audio.currentTime = 68; // elapsed = 0s in step 2
        audio.ontimeupdate?.();
      });

      // At elapsed = 0s: inhale
      expect(screen.getByText(/inhale/i)).toBeInTheDocument();

      // At elapsed = 3s (audio.currentTime = 71s): still inhale
      await act(async () => {
        audio.currentTime = 71;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText(/inhale/i)).toBeInTheDocument();

      // At elapsed = 4s (audio.currentTime = 72s): switches to exhale (4s inhale complete)
      await act(async () => {
        audio.currentTime = 72;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText(/exhale/i)).toBeInTheDocument();

      // At elapsed = 9s (audio.currentTime = 77s): still exhale
      await act(async () => {
        audio.currentTime = 77;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText(/exhale/i)).toBeInTheDocument();

      // At elapsed = 10s (audio.currentTime = 78s): next cycle starts -> inhale
      await act(async () => {
        audio.currentTime = 78;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText(/inhale/i)).toBeInTheDocument();
    });

    it('skips step cleanly by seeking audio forward to the next step start time without snapping back', async () => {
      render(<GuidedMeditationFlow isOpen={true} onClose={vi.fn()} />);
      const audio = instances[0];

      // Initial state: Step 0 (Arrive)
      expect(screen.getByText('Arrive')).toBeInTheDocument();

      // Click Skip Step button
      const skipButton = screen.getByTitle('Skip step');
      await act(async () => {
        fireEvent.click(skipButton);
      });

      // Next step (Observe the Body) starts at 21s
      expect(audio.currentTime).toBe(21);
      expect(screen.getByText('Observe the Body')).toBeInTheDocument();

      // When audio emits ontimeupdate at 21.2s, it remains at Step 1 (NO snapping back to Step 0)
      await act(async () => {
        audio.currentTime = 21.2;
        audio.ontimeupdate?.();
      });
      expect(screen.getByText('Observe the Body')).toBeInTheDocument();
    });
  });

  describe('SereneMindModal MediaTab Direct Audio Mode', () => {
    it('renders with direct audio source in audio mode without YouTube 404', () => {
      render(<SereneMindModal isOpen={true} onClose={vi.fn()} initialTab="audio" />);
      expect(screen.getByText("Sri Preethaji's Voice")).toBeInTheDocument();
      expect(screen.getByText('Practice Progression')).toBeInTheDocument();
      // Should show the 6 authentic audio practice progression steps
      expect(screen.getByText('Arrive')).toBeInTheDocument();
      expect(screen.getByText('Observe the Body')).toBeInTheDocument();
      expect(screen.getByText('Observe the Breath')).toBeInTheDocument();
    });
  });
});
