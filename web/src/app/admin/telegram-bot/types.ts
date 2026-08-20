export interface TelegramBotConfig {
  configured: boolean;
  enabled: boolean;
  default_persona_id: number | null;
  created_at: string | null;
}

export type TelegramChatType = "private" | "group" | "supergroup" | "channel";

export interface TelegramChatConfig {
  id: number;
  chat_id: number;
  chat_name: string;
  chat_type: TelegramChatType;
  require_bot_invocation: boolean;
  persona_override_id: number | null;
  enabled: boolean;
  first_seen_at: string;
}

export interface TelegramBotConfigUpdate {
  enabled: boolean;
  default_persona_id: number | null;
}

export interface TelegramChatConfigUpdate {
  enabled: boolean;
  require_bot_invocation: boolean;
  persona_override_id: number | null;
}
