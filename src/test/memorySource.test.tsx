import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n';
import { MemorySourceLink } from '@/components/common/MemorySourceLink';
import { memorySourceHref, normalizeSourceRef } from '@/lib/memorySource';
import { isMissingColumnError, sanitizeSourceConversationId } from '../../supabase/functions/_shared/memorySource';

const apiMocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  from: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: { getSession: apiMocks.getSession },
    from: apiMocks.from,
  },
}));

vi.mock('../lib/backendUrl', () => ({ BACKEND_URL: 'https://backend.test' }));

import { memoryApi } from '@/lib/memoryApi';

const ID = '3f2b8c1e-9a4d-4e6f-8a1b-2c3d4e5f6a7b';

describe('memorySourceHref', () => {
  it('links a conversation to the chat deep link and keeps the way back', () => {
    expect(memorySourceHref({ kind: 'conversation', id: ID })).toBe(`/chat?conversation=${ID}`);
    expect(memorySourceHref({ kind: 'conversation', id: ID }, '/profile?tab=memory')).toBe(
      `/chat?conversation=${ID}&returnTo=${encodeURIComponent('/profile?tab=memory')}`,
    );
  });

  it('links a notebook source to the notebook page', () => {
    expect(memorySourceHref({ kind: 'notebook', id: 'item-1' })).toBe('/notebooks');
  });

  it('never invents a link for unknown kinds, missing or malformed sources', () => {
    expect(memorySourceHref(null)).toBeNull();
    expect(memorySourceHref(undefined)).toBeNull();
    expect(memorySourceHref({ kind: 'teaching', id: 'abc' })).toBeNull();
    expect(memorySourceHref({ kind: 'conversation', id: '../admin' })).toBeNull();
    expect(memorySourceHref({ kind: 'conversation', id: 'a b' })).toBeNull();
    expect(memorySourceHref({ kind: 'conversation', id: 'x'.repeat(201) })).toBeNull();
    expect(normalizeSourceRef({ kind: 5, id: ID })).toBeNull();
  });
});

describe('MemorySourceLink', () => {
  const renderLink = (source: Parameters<typeof MemorySourceLink>[0]['source']) =>
    render(
      <MemoryRouter initialEntries={['/profile?tab=memory']}>
        <I18nextProvider i18n={i18n}>
          <MemorySourceLink source={source} />
        </I18nextProvider>
      </MemoryRouter>,
    );

  it('renders a link to the original conversation', () => {
    renderLink({ kind: 'conversation', id: ID });
    const link = screen.getByTestId('memory-source-link');
    expect(link).toHaveAttribute(
      'href',
      `/chat?conversation=${ID}&returnTo=${encodeURIComponent('/profile?tab=memory')}`,
    );
    expect(link).toHaveTextContent(/open original conversation/i);
    expect(screen.queryByTestId('memory-source-unavailable')).not.toBeInTheDocument();
  });

  it.each([null, undefined, { kind: 'teaching', id: 'abc' }, { kind: 'conversation', id: '<x>' }])(
    'says "Source unavailable" and renders no link for %o',
    (source) => {
      renderLink(source as never);
      expect(screen.getByTestId('memory-source-unavailable')).toHaveTextContent(/source unavailable/i);
      expect(screen.queryByTestId('memory-source-link')).not.toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    },
  );
});

describe('memoryApi.list source mapping', () => {
  const selects: string[] = [];

  const chain = (impl: (columns: string) => { data: unknown; error: unknown; count: number }) => {
    apiMocks.from.mockImplementation(() => ({
      select: (columns: string) => {
        selects.push(columns);
        const result = impl(columns);
        const builder = {
          order: () => builder,
          range: () => Promise.resolve(result),
        };
        return builder;
      },
    }));
  };

  beforeEach(() => {
    selects.length = 0;
    apiMocks.getSession.mockResolvedValue({ data: { session: { access_token: 't' } }, error: null });
  });
  afterEach(() => vi.clearAllMocks());

  it('maps source_conversation_id to source_ref and leaves legacy rows null', async () => {
    chain(() => ({
      data: [
        { id: 'm1', content: 'I walk daily', source: 'extracted', created_at: 'x', source_conversation_id: ID },
        { id: 'm2', content: 'I live in Pune', source: 'extracted', created_at: 'y', source_conversation_id: null },
      ],
      error: null,
      count: 2,
    }));

    const res = await memoryApi.list();
    expect(res.memories[0].source_ref).toEqual({ kind: 'conversation', id: ID });
    expect(res.memories[1].source_ref).toBeNull();
    expect(res.memories[0]).not.toHaveProperty('source_conversation_id');
    expect(selects).toEqual(['id, content, source, created_at, source_conversation_id']);
  });

  it('retries without the source column when the migration is not applied yet', async () => {
    chain((columns) =>
      columns.includes('source_conversation_id')
        ? { data: null, error: { code: '42703', message: 'column does not exist' }, count: 0 }
        : {
            data: [{ id: 'm1', content: 'I walk daily', source: 'extracted', created_at: 'x' }],
            error: null,
            count: 1,
          },
    );

    const res = await memoryApi.list();
    expect(selects).toEqual([
      'id, content, source, created_at, source_conversation_id',
      'id, content, source, created_at',
    ]);
    expect(res.memories).toHaveLength(1);
    expect(res.memories[0].source_ref).toBeNull();
  });

  it('does not swallow unrelated database errors', async () => {
    chain(() => ({ data: null, error: { code: '42501', message: 'permission denied' }, count: 0 }));
    await expect(memoryApi.list()).rejects.toThrow(/permission denied/);
    expect(selects).toHaveLength(1);
  });
});

// The edge functions that write the column share this validator (Deno runs the
// same file); keep it in lockstep with the API and the frontend pattern.
describe('edge-function source id validation', () => {
  it('accepts ids the frontend can link and rejects the rest', () => {
    expect(sanitizeSourceConversationId(ID)).toBe(ID);
    expect(sanitizeSourceConversationId(`  ${ID} `)).toBe(ID);
    for (const bad of [undefined, null, 5, '', ' ', 'a b', '../x', 'x/y', '<script>', 'a'.repeat(201), '-lead']) {
      expect(sanitizeSourceConversationId(bad)).toBeNull();
    }
  });

  it('agrees with the frontend about what is linkable', () => {
    for (const id of [ID, 'conv_1', 'a.b:c-d', 'x'.repeat(200), 'a b', '../x']) {
      const stored = sanitizeSourceConversationId(id);
      const linkable = memorySourceHref({ kind: 'conversation', id }) !== null;
      expect(stored !== null).toBe(linkable);
    }
  });

  it('only treats a missing column as recoverable', () => {
    expect(isMissingColumnError({ code: '42703' })).toBe(true);
    expect(isMissingColumnError({ code: 'PGRST204' })).toBe(true);
    expect(isMissingColumnError({ code: '23505' })).toBe(false);
    expect(isMissingColumnError(null)).toBe(false);
  });
});
