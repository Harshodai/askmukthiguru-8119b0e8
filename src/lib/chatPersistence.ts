import { supabase } from '@/integrations/supabase/client';
import type { Message } from './chatStorage';

// ── Types ──────────────────────────────────────────────────────────
export interface DbConversation {
  id: string;
  user_id: string;
  title: string | null;
  preview: string | null;
  created_at: string;
  updated_at: string;
}

// ── Auth helper ────────────────────────────────────────────────────
async function getAuthUserId(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.user?.id ?? null;
}

export async function isAuthenticated(): Promise<boolean> {
  return (await getAuthUserId()) !== null;
}

// ── Conversations ──────────────────────────────────────────────────
export async function loadConversationsFromDb(): Promise<DbConversation[]> {
  const userId = await getAuthUserId();
  if (!userId) return [];

  const { data, error } = await supabase
    .from('conversations')
    .select('*')
    .order('updated_at', { ascending: false })
    .limit(50);

  if (error) {
    console.error('Failed to load conversations from DB:', error);
    return [];
  }
  return data as DbConversation[];
}

export async function createConversationInDb(
  firstMessage: Message,
): Promise<DbConversation | null> {
  const userId = await getAuthUserId();
  if (!userId) return null;

  const preview =
    firstMessage.role === 'user'
      ? firstMessage.content.slice(0, 100)
      : 'New conversation';

  const { data, error } = await supabase
    .from('conversations')
    .insert({
      user_id: userId,
      title: preview.slice(0, 60),
      preview,
    })
    .select()
    .single();

  if (error) {
    console.error('Failed to create conversation in DB:', error);
    return null;
  }
  return data as DbConversation;
}

export async function updateConversationPreview(
  conversationId: string,
  preview: string,
): Promise<void> {
  await supabase
    .from('conversations')
    .update({ preview: preview.slice(0, 100), updated_at: new Date().toISOString() })
    .eq('id', conversationId);
}

export async function deleteConversationFromDb(id: string): Promise<void> {
  const { error } = await supabase.from('conversations').delete().eq('id', id);
  if (error) console.error('Failed to delete conversation:', error);
}

// ── Messages ───────────────────────────────────────────────────────
export async function loadMessagesFromDb(conversationId: string): Promise<Message[]> {
  const { data, error } = await supabase
    .from('chat_messages')
    .select('*')
    .eq('conversation_id', conversationId)
    .order('created_at', { ascending: true });

  if (error) {
    console.error('Failed to load messages:', error);
    return [];
  }

  return (data || []).map((row) => ({
    id: row.id,
    role: row.role as 'user' | 'guru',
    content: row.content,
    timestamp: new Date(row.created_at),
    citations: row.citations ?? undefined,
    confidenceScore: row.confidence_score ?? undefined,
  }));
}

export async function saveMessageToDb(
  conversationId: string,
  message: Message,
): Promise<void> {
  const { error } = await supabase.from('chat_messages').insert({
    conversation_id: conversationId,
    role: message.role,
    content: message.content,
    citations: message.citations ?? null,
    confidence_score: message.confidenceScore ?? null,
  });

  if (error) {
    console.error('Failed to save message to DB:', error);
  }

  // Update conversation preview + timestamp
  const preview =
    message.role === 'user'
      ? message.content.slice(0, 100)
      : undefined;

  if (preview) {
    await updateConversationPreview(conversationId, preview);
  } else {
    // At least bump updated_at
    await supabase
      .from('conversations')
      .update({ updated_at: new Date().toISOString() })
      .eq('id', conversationId);
  }
}
