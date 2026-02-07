export interface Message {
  id: string;
  role: 'user' | 'guru';
  content: string;
  timestamp: Date;
}

export interface Conversation {
  id: string;
  startedAt: Date;
  updatedAt: Date;
  preview: string;
  messageCount: number;
  messages: Message[];
}

const STORAGE_KEY = 'askmukthiguru_chat_history';
const CONVERSATIONS_KEY = 'askmukthiguru_conversations';
const CURRENT_CONVERSATION_KEY = 'askmukthiguru_current_conversation';
const MAX_CONVERSATIONS = 10;

export const generateId = (): string => {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
};

// Legacy functions for backward compatibility
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

// Multi-conversation functions
export const saveConversation = (conversation: Conversation): void => {
  try {
    const conversations = loadConversations();
    const existingIndex = conversations.findIndex(c => c.id === conversation.id);
    
    if (existingIndex >= 0) {
      conversations[existingIndex] = conversation;
    } else {
      conversations.unshift(conversation);
    }
    
    // Keep only the last MAX_CONVERSATIONS
    const trimmed = conversations.slice(0, MAX_CONVERSATIONS);
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('Failed to save conversation:', error);
  }
};

export const loadConversations = (): Conversation[] => {
  try {
    const stored = localStorage.getItem(CONVERSATIONS_KEY);
    if (stored) {
      const conversations = JSON.parse(stored);
      return conversations.map((conv: Conversation) => ({
        ...conv,
        startedAt: new Date(conv.startedAt),
        updatedAt: new Date(conv.updatedAt),
        messages: conv.messages.map((msg: Message) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        })),
      }));
    }
  } catch (error) {
    console.error('Failed to load conversations:', error);
  }
  return [];
};

export const loadConversation = (id: string): Conversation | null => {
  try {
    const conversations = loadConversations();
    return conversations.find(c => c.id === id) || null;
  } catch (error) {
    console.error('Failed to load conversation:', error);
  }
  return null;
};

export const deleteConversation = (id: string): void => {
  try {
    const conversations = loadConversations();
    const filtered = conversations.filter(c => c.id !== id);
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('Failed to delete conversation:', error);
  }
};

export const getCurrentConversationId = (): string | null => {
  try {
    return localStorage.getItem(CURRENT_CONVERSATION_KEY);
  } catch (error) {
    return null;
  }
};

export const setCurrentConversationId = (id: string): void => {
  try {
    localStorage.setItem(CURRENT_CONVERSATION_KEY, id);
  } catch (error) {
    console.error('Failed to set current conversation:', error);
  }
};

export const createNewConversation = (): Conversation => {
  const id = generateId();
  const now = new Date();
  return {
    id,
    startedAt: now,
    updatedAt: now,
    preview: '',
    messageCount: 0,
    messages: [],
  };
};

export const getConversationPreview = (messages: Message[]): string => {
  const firstUserMessage = messages.find(m => m.role === 'user');
  if (firstUserMessage) {
    return firstUserMessage.content.length > 50
      ? firstUserMessage.content.substring(0, 50) + '...'
      : firstUserMessage.content;
  }
  return 'New conversation';
};

// Format relative time
export const formatRelativeTime = (date: Date): string => {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  return date.toLocaleDateString();
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
