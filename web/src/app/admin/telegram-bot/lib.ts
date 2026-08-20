import {
  TelegramBotConfig,
  TelegramBotConfigUpdate,
  TelegramChatConfig,
  TelegramChatConfigUpdate,
} from "@/app/admin/telegram-bot/types";

const BASE_URL = "/api/manage/admin/telegram-bot";

// === Bot Config (Self-hosted only) ===

export async function createBotConfig(
  botToken: string
): Promise<TelegramBotConfig> {
  const response = await fetch(`${BASE_URL}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: botToken }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to create bot config");
  }
  return response.json();
}

export async function updateBotConfig(
  update: TelegramBotConfigUpdate
): Promise<TelegramBotConfig> {
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

// === Chat Config ===

export async function updateChatConfig(
  chatConfigId: number,
  update: TelegramChatConfigUpdate
): Promise<TelegramChatConfig> {
  const response = await fetch(`${BASE_URL}/chats/${chatConfigId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update chat config");
  }
  return response.json();
}

export async function deleteChatConfig(chatConfigId: number): Promise<void> {
  const response = await fetch(`${BASE_URL}/chats/${chatConfigId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to delete chat config");
  }
}
