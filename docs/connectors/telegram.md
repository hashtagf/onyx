# Telegram

Indexes messages your **Telegram bot** receives, via the Telegram Bot API.

## How it works

- The connector polls the Bot API's `getUpdates` endpoint (long-poll, no
  webhook or public URL required) and turns each update into a searchable
  document.
- Messages the bot can see are the ones in **groups/supergroups/channels it
  was added to** and **private chats where a user started the bot**
  (`/start`).
- The Bot API has **no message-history endpoint**: Onyx can only index
  messages that arrive *after* the connector is created. Updates the bot
  does not consume within ~24 hours are dropped by Telegram, so keep the
  refresh frequency at an hour or less.

## Getting a bot token

1. In Telegram, talk to [@BotFather](https://t.me/botfather).
2. Send `/newbot`, choose a name + username.
3. BotFather returns the **bot token** (looks like `123456:ABC-...`).
4. In each group/channel to be indexed: *Add bot as member*. For
   channels, grant the bot **Post messages** admin rights (channels the
   bot posts to are readable).
5. In a private chat, message the bot `/start` to include that
   conversation.

## Add the connector in Onyx

1. Admin → **Connectors** → **Add Connector** → **Telegram**.
2. Create a credential with the **Bot Token**.
3. Set a refresh frequency (recommend ≤ 1 hour; default 30 minutes).
4. Save. Documents appear after the first poll picks up new messages.

## Limitations

- No backfill of pre-existing chat history (Bot API constraint).
- Files larger than 20 MB cannot be downloaded through the Bot API; such
  media are indexed as text placeholders only.
- No permission sync: indexed documents are governed by Onyx access
  rules, not by Telegram chat membership.
