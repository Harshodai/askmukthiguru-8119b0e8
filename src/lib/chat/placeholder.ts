import { guruResponses } from '@/lib/chatStorage';

export function getPlaceholderResponse(): string {
  const randomIndex = Math.floor(Math.random() * guruResponses.length);
  return guruResponses[randomIndex];
}

export async function placeholderReply(): Promise<{ content: string }> {
  await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 1000));
  return { content: getPlaceholderResponse() };
}
