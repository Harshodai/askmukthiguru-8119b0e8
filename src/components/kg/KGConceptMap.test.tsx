import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/i18n';
import { KGConceptMap, DEMO_DATA } from '@/components/kg/KGConceptMap';

vi.mock('@/lib/chat/config', () => ({ getAIConfig: () => ({ endpoint: 'http://localhost:8000/api/chat' }) }));
vi.mock('@/lib/chat/auth', () => ({ getAccessToken: vi.fn(() => Promise.resolve('token')) }));

const liveData = { nodes: [{ id: 'n1', label: 'Beautiful State', type: 'State', teacher: 'Sri Preethaji' }], edges: [] };

const renderWithI18n = (ui: React.ReactElement) => render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);

const advanceSimulation = async () => {
  // Let the KG force-directed simulation run through its frames.
  await act(async () => {
    for (let i = 0; i < 5; i++) {
       
      await vi.advanceTimersByTimeAsync(16);
    }
  });
};

describe('KGConceptMap', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame'] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders live subgraph and hides demo label', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(liveData) }));
    vi.stubGlobal('fetch', fetchMock);
    renderWithI18n(<KGConceptMap initialQuery="beautiful state" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await act(async () => { await Promise.resolve(); });
    await advanceSimulation();
    await waitFor(() => expect(screen.getByLabelText('Beautiful State')).toBeInTheDocument());
    expect(screen.queryByText(/example map/i)).not.toBeInTheDocument();
  });

  it('shows show-example button on empty live result and loads demo when clicked', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) })));
    renderWithI18n(<KGConceptMap initialQuery="xyz" />);
    const btn = await screen.findByRole('button', { name: /example map/i });
    fireEvent.click(btn);
    await advanceSimulation();
    await waitFor(() => expect(screen.getByLabelText('Beautiful State')).toBeInTheDocument());
    expect(screen.getByText(/example map/i)).toBeInTheDocument();
  });

  it('falls back to demo data on fetch failure and offers a live-map retry', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })));
    renderWithI18n(<KGConceptMap initialQuery="fail" />);
    await act(async () => { await Promise.resolve(); });
    await advanceSimulation();
    await waitFor(() => expect(screen.getByLabelText('Beautiful State')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /retry live map/i })).toBeInTheDocument();
  });

  it('does not contain off-brand Krishnamurti node in demo data', () => {
    const names = DEMO_DATA.nodes.map((n) => n.label.toLowerCase());
    const teachers = DEMO_DATA.nodes.map((n) => (n.teacher || '').toLowerCase());
    const hasOffBrand = [...names, ...teachers].some((s) => s.includes('krishnamurti'));
    expect(hasOffBrand).toBe(false);
    expect(DEMO_DATA.nodes.some((n) => n.label === 'Sri Krishnaji')).toBe(true);
  });
});
