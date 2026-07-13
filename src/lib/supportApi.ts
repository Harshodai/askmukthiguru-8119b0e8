import { BACKEND_URL_OR_LOCAL as API_BASE } from './backendUrl';

export interface SupportPayload {
  name: string;
  email: string;
  subject: string;
  message: string;
  category: string;
  attachments?: File[];
}

export async function submitSupportForm(payload: SupportPayload): Promise<{ ok: boolean; message: string }> {
  const form = new FormData();
  form.append('name', payload.name);
  form.append('email', payload.email);
  form.append('subject', payload.subject);
  form.append('message', payload.message);
  form.append('category', payload.category);

  if (payload.attachments) {
    for (const f of payload.attachments) {
      form.append('attachments', f);
    }
  }

  const res = await fetch(`${API_BASE}/api/support/contact`, {
    method: 'POST',
    body: form,
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to send message');
  }
  return data;
}
