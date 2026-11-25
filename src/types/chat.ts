/**
 * Public re-export of chat-domain types from lib/chatStorage so that
 * import paths like '@/types/chat' resolve without duplicating definitions.
 *
 * Keep this as a barrel — add no logic here.
 */
export type {
  Message,
  MessageError,
  MessageErrorKind,
  MessageFeedback,
  Conversation,
} from '@/lib/chatStorage';
