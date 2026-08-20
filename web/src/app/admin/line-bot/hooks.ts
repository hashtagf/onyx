"use client";

import useSWR from "swr";
import { LineBotConfig } from "@/app/admin/line-bot/types";

const BASE_URL = "/api/manage/admin/line-bot";

/**
 * Custom fetcher for bot config that handles 403 specially.
 * 403 means bot config is managed externally (Cloud or env vars).
 */
async function botConfigFetcher(url: string): Promise<LineBotConfig | null> {
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
 * Hook for bot config. Returns null when managed externally (Cloud/env vars).
 */
export function useLineBotConfig() {
  const url = `${BASE_URL}/config`;
  const swrResponse = useSWR<LineBotConfig | null>(url, botConfigFetcher);
  return {
    ...swrResponse,
    // null = managed externally (403), undefined = loading
    isManaged: swrResponse.data === null,
    refreshBotConfig: () => swrResponse.mutate(),
  };
}
