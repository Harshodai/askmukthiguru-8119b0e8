import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { DeepenAndTuneBar } from '@/components/chat/DeepenAndTuneBar';
import type { Message } from '@/lib/chatStorage';

vi.mock('@/hooks/useProfile', () => ({
  useProfile: () => ({
    profile: {
      displayName: 'Seeker',
      familiarityLevel: 'practitioner',
    },
    updateProfile: vi.fn().mockResolvedValue({}),
  }),
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockOpenSereneMind = vi.fn();
vi.mock('@/components/common/SereneMindProvider', () => ({
  useSereneMind: () => ({
    open: mockOpenSereneMind,
    close: vi.fn(),
    isOpen: false,
  }),
}));

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: {
    getRelevant: vi.fn().mockResolvedValue([
      { id: '1', content: 'You recognized your inner observer during meditation.', similarity: 0.85 },
    ]),
  },
}));

vi.mock('@xyflow/react', async () => {
  return {
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    Position: { Top: 'top', Right: 'right', Bottom: 'bottom', Left: 'left' },
    ReactFlow: ({ nodes }: { nodes: Array<{ id: string; data: { label: string } }> }) => (
      <div data-testid="react-flow-micro">
        {nodes.map((n) => (
          <div key={n.id} data-testid="flow-node">
            {n.data.label}
          </div>
        ))}
      </div>
    ),
  };
});

describe('DeepenAndTuneBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockMessage: Message = {
    id: 'msg-1',
    role: 'guru',
    content: 'When you cease the internal war, the turbulence begins to dissolve into a beautiful state of connection.',
    timestamp: new Date(),
  };

  const mockCitation = {
    url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    title: 'Transform Your Life by Forgiving Yourself',
    speaker: 'Sri Preethaji',
    playbackStartSeconds: 76,
    playbackEndSeconds: 165,
  };

  const renderComponent = (props: Partial<React.ComponentProps<typeof DeepenAndTuneBar>> = {}) =>
    render(
      <BrowserRouter>
        <DeepenAndTuneBar
          message={mockMessage}
          queryText="How to reach peace?"
          citation={mockCitation}
          {...props}
        />
      </BrowserRouter>
    );

  it('renders all 4 quadrants clearly', () => {
    renderComponent();

    // Check Eyebrow
    expect(screen.getByTestId('deepen-and-tune-bar')).toBeInTheDocument();
    expect(screen.getByText(/Deepen & Tune Your Contemplation/i)).toBeInTheDocument();

    // Quadrant A
    expect(screen.getByText(/Pattern A · Memgraph GraphRAG/i)).toBeInTheDocument();
    expect(screen.getByText('Beautiful State')).toBeInTheDocument();

    // Quadrant B
    expect(screen.getByText(/Pattern B · Journey & Resonance/i)).toBeInTheDocument();
    expect(screen.getByText(/Reflect with My Journey/i)).toBeInTheDocument();
    expect(screen.getByText(/Practitioner/i)).toBeInTheDocument();

    // Quadrant C
    expect(screen.getByText(/Pattern C · Somatic Embodiment/i)).toBeInTheDocument();
    expect(screen.getByText(/3-Min Serene Mind Reset/i)).toBeInTheDocument();

    // Quadrant D
    expect(screen.getByText(/Pattern D · Surrounding Discourse/i)).toBeInTheDocument();
    expect(screen.getByText(/Watch Full Video/i)).toBeInTheDocument();
    expect(screen.getByText(/Surrounding Discourse Window/i)).toBeInTheDocument();
  });

  it('clicking a concept pill opens the Memgraph micro-graph modal', async () => {
    renderComponent();

    const conceptBtn = screen.getByText('Beautiful State');
    fireEvent.click(conceptBtn);

    // Modal opens
    await waitFor(() => {
      expect(screen.getByTestId('react-flow-micro')).toBeInTheDocument();
    });
    expect(screen.getByText('Explore Full Knowledge Graph')).toBeInTheDocument();
  });

  it('clicking 3-Min Serene Mind Reset invokes useSereneMind()', () => {
    renderComponent();

    const sereneBtn = screen.getByText(/3-Min Serene Mind Reset/i);
    fireEvent.click(sereneBtn);

    expect(mockOpenSereneMind).toHaveBeenCalledWith('audio', false);
  });

  it('clicking Reflect with My Journey displays recalled insights from Second Brain Vault', async () => {
    renderComponent();

    const reflectBtn = screen.getByText(/Reflect with My Journey/i);
    fireEvent.click(reflectBtn);

    await waitFor(() => {
      expect(screen.getByText(/You recognized your inner observer during meditation/i)).toBeInTheDocument();
    });
  });

  it('triggers onOpenVideoModal and onOpenSearchModal when clicked in Quadrant D', () => {
    const onOpenVideo = vi.fn();
    const onOpenSearch = vi.fn();

    renderComponent({ onOpenVideoModal: onOpenVideo, onOpenSearchModal: onOpenSearch });

    fireEvent.click(screen.getByText(/Watch Full Video/i));
    expect(onOpenVideo).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText(/Surrounding Discourse Window/i));
    expect(onOpenSearch).toHaveBeenCalledTimes(1);
  });
});
