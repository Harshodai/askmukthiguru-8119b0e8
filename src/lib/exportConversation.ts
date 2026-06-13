import type { Conversation, Message } from '@/lib/chatStorage';

const fmtTime = (d: Date | string) => {
  const date = typeof d === 'string' ? new Date(d) : d;
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
};

const roleLabel = (role: Message['role']) =>
  role === 'user' ? '🧘 Seeker' : role === 'guru' ? '🕉️ Guru' : '⚙️ System';

export const conversationToMarkdown = (conversation: Conversation): string => {
  const lines: string[] = [];
  const title = conversation.preview?.trim() || 'Conversation with AskMukthiGuru';
  lines.push(`# ${title}`);
  lines.push('');
  lines.push(`_Exported from AskMukthiGuru on ${new Date().toLocaleString()}_`);
  if (conversation.updatedAt) {
    lines.push(`_Last activity: ${fmtTime(conversation.updatedAt)}_`);
  }
  lines.push('');
  lines.push('---');
  lines.push('');

  for (const msg of conversation.messages ?? []) {
    if (!msg?.content?.trim()) continue;
    lines.push(`### ${roleLabel(msg.role)}  ·  ${fmtTime(msg.timestamp)}`);
    lines.push('');
    lines.push(msg.content.trim());
    if (msg.citations && msg.citations.length > 0) {
      lines.push('');
      lines.push('**Sources:**');
      for (const c of msg.citations) {
        const label = (c as { title?: string; source?: string }).title
          ?? (c as { source?: string }).source
          ?? String(c);
        lines.push(`- ${label}`);
      }
    }
    lines.push('');
  }

  lines.push('---');
  lines.push('');
  lines.push(
    '> AskMukthiGuru is an AI companion grounded in the teachings of Sri Preethaji & Sri Krishnaji. ' +
      'It is not a substitute for professional mental-health care.',
  );
  return lines.join('\n');
};

export const downloadConversationAsMarkdown = (conversation: Conversation) => {
  const md = conversationToMarkdown(conversation);
  const safeTitle = (conversation.preview || 'conversation')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48) || 'conversation';
  const stamp = new Date().toISOString().slice(0, 10);
  const filename = `mukthiguru-${safeTitle}-${stamp}.md`;
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return filename;
};
