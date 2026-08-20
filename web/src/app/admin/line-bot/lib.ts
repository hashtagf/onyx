import { LineBotConfig, LineBotConfigUpdate } from "@/app/admin/line-bot/types";

const BASE_URL = "/api/manage/admin/line-bot";

export async function createBotConfig(
  channelAccessToken: string,
  channelSecret: string
): Promise<LineBotConfig> {
  const response = await fetch(`${BASE_URL}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel_access_token: channelAccessToken,
      channel_secret: channelSecret,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to create bot config");
  }
  return response.json();
}

export async function updateBotConfig(
  update: LineBotConfigUpdate
): Promise<LineBotConfig> {
  const response = await fetch(`${BASE_URL}/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update bot config");
  }
  return response.json();
}

export async function deleteBotConfig(): Promise<void> {
  const response = await fetch(`${BASE_URL}/config`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error("Failed to delete bot config");
  }
}
