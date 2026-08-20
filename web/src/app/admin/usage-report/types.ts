export interface DailyActivity {
  date: string;
  messages: number;
  sessions: number;
  active_users: number;
}

export interface ModelUsageRow {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export interface UserUsageRow {
  email: string;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
}

export interface UsageOverview {
  days: number;
  total_messages: number;
  total_sessions: number;
  active_users: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_cents: number;
  feedback_positive: number;
  feedback_negative: number;
  daily: DailyActivity[];
  by_model: ModelUsageRow[];
  by_user: UserUsageRow[];
}

export interface ChatHistoryEntry {
  session_id: string;
  time_created: string;
  user_email: string | null;
  persona_name: string | null;
  description: string | null;
  message_count: number;
}

export interface ChatHistoryPage {
  total: number;
  page: number;
  page_size: number;
  entries: ChatHistoryEntry[];
}

export interface ChatHistoryMessage {
  id: number;
  message_type: "user" | "assistant" | "tool_call_response" | "system";
  time_sent: string;
  message: string;
  token_count: number;
  model_display_name: string | null;
}
