export interface LineBotConfig {
  configured: boolean;
  enabled: boolean;
  default_persona_id: number | null;
  respond_to_dms: boolean;
  require_mention_in_groups: boolean;
  created_at: string | null;
}

export interface LineBotConfigUpdate {
  enabled: boolean;
  default_persona_id: number | null;
  respond_to_dms: boolean;
  require_mention_in_groups: boolean;
}
