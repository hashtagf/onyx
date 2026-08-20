"use client";

import { useState } from "react";
import { Section } from "@/layouts/general-layouts";
import Text from "@/refresh-components/texts/Text";
import { Button, Card, PasswordInputTypeIn } from "@opal/components";
import { Badge } from "@/components/ui/badge";
import SvgSimpleLoader from "@opal/icons/simple-loader";
import { useTelegramBotConfig } from "@/app/admin/telegram-bot/hooks";
import { createBotConfig, deleteBotConfig } from "@/app/admin/telegram-bot/lib";
import { toast } from "@opal/layouts";
import { ConfirmEntityModal } from "@/sections/modals/ConfirmEntityModal";
import { getFormattedDateTime } from "@/lib/dateUtils";

export function BotConfigCard() {
  const {
    data: botConfig,
    isLoading,
    isManaged,
    refreshBotConfig,
  } = useTelegramBotConfig();

  const [botToken, setBotToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Don't render anything if managed externally (Cloud or env var)
  if (isManaged) {
    return null;
  }

  if (isLoading) {
    return (
      <Card border="solid" rounding="lg">
        <Section alignItems="start" height="fit">
          <Text mainContentEmphasis text05>
            Bot Token
          </Text>
          <div className="flex justify-center">
            <SvgSimpleLoader className="h-6 w-6" />
          </div>
        </Section>
      </Card>
    );
  }

  const isConfigured = botConfig?.configured ?? false;

  const handleSaveToken = async () => {
    if (!botToken.trim()) {
      toast.error("Please enter a bot token");
      return;
    }

    setIsSubmitting(true);
    try {
      await createBotConfig(botToken.trim());
      setBotToken("");
      refreshBotConfig();
      toast.success("Bot token saved successfully");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save bot token"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteToken = async () => {
    setIsSubmitting(true);
    try {
      await deleteBotConfig();
      refreshBotConfig();
      toast.success("Bot token deleted");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete bot token"
      );
    } finally {
      setIsSubmitting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <>
      {showDeleteConfirm && (
        <ConfirmEntityModal
          danger
          entityType="Telegram bot token"
          entityName="Telegram Bot Token"
          onClose={() => setShowDeleteConfirm(false)}
          onSubmit={handleDeleteToken}
          additionalDetails="This will disconnect your Telegram bot. You will need to re-enter the token to use the bot again."
        />
      )}
      <Card border="solid" rounding="lg">
        <Section alignItems="start" height="fit">
          <Section flexDirection="row" justifyContent="between">
            <Section flexDirection="row" gap={2} width="fit">
              <Text mainContentEmphasis text05>
                Bot Token
              </Text>
              {isConfigured ? (
                <Badge variant="success">Configured</Badge>
              ) : (
                <Badge variant="secondary">Not Configured</Badge>
              )}
            </Section>
            {isConfigured && (
              <Button
                disabled={isSubmitting}
                variant="danger"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Delete Telegram Token
              </Button>
            )}
          </Section>

          {isConfigured ? (
            <Section flexDirection="column" alignItems="start" gap={2}>
              <Text text03 secondaryBody>
                Your Telegram bot token is configured.
                {botConfig?.created_at && (
                  <>
                    {" "}
                    Added {getFormattedDateTime(new Date(botConfig.created_at))}
                    .
                  </>
                )}
              </Text>
              <Text text03 secondaryBody>
                To change the token, delete the current one and add a new one.
              </Text>
            </Section>
          ) : (
            <Section flexDirection="column" alignItems="start" gap={3}>
              <Text text03 secondaryBody>
                Enter your Telegram bot token to enable the bot. Create a bot
                and get its token from @BotFather. Use a different bot than the
                Telegram connector — Telegram allows only one reader per bot.
              </Text>
              <Section flexDirection="row" alignItems="end" gap={2}>
                <PasswordInputTypeIn
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder="Enter bot token..."
                  disabled={isSubmitting}
                />
                <Button
                  disabled={isSubmitting || !botToken.trim()}
                  onClick={handleSaveToken}
                >
                  {isSubmitting ? "Saving..." : "Save Token"}
                </Button>
              </Section>
            </Section>
          )}
        </Section>
      </Card>
    </>
  );
}
