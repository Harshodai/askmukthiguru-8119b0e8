import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  saveFeedback,
  clearLocalChatData,
  loadAllFeedback,
  saveConversation,
  loadConversations,
  deleteConversation,
  createNewConversation,
  getConversationPreview,
  saveChatHistory,
  setIncognitoMode,
  formatRelativeTime,
  type MessageFeedback,
  type Conversation,
  type Message,
} from '@/lib/chatStorage';

describe('chatStorage', () => {
  beforeEach(() => {
    localStorage.clear();
    setIncognitoMode(false);
  });

  describe('Feedback', () => {
    it('saves and loads feedback', () => {
      const feedback: MessageFeedback = {
        vote: 'up',
        tags: ['Clear answer', 'Insightful'],
        comment: 'Very helpful!',
        timestamp: new Date('2026-05-05'),
      };
      saveFeedback('msg-1', feedback);
      const all = loadAllFeedback();
      expect(all['msg-1']).toBeDefined();
      expect(all['msg-1'].vote).toBe('up');
      expect(all['msg-1'].tags).toEqual(['Clear answer', 'Insightful']);
      expect(all['msg-1'].comment).toBe('Very helpful!');
    });

    it('does not persist feedback while Temporary Chat is active', () => {
      setIncognitoMode(true);
      saveFeedback('temporary-message', {
        vote: 'up',
        tags: ['Helpful'],
        comment: 'Temporary feedback must not persist',
        timestamp: new Date(),
      });

      expect(loadAllFeedback()).toEqual({});
      expect(localStorage.getItem('askmukthiguru_feedback')).toBeNull();
    });

    it('overwrites existing feedback for same message', () => {
      saveFeedback('msg-1', { vote: 'up', tags: [], timestamp: new Date() });
      saveFeedback('msg-1', { vote: 'down', tags: ['Could improve'], timestamp: new Date() });
      const all = loadAllFeedback();
      expect(all['msg-1'].vote).toBe('down');
    });
  });

  it('clears cached chat and feedback data for an identity transition', async () => {
    localStorage.setItem('askmukthiguru_chat_history', '[]');
    localStorage.setItem('askmukthiguru_conversations', '[]');
    localStorage.setItem('askmukthiguru_current_conversation', 'conversation-1');
    localStorage.setItem('askmukthiguru_feedback', '{}');

    await clearLocalChatData();

    expect(localStorage.getItem('askmukthiguru_chat_history')).toBeNull();
    expect(localStorage.getItem('askmukthiguru_conversations')).toBeNull();
    expect(localStorage.getItem('askmukthiguru_current_conversation')).toBeNull();
    expect(localStorage.getItem('askmukthiguru_feedback')).toBeNull();
  });

  describe('Conversations', () => {
    it('creates a new conversation with correct defaults', () => {
      const conv = createNewConversation();
      expect(conv.id).toBeDefined();
      expect(conv.messages).toEqual([]);
      expect(conv.messageCount).toBe(0);
      expect(conv.isTemporary).toBeUndefined();
    });

    it('marks conversation as temporary when incognito mode is active even without options', () => {
      setIncognitoMode(true);
      try {
        const conv = createNewConversation();
        expect(conv.isTemporary).toBe(true);
      } finally {
        setIncognitoMode(false);
      }
    });

    it('filters out temporary conversations when loading from storage', async () => {
      // Simulate raw storage having a temporary conversation (defense-in-depth)
      const convs = [
        { id: '11111111-1111-4111-8111-111111111111', startedAt: new Date().toISOString(), updatedAt: new Date().toISOString(), preview: 'Normal', messageCount: 0, messages: [] },
        { id: '22222222-2222-4222-8222-222222222222', startedAt: new Date().toISOString(), updatedAt: new Date().toISOString(), preview: 'Temp', messageCount: 0, messages: [], isTemporary: true }
      ];
      localStorage.setItem('askmukthiguru_conversations', JSON.stringify(convs));
      localStorage.setItem('askmukthiguru_current_conversation', '22222222-2222-4222-8222-222222222222');
      const loaded = await loadConversations();
      expect(loaded).toHaveLength(1);
      expect(loaded[0].id).toBe('11111111-1111-4111-8111-111111111111');
      expect(JSON.parse(localStorage.getItem('askmukthiguru_conversations')!)).toEqual([convs[0]]);
      expect(localStorage.getItem('askmukthiguru_current_conversation')).toBeNull();
    });

    it('saves and loads conversations', async () => {
      const conv = createNewConversation();
      conv.preview = 'Test preview';
      await saveConversation(conv);
      const loaded = await loadConversations();
      expect(loaded).toHaveLength(1);
      expect(loaded[0].preview).toBe('Test preview');
    });

    it('auto-tags isTemporary when incognito mode is active', () => {
      setIncognitoMode(true);
      const conv = createNewConversation();
      expect(conv.isTemporary).toBe(true);
      setIncognitoMode(false);
      const normalConv = createNewConversation();
      expect(normalConv.isTemporary).toBeUndefined();
    });

    it('never persists a temporary conversation after temporary mode closes', async () => {
      const temporary = createNewConversation({ temporary: true });
      temporary.preview = 'A private temporary-chat title';

      // This models delayed title generation completing after the UI has
      // already left temporary mode.  Persistence must be denied by the
      // conversation itself, not just a mutable global mode flag.
      await saveConversation(temporary);

      expect(await loadConversations()).toEqual([]);
      expect(localStorage.getItem('askmukthiguru_conversations')).toBeNull();
    });

    it('does not write legacy history while temporary mode is active', () => {
      setIncognitoMode(true);
      saveChatHistory([{ id: 'private-message', role: 'user', content: 'private', timestamp: new Date() }]);

      expect(localStorage.getItem('askmukthiguru_chat_history')).toBeNull();
    });

    it('keeps every local content store empty for a temporary conversation', async () => {
      setIncognitoMode(true);
      const temporary = createNewConversation({ temporary: true });
      temporary.preview = 'TEMPORARY-MARKER-DO-NOT-PERSIST';
      temporary.messages = [{
        id: 'temporary-message',
        role: 'user',
        content: 'TEMPORARY-MARKER-DO-NOT-PERSIST',
        timestamp: new Date(),
      }];

      setIncognitoMode(true);
      await saveConversation(temporary);
      saveChatHistory(temporary.messages);
      saveFeedback('temporary-message', { vote: 'down', tags: [], timestamp: new Date() });
      setIncognitoMode(false);

      expect(await loadConversations()).toEqual([]);
      expect(localStorage.getItem('askmukthiguru_conversations')).toBeNull();
      expect(localStorage.getItem('askmukthiguru_chat_history')).toBeNull();
      expect(localStorage.getItem('askmukthiguru_feedback')).toBeNull();
      expect(localStorage.getItem('askmukthiguru_current_conversation')).toBeNull();
      setIncognitoMode(false);
    });

    it('preserves normal history when temporary conversation is processed and cleaned up', async () => {
      const normal = createNewConversation();
      normal.preview = 'NORMAL-KEEP-CONVERSATION';
      normal.messages = [{
        id: 'normal-message-1',
        role: 'user',
        content: 'NORMAL-KEEP content',
        timestamp: new Date(),
      }];
      await saveConversation(normal);

      // Now create and attempt to save temporary conversation
      setIncognitoMode(true);
      const temporary = createNewConversation({ temporary: true });
      temporary.preview = 'TEMP-20261122-ALPHA-9471';
      temporary.messages = [{
        id: 'temp-msg-1',
        role: 'user',
        content: 'TEMP-20261122-ALPHA-9471 question',
        timestamp: new Date(),
      }];
      await saveConversation(temporary);
      setIncognitoMode(false);

      const loaded = await loadConversations();
      expect(loaded).toHaveLength(1);
      expect(loaded[0].preview).toBe('NORMAL-KEEP-CONVERSATION');
      expect(loaded[0].messages[0].content).toBe('NORMAL-KEEP content');
      expect(JSON.stringify(loaded)).not.toContain('TEMP-20261122-ALPHA-9471');
    });

    it('prevents mode-close race from persisting deferred title generation', async () => {
      // 1. Create temporary conversation while incognito
      setIncognitoMode(true);
      const temporary = createNewConversation({ temporary: true });
      expect(temporary.isTemporary).toBe(true);

      // 2. User closes temporary chat or switches to normal chat BEFORE title finishes
      setIncognitoMode(false);

      // 3. Deferred title generation completes and attempts to save
      temporary.preview = 'Delayed Title for TEMP-20261122-ALPHA-9471';
      temporary.messages = [{
        id: 'm-deferred',
        role: 'user',
        content: 'TEMP-20261122-ALPHA-9471',
        timestamp: new Date(),
      }];
      await saveConversation(temporary);

      // 4. Persistence must be blocked by conversation.isTemporary
      const loaded = await loadConversations();
      expect(loaded).toEqual([]);
      expect(localStorage.getItem('askmukthiguru_conversations')).toBeNull();
    });

    it('round-trips backend provenance metadata with a conversation', async () => {
      const conv = createNewConversation();
      conv.messages = [{
        id: 'guru-1',
        role: 'guru',
        content: 'Grounded answer',
        timestamp: new Date('2026-08-19T10:00:00.000Z'),
        citations: [{ url: 'https://example.com/teaching', title: 'The Teaching' }],
        citationsVerified: true,
        faithfulnessScore: 0.9,
        verification: { passed: true },
        provenanceManifest: { manifest_id: 'manifest-1' },
        releaseManifest: { release_id: 'release-1' },
        queryTier: 'tier2_simple',
      }];
      await saveConversation(conv);

      const loaded = await loadConversations();
      expect(loaded[0].messages[0]).toMatchObject({
        citationsVerified: true,
        faithfulnessScore: 0.9,
        verification: { passed: true },
        provenanceManifest: { manifest_id: 'manifest-1' },
        releaseManifest: { release_id: 'release-1' },
        queryTier: 'tier2_simple',
      });
    });

    it('round-trips public teaching evidence with a conversation', async () => {
      const conv = createNewConversation();
      conv.messages = [{
        id: 'guru-teaching-1',
        role: 'guru',
        content: 'Grounded answer',
        timestamp: new Date('2026-09-20T10:00:00.000Z'),
        teachingPreview: [{
          title: 'Awareness and the Beautiful State',
          teacher: 'Sri Preethaji',
          url: 'https://example.com/teaching',
          excerpt: 'A source-backed teaching excerpt.',
        }],
      }];
      await saveConversation(conv);

      const loaded = await loadConversations();
      expect(loaded[0].messages[0].teachingPreview).toEqual([{
        title: 'Awareness and the Beautiful State',
        teacher: 'Sri Preethaji',
        url: 'https://example.com/teaching',
        excerpt: 'A source-backed teaching excerpt.',
      }]);
    });

    it('deletes conversations', async () => {
      const conv = createNewConversation();
      await saveConversation(conv);
      expect(await loadConversations()).toHaveLength(1);
      await deleteConversation(conv.id);
      expect(await loadConversations()).toHaveLength(0);
    });

    it('getConversationPreview returns first user message', () => {
      const messages: Message[] = [
        { id: '1', role: 'guru', content: 'Welcome', timestamp: new Date() },
        { id: '2', role: 'user', content: 'What is meditation?', timestamp: new Date() },
      ];
      expect(getConversationPreview(messages)).toBe('What is meditation?');
    });

    it('getConversationPreview truncates long messages', () => {
      const longMsg = 'a'.repeat(100);
      const messages: Message[] = [
        { id: '1', role: 'user', content: longMsg, timestamp: new Date() },
      ];
      const preview = getConversationPreview(messages);
      expect(preview.length).toBeLessThanOrEqual(53); // 50 + '...'
    });
  });

  describe('formatRelativeTime', () => {
    it('returns Today for current date', () => {
      expect(formatRelativeTime(new Date())).toBe('Today');
    });

    it('returns Yesterday for yesterday', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      expect(formatRelativeTime(yesterday)).toBe('Yesterday');
    });
  });
});
