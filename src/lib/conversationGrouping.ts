import type { Conversation } from '@/lib/chatStorage';

export type GroupLabel = 'Today' | 'Yesterday' | 'Previous 7 days' | 'Older';

export interface ConversationGroup {
  label: GroupLabel;
  conversations: Conversation[];
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function daysAgo(n: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = daysAgo(1);
  const lastWeekStart = daysAgo(7);

  const groups: Record<GroupLabel, Conversation[]> = {
    Today: [],
    Yesterday: [],
    'Previous 7 days': [],
    Older: [],
  };

  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );

  for (const conv of sorted) {
    const date = new Date(conv.updatedAt);
    if (isSameDay(date, now)) {
      groups.Today.push(conv);
    } else if (isSameDay(date, yesterdayStart)) {
      groups.Yesterday.push(conv);
    } else if (date >= lastWeekStart) {
      groups['Previous 7 days'].push(conv);
    } else {
      groups.Older.push(conv);
    }
  }

  return (Object.entries(groups) as [GroupLabel, Conversation[]][])
    .filter(([, convs]) => convs.length > 0)
    .map(([label, conversations]) => ({ label, conversations }));
}
