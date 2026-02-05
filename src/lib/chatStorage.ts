export interface Message {
  id: string;
  role: 'user' | 'guru';
  content: string;
  timestamp: Date;
}

const STORAGE_KEY = 'askmukthiguru_chat_history';

export const generateId = (): string => {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
};

export const saveChatHistory = (messages: Message[]): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch (error) {
    console.error('Failed to save chat history:', error);
  }
};

export const loadChatHistory = (): Message[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const messages = JSON.parse(stored);
      return messages.map((msg: Message) => ({
        ...msg,
        timestamp: new Date(msg.timestamp),
      }));
    }
  } catch (error) {
    console.error('Failed to load chat history:', error);
  }
  return [];
};

export const clearChatHistory = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear chat history:', error);
  }
};

// Placeholder responses from the Gurus
export const guruResponses: string[] = [
  "When you are in a beautiful state, you don't just experience life - you become life itself. The separation between you and existence dissolves.",
  "The mind that suffers is the mind that resists what is. Acceptance is not resignation - it is awakening to the present moment.",
  "Your thoughts are not you. They are clouds passing through the sky of consciousness. Watch them, but do not become them.",
  "The heart that is connected feels no isolation. In connection, there is no suffering. In disconnection lies all pain.",
  "Every conflict outside is a reflection of conflict within. When inner peace dawns, outer peace follows naturally.",
  "The beautiful state is not something to achieve - it is what remains when the suffering state is seen through.",
  "When you stop fighting with life, life starts flowing through you. This is the secret of effortless living.",
  "Consciousness is not something you have - it is what you are. Realize this, and the search ends.",
  "The greatest gift you can give another is your own beautiful state. From this state, all right action flows.",
  "Suffering is not what happens to you - it is your relationship with what happens. Transform the relationship, transform the experience.",
];

export const getPlaceholderResponse = (): string => {
  const randomIndex = Math.floor(Math.random() * guruResponses.length);
  return guruResponses[randomIndex];
};
