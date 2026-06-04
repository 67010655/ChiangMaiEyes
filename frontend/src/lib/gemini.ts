import type { DashboardResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export type ChatRole = 'user' | 'model';

export type ChatMessage = {
  role: ChatRole;
  text: string;
};

type AdvisorResponse = {
  text: string;
  source: string;
};

async function postAdvisor(path: string, body: unknown): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 25_000);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (response.status === 503) {
      throw new Error('ADVISOR_UNAVAILABLE');
    }
    if (!response.ok) {
      throw new Error(`Advisor API failed with ${response.status}`);
    }

    const data = (await response.json()) as AdvisorResponse;
    return data.text;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function generateDailyBriefing(dashboard: DashboardResponse): Promise<string> {
  return postAdvisor('/api/advisor/briefing', { dashboard });
}

export function chatWithAdvisor(
  dashboard: DashboardResponse,
  history: ChatMessage[],
  userMessage: string,
): Promise<string> {
  return postAdvisor('/api/advisor/chat', {
    dashboard,
    history,
    user_message: userMessage,
  });
}
