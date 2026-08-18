# LINE

Indexes the **follower roster** (directory) of your **LINE Official
Account** via the LINE Messaging API. Each user who added the account as a
friend becomes a searchable directory entry: display name, status message,
picture, and language.

## What is indexed

- Users who added your LINE Official Account as a friend.
- Per user: display name, status message, profile picture URL, language.

## What is NOT indexed

The **chat messages** are not indexed. The LINE Messaging API has **no
message-history endpoint** — messages are only delivered to an always-on
webhook that Onyx's standard connector framework does not use. The follower
**roster** is the only pullable data.

The follower listing additionally requires a **verified or premium** LINE
Official Account.

## Getting a channel access token

1. Create a LINE Official Account and a Messaging API channel in the
   [LINE Developers Console](https://developers.line.biz/console/).
2. Under the channel's **Messaging API** tab, issue a **Channel
   access token** (long-lived).
3. Grant the **profile** scope so user profiles can be fetched.

## Add the connector in Onyx

1. Admin → **Connectors** → **Add Connector** → **LINE**.
2. Create a credential with the **Channel Access Token**.
3. Save. The follower roster is indexed on this run and on refresh
   (load-state connector).

## Limitations

- Chat messages are not indexed (Messaging API has no history endpoint).
- Follower listing requires a verified/premium account.
- Users who block the account, delete it, or do not consent to profile
  access are omitted by LINE.
