const BASE = "/api/manage/admin/ai-improvement";

export const improvementUrls = {
  targets: `${BASE}/targets`,
  versionsRoot: `${BASE}/versions`,
  versions: (type: string, id: string) =>
    `${BASE}/versions?target_type=${encodeURIComponent(type)}&target_id=${encodeURIComponent(id)}`,
  datasets: `${BASE}/datasets`,
  runs: `${BASE}/runs`,
  canaries: `${BASE}/canaries`,
};

export async function postJson<T>(url: string, body: unknown = {}): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
      message?: string;
    } | null;
    throw new Error(payload?.detail ?? payload?.message ?? "Request failed.");
  }
  return (await response.json()) as T;
}
