import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  saveFeedback,
  loadAllFeedback,
  saveConversation,
  loadConversations,
  deleteConversation,
  createNewConversation,
  getConversationPreview,
  formatRelativeTime,
  type MessageFeedback,
  type Conversation,
  type Message,
} from '@/lib/chatStorage';

describe('chatStorage', () => {
  beforeEach(() => {
    localStorage.clear();
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

    it('overwrites existing feedback for same message', () => {
      saveFeedback('msg-1', { vote: 'up', tags: [], timestamp: new Date() });
      saveFeedback('msg-1', { vote: 'down', tags: ['Could improve'], timestamp: new Date() });
      const all = loadAllFeedback();
      expect(all['msg-1'].vote).toBe('down');
    });
  });

  describe('Conversations', () => {
    it('creates a new conversation with correct defaults', () => {
      const conv = createNewConversation();
      expect(conv.id).toBeDefined();
      expect(conv.messages).toEqual([]);
      expect(conv.messageCount).toBe(0);
    });

    it('saves and loads conversations', () => {
      const conv = createNewConversation();
      conv.preview = 'Test preview';
      saveConversation(conv);
      const loaded = loadConversations();
      expect(loaded).toHaveLength(1);
      expect(loaded[0].preview).toBe('Test preview');
    });

    it('deletes conversations', () => {
      const conv = createNewConversation();
      saveConversation(conv);
      expect(loadConversations()).toHaveLength(1);
      deleteConversation(conv.id);
      expect(loadConversations()).toHaveLength(0);
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
