import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryManager } from '@/components/profile/MemoryManager';
import { memoryApi } from '@/lib/memoryApi';

const toastMock = vi.fn();
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock('@/hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: '',
    interimTranscript: '',
    isSupported: true,
    startListening: vi.fn(),
    stopListening: vi.fn(),
  }),
}));

vi.mock('@/components/kg/KGConceptMap', () => ({
  KGConceptMap: (props: {
    scope?: string;
    hasConsent?: boolean | null;
    onApproveConsent?: () => void;
  }) => (
    <div
      data-testid="kg-concept-map"
      data-scope={props.scope}
      data-has-consent={String(props.hasConsent)}
    >
      <button
        data-testid="kg-approve-consent-btn"
        onClick={() => props.onApproveConsent?.()}
      >
        Approve From Inside Graph
      </button>
    </div>
  ),
}));

vi.mock('@/lib/memoryApi', () => ({
  memoryApi: {
    list: vi.fn(),
    getCore: vi.fn(),
    getSummaries: vi.fn(),
    getConversations: vi.fn(),
    getPersona: vi.fn(),
    getSkills: vi.fn(),
    getConsent: vi.fn(),
    hasConsent: vi.fn(),
    recordConsent: vi.fn(),
    deleteAll: vi.fn(),
    forgetAllReflections: vi.fn(),
    add: vi.fn(),
    edit: vi.fn(),
    forget: vi.fn(),
    setCore: vi.fn(),
    reflect: vi.fn().mockResolvedValue({ status: 'ok' }),
  },
  MemoryApiError: class extends Error {},
}));

describe('MemoryManager Governance & Knowledge Graph Controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(memoryApi.list).mockResolvedValue({
      memories: [
        {
          id: 'm1',
          content: 'I observed feelings of anxiety during work meetings.',
          source: 'extracted',
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.mocked(memoryApi.getCore).mockResolvedValue(null);
    vi.mocked(memoryApi.getSummaries).mockResolvedValue([]);
    vi.mocked(memoryApi.getConversations).mockResolvedValue([]);
    vi.mocked(memoryApi.getPersona).mockResolvedValue({ content: '', updated_at: '' });
    vi.mocked(memoryApi.getSkills).mockResolvedValue([]);
    vi.mocked(memoryApi.getConsent).mockResolvedValue(false);
    vi.mocked(memoryApi.hasConsent).mockResolvedValue(false);
    vi.mocked(memoryApi.recordConsent).mockResolvedValue(undefined);
    vi.mocked(memoryApi.deleteAll).mockResolvedValue(undefined);
  });

  it('renders Approval Notification Banner when hasConsent is false/not approved', async () => {
    vi.mocked(memoryApi.getConsent).mockResolvedValue(false);

    render(<MemoryManager />);

    await waitFor(() => {
      expect(
        screen.getByText(/personal spiritual memory is paused \/ not approved/i),
      ).toBeInTheDocument();
    });

    expect(screen.getByText(/private & encrypted/i)).toBeInTheDocument();
    expect(
      screen.getByText(/allow mukthi guru to remember your reflections and inquiries/i),
    ).toBeInTheDocument();

    const approveBtn = screen.getByRole('button', { name: /approve & enable memory/i });
    expect(approveBtn).toBeInTheDocument();

    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(true);
    });
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringMatching(/memory enabled/i),
      }),
    );
  });

  it('displays Paused status pill when hasConsent is false and toggles to active on click', async () => {
    vi.mocked(memoryApi.getConsent).mockResolvedValue(false);

    render(<MemoryManager />);

    await waitFor(() => {
      expect(screen.getByText(/⏸️ paused/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/⏸️ paused/i));

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(true);
    });
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringMatching(/memory active/i),
      }),
    );
  });

  it('displays Active status pill when hasConsent is true and toggles to paused on click', async () => {
    vi.mocked(memoryApi.getConsent).mockResolvedValue(true);

    render(<MemoryManager />);

    await waitFor(() => {
      expect(screen.getByText(/🟢 active/i)).toBeInTheDocument();
    });

    // Approval notification banner should NOT be rendered when active
    expect(
      screen.queryByText(/personal spiritual memory is paused \/ not approved/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/🟢 active/i));

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(false);
    });
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringMatching(/memory paused/i),
      }),
    );
  });

  it('provides Delete Entirely button that permanently erases memories and wisdom map across stores', async () => {
    vi.mocked(memoryApi.getConsent).mockResolvedValue(true);

    render(<MemoryManager />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /delete entirely/i })).toBeInTheDocument();
    });

    // Click Delete Entirely to open AlertDialog
    fireEvent.click(screen.getByRole('button', { name: /delete entirely/i }));

    // Verify AlertDialog contents
    await waitFor(() => {
      expect(
        screen.getByText(/erase all memories & wisdom map\?/i),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(
        /this permanently deletes all your personal reflections, guiding notes, and knowledge graph connections across qdrant, neo4j, and supabase/i,
      ),
    ).toBeInTheDocument();

    // Confirm deletion
    const confirmBtn = screen.getByRole('button', { name: /^delete$/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(memoryApi.deleteAll).toHaveBeenCalledTimes(1);
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(false);
    });

    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringMatching(/memories erased/i),
        description: expect.stringMatching(
          /all personal memories and wisdom map connections have been permanently erased/i,
        ),
      }),
    );
  });

  it('passes scope="personal", hasConsent, and onApproveConsent to KGConceptMap in graph view', async () => {
    vi.mocked(memoryApi.getConsent).mockResolvedValue(false);

    render(<MemoryManager />);

    await waitFor(() => {
      expect(screen.getByTestId('kg-concept-map')).toBeInTheDocument();
    });

    const kgMap = screen.getByTestId('kg-concept-map');
    expect(kgMap.getAttribute('data-scope')).toBe('personal');
    expect(kgMap.getAttribute('data-has-consent')).toBe('false');

    // Trigger approve from inside the graph component
    const kgApproveBtn = screen.getByTestId('kg-approve-consent-btn');
    fireEvent.click(kgApproveBtn);

    await waitFor(() => {
      expect(memoryApi.recordConsent).toHaveBeenCalledWith(true);
    });
  });
});
