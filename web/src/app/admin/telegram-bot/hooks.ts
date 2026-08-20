"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  TelegramBotConfig,
  TelegramChatConfig,
} from "@/app/admin/telegram-bot/types";

const BASE_URL = "/api/manage/admin/telegram-bot";

/**
 * Custom fetcher for bot config that handles 403 specially.
 * 403 means bot config is managed externally (Cloud or env var).
 */
async function botConfigFetcher(
  url: string
): Promise<TelegramBotConfig | null> {
  const res = await fetch(url);

  if (res.status === 403) {
    return null;
  }

  if (!res.ok) {
    throw new Error("Failed to fetch bot config");
  }

  return res.json();
}

/**
 * Hook for bot config. Returns null when managed externally (Cloud/env var).
 */
export function useTelegramBotConfig() {
  const url = `${BASE_URL}/config`;
  const swrResponse = useSWR<TelegramBotConfig | null>(url, botConfigFetcher);
  return {
    ...swrResponse,
    // null = managed externally (403), undefined = loading
    isManaged: swrResponse.data === null,
    refreshBotConfig: () => swrResponse.mutate(),
  };
}

export function useTelegramChats() {
  const url = `${BASE_URL}/chats`;
  const swrResponse = useSWR<TelegramChatConfig[]>(url, errorHandlingFetcher);
  return {
    ...swrResponse,
    refreshChats: () => swrResponse.mutate(),
  };
}
