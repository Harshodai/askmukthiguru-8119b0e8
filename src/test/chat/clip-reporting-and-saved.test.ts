import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadSavedAnswers,
  saveAnswerItem,
  deleteSavedAnswerItem,
  getSavedCollections,
  SavedAnswerItem,
} from '@/lib/savedAnswersStorage';

describe('T6-04 / FR-SAVE-01: Saved answers and collections storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('saves an answer to a personal collection and reads it back', () => {
    const item: SavedAnswerItem = {
      id: 'save-123',
      messageId: 'msg-456',
      question: 'How do I overcome anxiety?',
      answerText: 'In a beautiful state, fear dissolves...',
      collectionName: 'Peace & Stillness',
      notes: 'Listen to this during morning practice',
      createdAt: '2026-11-05T10:00:00Z',
      citations: [
        {
          url: 'https://youtube.com/watch?v=abc',
          title: 'Freedom from Fear',
          speaker: 'Sri Krishnaji',
          videoId: 'abc',
        },
      ],
    };

    saveAnswerItem(item);
    const saved = loadSavedAnswers();
    expect(saved).toHaveLength(1);
    expect(saved[0].id).toBe('save-123');
    expect(saved[0].collectionName).toBe('Peace & Stillness');
    expect(saved[0].notes).toBe('Listen to this during morning practice');
  });

  it('lists unique collection names with Favorites always present', () => {
    expect(getSavedCollections()).toContain('Favorites');

    saveAnswerItem({
      id: 'save-1',
      messageId: 'm1',
      question: 'q1',
      answerText: 'a1',
      collectionName: 'Meditation',
      createdAt: '2026-11-05T10:00:00Z',
      citations: [],
    });

    saveAnswerItem({
      id: 'save-2',
      messageId: 'm2',
      question: 'q2',
      answerText: 'a2',
      collectionName: 'Relationships',
      createdAt: '2026-11-05T10:01:00Z',
      citations: [],
    });

    const collections = getSavedCollections();
    expect(collections).toContain('Favorites');
    expect(collections).toContain('Meditation');
    expect(collections).toContain('Relationships');
  });

  it('deletes a saved answer by id', () => {
    saveAnswerItem({
      id: 'save-1',
      messageId: 'm1',
      question: 'q1',
      answerText: 'a1',
      collectionName: 'Favorites',
      createdAt: '2026-11-05T10:00:00Z',
      citations: [],
    });

    expect(loadSavedAnswers()).toHaveLength(1);
    deleteSavedAnswerItem('save-1');
    expect(loadSavedAnswers()).toHaveLength(0);
  });
});
