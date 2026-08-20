"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Switch } from "@opal/components";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { EmptyMessageCard } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { Section } from "@/layouts/general-layouts";
import {
  TelegramChatConfig,
  TelegramChatType,
} from "@/app/admin/telegram-bot/types";
import { SvgBubbleText, SvgUser, SvgUsers } from "@opal/icons";
import { IconProps } from "@opal/types";
import { Agent } from "@/lib/agents/types";

function getChatIcon(
  chatType: TelegramChatType
): React.ComponentType<IconProps> {
  switch (chatType) {
    case "private":
      return SvgUser;
    case "group":
    case "supergroup":
      return SvgUsers;
    default:
      return SvgBubbleText;
  }
}

interface Props {
  chats: TelegramChatConfig[];
  personas: Agent[];
  onChatUpdate: (
    chatConfigId: number,
    field: "enabled" | "require_bot_invocation" | "persona_override_id",
    value: boolean | number | null
  ) => void;
  disabled?: boolean;
}

export function TelegramChatsTable({
  chats,
  personas,
  onChatUpdate,
  disabled = false,
}: Props) {
  if (chats.length === 0) {
    return (
      <EmptyMessageCard
        sizePreset="main-ui"
        title="No chats discovered"
        description="Send your bot a message (or add it to a group) and the chat will appear here."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="[&>th]:whitespace-nowrap">
          <TableHead>Chat</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Enabled</TableHead>
          <TableHead>Require @mention</TableHead>
          <TableHead>Agent Override</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {chats.map((chat) => {
          const ChatIcon = getChatIcon(chat.chat_type);
          return (
            <TableRow key={chat.id}>
              <TableCell>
                <Section
                  flexDirection="row"
                  justifyContent="start"
                  gap={2}
                  width="fit"
                >
                  <ChatIcon width={16} height={16} />
                  <Text text04 mainUiBody>
                    {chat.chat_name}
                  </Text>
                </Section>
              </TableCell>
              <TableCell>
                <Text text03 secondaryBody>
                  {chat.chat_type}
                </Text>
              </TableCell>
              <TableCell>
                <Switch
                  checked={chat.enabled}
                  onCheckedChange={(checked) =>
                    onChatUpdate(chat.id, "enabled", checked)
                  }
                  disabled={disabled}
                />
              </TableCell>
              <TableCell>
                {chat.chat_type !== "private" && (
                  <Switch
                    checked={chat.require_bot_invocation}
                    onCheckedChange={(checked) =>
                      onChatUpdate(chat.id, "require_bot_invocation", checked)
                    }
                    disabled={disabled}
                  />
                )}
              </TableCell>
              <TableCell>
                <InputSelect
                  value={chat.persona_override_id?.toString() ?? "default"}
                  onValueChange={(value: string) =>
                    onChatUpdate(
                      chat.id,
                      "persona_override_id",
                      value === "default" ? null : parseInt(value)
                    )
                  }
                  disabled={disabled}
                >
                  <InputSelect.Trigger placeholder="-" />
                  <InputSelect.Content>
                    <InputSelect.Item value="default">-</InputSelect.Item>
                    {personas.map((persona) => (
                      <InputSelect.Item
                        key={persona.id}
                        value={persona.id.toString()}
                      >
                        {persona.name}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
