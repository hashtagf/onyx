export type ApiKeyRole = "limited" | "basic" | "admin";

export interface ApiKeyDescriptor {
  api_key_id: number;
  api_key_role: ApiKeyRole;
  api_key_display: string;
  api_key_name: string | null;
  user_id: string;
  // Full key — only present in create/regenerate responses, shown once.
  api_key?: string;
}
