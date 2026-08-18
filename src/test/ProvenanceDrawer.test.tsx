import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ProvenanceDrawer } from '@/components/compliance/ProvenanceDrawer';
import type { Message } from '@/lib/chatStorage';
import type { AIProvenanceManifest } from '@/types/provenance';

const mockToast = vi.fn();
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

describe('ProvenanceDrawer Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  const sampleManifest: AIProvenanceManifest = {
    id: 'test-manifest-123',
    originType: 'ai_generated',
    riskTier: 'transparency',
    modality: 'text',
    generatedAt: '2026-08-17T20:00:00.000Z',
    modelDescriptor: {
      name: 'AskMukthiGuru LLaMA Ensemble',
      version: 'v2.6.0',
      provider: 'AskMukthiGuru Platform',
      parameters: 'Dual-Level GraphRAG + BGE-M3',
    },
    latencyMs: 680,
    grounding: {
      status: 'grounded',
      sourceCount: 3,
      sources: [
        { title: 'The Four Sacred Secrets - Chapter 2', url: 'https://example.com/ch2' },
        { title: 'Discourse on Inner Peace (YouTube)', url: 'https://youtube.com/watch?v=123' },
      ],
      confidenceScore: 0.94,
      evidenceSupportLabel: 'Dual-Layer Doctrine Retrieval',
      corpusVersion: 'v2026.08',
    },
    disclosure: {
      article: 'Article 50(1)',
      notice: 'AI-Generated Content: Synthesized by AskMukthiGuru AI.',
      plainLanguageDisclosure:
        'In compliance with EU AI Act Article 50: You are interacting with an AI assistant grounded in spiritual wisdom teachings.',
    },
  };

  const sampleMessage: Message = {
    id: 'msg-456',
    role: 'guru',
    content: 'Wisdom begins with self-observation.',
    timestamp: new Date('2026-08-17T20:00:00.000Z'),
    citations: ['https://example.com/source1', 'https://example.com/source2'],
    confidenceScore: 0.92,
    groundingState: 'grounded',
  };

  it('does not render drawer content when isOpen is false', () => {
    render(<ProvenanceDrawer isOpen={false} onClose={vi.fn()} manifest={sampleManifest} />);

    expect(screen.queryByTestId('provenance-drawer')).not.toBeInTheDocument();
  });

  it('renders drawer header, Article 50 disclosure, and compliance risk tier when open', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    expect(screen.getByTestId('provenance-drawer')).toBeInTheDocument();
    expect(screen.getByText('AI Provenance & Disclosure')).toBeInTheDocument();
    expect(screen.getByText(/Article 50\(1\) Transparency Notice/i)).toBeInTheDocument();
    expect(screen.getByText(/Tier: transparency/i)).toBeInTheDocument();
    expect(
      screen.getByText(/In compliance with EU AI Act Article 50/i)
    ).toBeInTheDocument();
  });

  it('renders origin classification visual meter with correct active state', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    expect(screen.getByText('Origin Classification Meter')).toBeInTheDocument();
    expect(screen.getAllByText('AI Generated').length).toBeGreaterThan(0);
    expect(screen.getByText('Human')).toBeInTheDocument();
    expect(screen.getByText('AI Assisted')).toBeInTheDocument();
  });

  it('displays inference model descriptors, latency, and formatted timestamp', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    expect(screen.getByText('AskMukthiGuru LLaMA Ensemble')).toBeInTheDocument();
    expect(screen.getByText('680 ms')).toBeInTheDocument();
    expect(screen.getByText('Dual-Level GraphRAG + BGE-M3')).toBeInTheDocument();
  });

  it('displays knowledge grounding details and source references', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    expect(screen.getByText('Knowledge Grounding Lineage')).toBeInTheDocument();
    expect(screen.getByText('3 verified sources')).toBeInTheDocument();
    expect(screen.getByText('The Four Sacred Secrets - Chapter 2')).toBeInTheDocument();
    expect(screen.getByText('94%')).toBeInTheDocument();
  });

  it('derives provenance manifest automatically from Message prop', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} message={sampleMessage} />);

    expect(screen.getByTestId('provenance-drawer')).toBeInTheDocument();
    expect(screen.getByText('2 verified sources')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('toggles machine-readable JSON-LD preview on click', () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    const toggleBtn = screen.getByRole('button', { name: /show preview/i });
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByText(/hide preview/i)).toBeInTheDocument();
    expect(screen.getByText(/http:\/\/www\.w3\.org\/ns\/prov#/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /hide preview/i }));
    expect(screen.getByText(/show preview/i)).toBeInTheDocument();
  });

  it('copies PROV-O JSON-LD to clipboard and shows feedback when copy button is clicked', async () => {
    render(<ProvenanceDrawer isOpen={true} onClose={vi.fn()} manifest={sampleManifest} />);

    const copyBtn = screen.getByRole('button', {
      name: /copy machine-readable prov-o json-ld/i,
    });
    expect(copyBtn).toBeInTheDocument();

    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Machine-Readable Provenance Copied',
      })
    );

    expect(screen.getByText('Copied PROV-O JSON-LD!')).toBeInTheDocument();
  });
});
