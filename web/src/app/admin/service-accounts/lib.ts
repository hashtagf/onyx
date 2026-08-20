import {
  ApiKeyDescriptor,
  ApiKeyRole,
} from "@/app/admin/service-accounts/types";

const BASE_URL = "/api/admin/api-key";

async function orThrow(response: Response, action: string): Promise<Response> {
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || `Failed to ${action}`);
  }
  return response;
}

export async function createApiKey(
  name: string,
  role: ApiKeyRole
): Promise<ApiKeyDescriptor> {
  const response = await fetch(BASE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, role }),
  });
  return (await orThrow(response, "create key")).json();
}

export async function regenerateApiKey(
  apiKeyId: number
): Promise<ApiKeyDescriptor> {
  const response = await fetch(`${BASE_URL}/${apiKeyId}/regenerate`, {
    method: "POST",
  });
  return (await orThrow(response, "regenerate key")).json();
}

export async function renameApiKey(
  apiKeyId: number,
  name: string,
  role: ApiKeyRole
): Promise<ApiKeyDescriptor> {
  const response = await fetch(`${BASE_URL}/${apiKeyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, role }),
  });
  return (await orThrow(response, "rename key")).json();
}

export async function deleteApiKey(apiKeyId: number): Promise<void> {
  await orThrow(
    await fetch(`${BASE_URL}/${apiKeyId}`, { method: "DELETE" }),
    "delete key"
  );
}
