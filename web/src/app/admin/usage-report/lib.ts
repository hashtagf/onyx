export const BASE_URL = "/api/manage/admin/usage-insights";

export function overviewUrl(days: number): string {
  return `${BASE_URL}/overview?days=${days}`;
}

export function chatHistoryUrl(
  days: number,
  page: number,
  pageSize: number,
  search: string
): string {
  const params = new URLSearchParams({
    days: String(days),
    page: String(page),
    page_size: String(pageSize),
  });
  if (search) {
    params.set("q", search);
  }
  return `${BASE_URL}/chat-history?${params.toString()}`;
}

export function sessionMessagesUrl(sessionId: string): string {
  return `${BASE_URL}/chat-history/${sessionId}`;
}

export function exportUrl(days: number): string {
  return `${BASE_URL}/export?days=${days}`;
}

export function formatCost(costCents: number): string {
  return `$${(costCents / 100).toFixed(2)}`;
}

export function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return String(tokens);
}
