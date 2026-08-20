"use client";

import { useState } from "react";
import { PageLoader } from "@opal/layouts";
import { ErrorCallout } from "@/components/ErrorCallout";
import { SettingsLayouts, ContentAction, toast } from "@opal/layouts";
import Card from "@/refresh-components/cards/Card";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { Switch } from "@opal/components";
import {
  useTelegramBotConfig,
  useTelegramChats,
} from "@/app/admin/telegram-bot/hooks";
import {
  updateBotConfig,
  updateChatConfig,
} from "@/app/admin/telegram-bot/lib";
import { TelegramChatsTable } from "@/app/admin/telegram-bot/TelegramChatsTable";
import { BotConfigCard } from "@/app/admin/telegram-bot/BotConfigCard";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminAgents } from "@/lib/agents/hooks";

const route = ADMIN_ROUTES.TELEGRAM_BOTS;

function TelegramBotContent() {
  const { data: chats, isLoading, error, refreshChats } = useTelegramChats();
  const {
    data: botConfig,
    isManaged,
    refreshBotConfig,
  } = useTelegramBotConfig();
  const { agents, isLoading: personasLoading } = useAdminAgents(
    false,
    false,
    true
  );
  const [isUpdating, setIsUpdating] = useState(false);

  const isBotAvailable = isManaged || botConfig?.configured === true;
  const isBotEnabled = isManaged || (botConfig?.enabled ?? false);

  const handleBotConfigUpdate = async (
    enabled: boolean,
    defaultPersonaId: number | null
  ) => {
    setIsUpdating(true);
    try {
      await updateBotConfig({
        enabled,
        default_persona_id: defaultPersonaId,
      });
      refreshBotConfig();
      toast.success("Bot settings updated");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to update bot settings"
      );
    } finally {
      setIsUpdating(false);
    }
  };

  const handleChatUpdate = async (
    chatConfigId: number,
    field: "enabled" | "require_bot_invocation" | "persona_override_id",
    value: boolean | number | null
  ) => {
    const chat = chats?.find((c) => c.id === chatConfigId);
    if (!chat) return;
    try {
      await updateChatConfig(chatConfigId, {
        enabled: chat.enabled,
        require_bot_invocation: chat.require_bot_invocation,
        persona_override_id: chat.persona_override_id,
        [field]: value,
      });
      refreshChats();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update chat");
    }
  };

  if (isLoading) {
    return <PageLoader />;
  }

  if (error || !chats) {
    return (
      <ErrorCallout
        errorTitle="Failed to load Telegram chats"
        errorMsg={error?.info?.detail || "An unknown error occurred"}
      />
    );
  }

  return (
    <>
      <BotConfigCard />

      {!isManaged && botConfig?.configured && (
        <Card variant="primary">
          <ContentAction
            title="Bot Enabled"
            description="Turn the Telegram bot on or off without deleting the token."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <Switch
                checked={botConfig.enabled}
                onCheckedChange={(checked) =>
                  handleBotConfigUpdate(checked, botConfig.default_persona_id)
                }
                disabled={isUpdating}
              />
            }
          />
          <ContentAction
            title="Default Agent"
            description="The agent used in all chats unless overridden."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <InputSelect
                value={botConfig.default_persona_id?.toString() ?? "default"}
                onValueChange={(value: string) =>
                  handleBotConfigUpdate(
                    botConfig.enabled,
                    value === "default" ? null : parseInt(value)
                  )
                }
                disabled={isUpdating || personasLoading}
              >
                <InputSelect.Trigger placeholder="Select agent" />
                <InputSelect.Content>
                  <InputSelect.Item value="default">
                    Default Agent
                  </InputSelect.Item>
                  {agents.map((persona) => (
                    <InputSelect.Item
                      key={persona.id}
                      value={persona.id.toString()}
                    >
                      {persona.name}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            }
          />
        </Card>
      )}

      <Card variant={!isBotAvailable ? "disabled" : "primary"}>
        <ContentAction
          title="Chats"
          description="Chats are discovered automatically when the bot receives a message. Enable the ones the bot should answer in."
          sizePreset="main-content"
          variant="section"
        />
        <TelegramChatsTable
          chats={chats}
          personas={agents}
          onChatUpdate={handleChatUpdate}
          disabled={!isBotAvailable || !isBotEnabled}
        />
      </Card>
    </>
  );
}

export default function Page() {
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        description="Connect Onyx to Telegram. Users can ask questions in direct messages or group chats."
      />
      <SettingsLayouts.Body>
        <TelegramBotContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
