/**
 * Saved answers and personal collections storage (FR-SAVE-01, T6-04).
 * Allows seekers to save a clip answer to a personal collection (e.g. "Favorites", "Practice", "Wisdom on Fear")
 * with personal notes, and revisit later.
 */

export interface SavedAnswerCitation {
  url: string;
  title?: string;
  speaker?: string;
  quote?: string;
  videoId?: string;
  sourceSpanId?: string;
}

export interface SavedAnswerItem {
  id: string;
  messageId: string;
  question: string;
  answerText: string;
  collectionName: string;
  notes?: string;
  createdAt: string;
  citations: SavedAnswerCitation[];
}

const STORAGE_KEY = 'askmukthiguru_saved_answers_v1';
const EVENT_NAME = 'saved_answers:updated';

export const loadSavedAnswers = (): SavedAnswerItem[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export const saveAnswerItem = (item: SavedAnswerItem): void => {
  try {
    const current = loadSavedAnswers();
    const updated = [item, ...current.filter((i) => i.id !== item.id)];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: updated }));
    }
  } catch (err) {
    console.error('Failed to save answer locally', err);
  }
};

export const deleteSavedAnswerItem = (id: string): void => {
  try {
    const current = loadSavedAnswers();
    const filtered = current.filter((i) => i.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: filtered }));
    }
  } catch (err) {
    console.error('Failed to delete saved answer locally', err);
  }
};

export const getSavedCollections = (): string[] => {
  const items = loadSavedAnswers();
  const collections = new Set<string>(['Favorites']);
  for (const item of items) {
    if (item.collectionName) {
      collections.add(item.collectionName);
    }
  }
  return Array.from(collections);
};
