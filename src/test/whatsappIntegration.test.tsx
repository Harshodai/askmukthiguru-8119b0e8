import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LinkWhatsAppPage from '@/pages/LinkWhatsAppPage';
import { WhatsAppCard } from '@/components/profile/settings/WhatsAppCard';

const mockGetSession = vi.fn();
const mockOnAuthStateChange = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: () => mockGetSession(),
      onAuthStateChange: () => mockOnAuthStateChange(),
    },
  },
}));

vi.mock('@/lib/backendUrl', () => ({
  BACKEND_URL: 'https://backend.test',
}));

describe('WhatsApp Two-Channel Account Linking & DPDP Consent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders unauthenticated prompt when user has no active session', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } });

    render(
      <MemoryRouter initialEntries={['/link-whatsapp#code=test-challenge-123']}>
        <Routes>
          <Route path="/link-whatsapp" element={<LinkWhatsAppPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Sign in to complete linking/i)).toBeInTheDocument();
      expect(screen.getByText(/Sign In or Create Account/i)).toBeInTheDocument();
    });
  });

  it('renders confirmation card with token when signed in', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        session: {
          access_token: 'fake-jwt-token',
          user: { id: 'usr-123', email: 'seeker@example.com' },
        },
      },
    });

    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ linked: false }),
    });

    render(
      <MemoryRouter initialEntries={['/link-whatsapp#code=my-secret-token-456']}>
        <Routes>
          <Route path="/link-whatsapp" element={<LinkWhatsAppPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Confirm Connection/i)).toBeInTheDocument();
      expect(screen.getByText(/my-secret-token-456/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Confirm & Link WhatsApp/i })).toBeInTheDocument();
    });
  });

  it('successfully verifies token and renders DPDP consent switches', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        session: {
          access_token: 'fake-jwt-token',
          user: { id: 'usr-123', email: 'seeker@example.com' },
        },
      },
    });

    // 1. Initial status fetch
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ linked: false }),
    });

    // 2. Link verify call
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        masked_phone: '+91 98*** **210',
        sync_history_consent: false,
        memory_write_consent: false,
        linked_at: new Date().toISOString(),
      }),
    });

    render(
      <MemoryRouter initialEntries={['/link-whatsapp#code=valid-token-789']}>
        <Routes>
          <Route path="/link-whatsapp" element={<LinkWhatsAppPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Confirm & Link WhatsApp/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Confirm & Link WhatsApp/i }));

    await waitFor(() => {
      expect(screen.getByText(/WhatsApp Connected/i)).toBeInTheDocument();
      expect(screen.getByText(/\+91 98\*\*\* \*\*210/i)).toBeInTheDocument();
      expect(screen.getByText(/Return to WhatsApp/i)).toBeInTheDocument();
      expect(screen.getByText(/Sync Chat History/i)).toBeInTheDocument();
      expect(screen.getByText(/Spiritual Journey Memory/i)).toBeInTheDocument();
    });

    // Verify verify payload called backend with Authorization header and DPDP flags
    expect(global.fetch).toHaveBeenCalledWith(
      'https://backend.test/api/whatsapp/link/verify',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer fake-jwt-token',
        }),
        body: JSON.stringify({
          code: 'valid-token-789',
          sync_history_consent: true,
          memory_write_consent: true,
        }),
      })
    );
  });

  it('WhatsAppCard renders connection state in profile settings', async () => {
    mockGetSession.mockResolvedValue({
      data: {
        session: {
          access_token: 'fake-jwt-token',
          user: { id: 'usr-123', email: 'seeker@example.com' },
        },
      },
    });

    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        linked: true,
        masked_phone: '+91 99*** **333',
        sync_history_consent: true,
        memory_write_consent: false,
        linked_at: '2026-11-21T10:00:00Z',
      }),
    });

    render(
      <MemoryRouter>
        <WhatsAppCard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/WhatsApp Companion/i)).toBeInTheDocument();
      expect(screen.getByText(/\+91 99\*\*\* \*\*333/i)).toBeInTheDocument();
      expect(screen.getByText(/Disconnect/i)).toBeInTheDocument();
    });
  });
});
