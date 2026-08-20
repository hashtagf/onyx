"use client";

import { useEffect, useState } from "react";
import { PageLoader } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import { SettingsLayouts, ContentAction, toast } from "@opal/layouts";
import Text from "@/refresh-components/texts/Text";
import Card from "@/refresh-components/cards/Card";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import {
  Button,
  CopyButton,
  PasswordInputTypeIn,
  Switch,
} from "@opal/components";
import { Badge } from "@/components/ui/badge";
import { useLineBotConfig } from "@/app/admin/line-bot/hooks";
import {
  createBotConfig,
  deleteBotConfig,
  updateBotConfig,
} from "@/app/admin/line-bot/lib";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminAgents } from "@/lib/agents/hooks";
import { ConfirmEntityModal } from "@/sections/modals/ConfirmEntityModal";
import { getFormattedDateTime } from "@/lib/dateUtils";

const route = ADMIN_ROUTES.LINE_BOTS;

function LineBotContent() {
  const {
    data: botConfig,
    isLoading,
    isManaged,
    refreshBotConfig,
  } = useLineBotConfig();
  const { agents, isLoading: personasLoading } = useAdminAgents(
    false,
    false,
    true
  );

  const [channelAccessToken, setChannelAccessToken] = useState("");
  const [channelSecret, setChannelSecret] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");

  useEffect(() => {
    setWebhookUrl(`${window.location.origin}/api/line/webhook`);
  }, []);

  if (isLoading) {
    return <PageLoader />;
  }

  const isConfigured = isManaged || (botConfig?.configured ?? false);

  const handleSaveCredentials = async () => {
    if (!channelAccessToken.trim() || !channelSecret.trim()) {
      toast.error("Please enter both the channel access token and secret");
      return;
    }

    setIsSubmitting(true);
    try {
      await createBotConfig(channelAccessToken.trim(), channelSecret.trim());
      setChannelAccessToken("");
      setChannelSecret("");
      refreshBotConfig();
      toast.success("LINE credentials saved successfully");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save credentials"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteCredentials = async () => {
    setIsSubmitting(true);
    try {
      await deleteBotConfig();
      refreshBotConfig();
      toast.success("LINE credentials deleted");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete credentials"
      );
    } finally {
      setIsSubmitting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleSettingUpdate = async (
    field:
      | "enabled"
      | "default_persona_id"
      | "respond_to_dms"
      | "require_mention_in_groups",
    value: boolean | number | null
  ) => {
    if (!botConfig) return;
    setIsSubmitting(true);
    try {
      await updateBotConfig({
        enabled: botConfig.enabled,
        default_persona_id: botConfig.default_persona_id,
        respond_to_dms: botConfig.respond_to_dms,
        require_mention_in_groups: botConfig.require_mention_in_groups,
        [field]: value,
      });
      refreshBotConfig();
      toast.success("Settings updated");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to update settings"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      {showDeleteConfirm && (
        <ConfirmEntityModal
          danger
          entityType="LINE credentials"
          entityName="LINE Channel Credentials"
          onClose={() => setShowDeleteConfirm(false)}
          onSubmit={handleDeleteCredentials}
          additionalDetails="This will disconnect your LINE Official Account. You will need to re-enter the credentials to use the bot again."
        />
      )}

      {!isManaged && (
        <Card variant="primary">
          <Section alignItems="start" height="fit">
            <Section flexDirection="row" justifyContent="between">
              <Section flexDirection="row" gap={2} width="fit">
                <Text mainContentEmphasis text05>
                  Channel Credentials
                </Text>
                {botConfig?.configured ? (
                  <Badge variant="success">Configured</Badge>
                ) : (
                  <Badge variant="secondary">Not Configured</Badge>
                )}
              </Section>
              {botConfig?.configured && (
                <Button
                  disabled={isSubmitting}
                  variant="danger"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  Delete Credentials
                </Button>
              )}
            </Section>

            {botConfig?.configured ? (
              <Section flexDirection="column" alignItems="start" gap={2}>
                <Text text03 secondaryBody>
                  Your LINE channel credentials are configured.
                  {botConfig?.created_at && (
                    <>
                      {" "}
                      Added{" "}
                      {getFormattedDateTime(new Date(botConfig.created_at))}.
                    </>
                  )}
                </Text>
                <Text text03 secondaryBody>
                  To change them, delete the current credentials and add new
                  ones.
                </Text>
              </Section>
            ) : (
              <Section flexDirection="column" alignItems="start" gap={3}>
                <Text text03 secondaryBody>
                  Enter the Messaging API channel access token and channel
                  secret of your LINE Official Account. You can find both in the
                  LINE Developers console.
                </Text>
                <Section flexDirection="row" alignItems="end" gap={2}>
                  <PasswordInputTypeIn
                    value={channelAccessToken}
                    onChange={(e) => setChannelAccessToken(e.target.value)}
                    placeholder="Channel access token..."
                    disabled={isSubmitting}
                  />
                  <PasswordInputTypeIn
                    value={channelSecret}
                    onChange={(e) => setChannelSecret(e.target.value)}
                    placeholder="Channel secret..."
                    disabled={isSubmitting}
                  />
                  <Button
                    disabled={
                      isSubmitting ||
                      !channelAccessToken.trim() ||
                      !channelSecret.trim()
                    }
                    onClick={handleSaveCredentials}
                  >
                    {isSubmitting ? "Saving..." : "Save"}
                  </Button>
                </Section>
              </Section>
            )}
          </Section>
        </Card>
      )}

      <Card variant={!isConfigured ? "disabled" : "primary"}>
        <ContentAction
          title="Webhook URL"
          description="Set this as the webhook URL in the LINE Developers console (Messaging API tab) and enable 'Use webhook'. The URL must be reachable from the internet over HTTPS."
          sizePreset="main-content"
          variant="section"
          rightChildren={<CopyButton getCopyText={() => webhookUrl} />}
        />
        <Text text03 secondaryMono>
          {webhookUrl}
        </Text>
      </Card>

      {!isManaged && botConfig?.configured && (
        <Card variant="primary">
          <ContentAction
            title="Bot Enabled"
            description="Turn the LINE bot on or off without deleting credentials."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <Switch
                checked={botConfig.enabled}
                onCheckedChange={(checked) =>
                  handleSettingUpdate("enabled", checked)
                }
                disabled={isSubmitting}
              />
            }
          />
          <ContentAction
            title="Respond to Direct Messages"
            description="Answer 1:1 chats with the Official Account."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <Switch
                checked={botConfig.respond_to_dms}
                onCheckedChange={(checked) =>
                  handleSettingUpdate("respond_to_dms", checked)
                }
                disabled={isSubmitting || !botConfig.enabled}
              />
            }
          />
          <ContentAction
            title="Require @mention in Groups"
            description="In group chats, answer only when the bot is mentioned."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <Switch
                checked={botConfig.require_mention_in_groups}
                onCheckedChange={(checked) =>
                  handleSettingUpdate("require_mention_in_groups", checked)
                }
                disabled={isSubmitting || !botConfig.enabled}
              />
            }
          />
          <ContentAction
            title="Default Agent"
            description="The agent used to answer all LINE messages."
            sizePreset="main-content"
            variant="section"
            rightChildren={
              <InputSelect
                value={botConfig.default_persona_id?.toString() ?? "default"}
                onValueChange={(value: string) =>
                  handleSettingUpdate(
                    "default_persona_id",
                    value === "default" ? null : parseInt(value)
                  )
                }
                disabled={isSubmitting || personasLoading || !botConfig.enabled}
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
    </>
  );
}

export default function Page() {
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        description="Connect Onyx to a LINE Official Account. Users can ask questions in 1:1 chats or groups."
      />
      <SettingsLayouts.Body>
        <LineBotContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
