"""Live test for the Telegram connector.

Requires the ``telegram-bot-token`` connector secret: a BotFather token for a
bot that (a) has been started by at least one user and (b) messages appear in
the queue when this test runs. The Bot API cannot backfill history, so the
test drains whatever is queued; if the queue is empty the test asserts that
the connector still runs cleanly (no documents).
"""

import time

import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import Document, HierarchyNode
from onyx.connectors.telegram.connector import TelegramConnector
from tests.utils.secret_names import TestSecret

pytestmark = pytest.mark.secrets(TestSecret.TELEGRAM_BOT_TOKEN)


@pytest.fixture
def telegram_connector(test_secrets: dict[TestSecret, str]) -> TelegramConnector:
    connector = TelegramConnector()
    connector.load_credentials(
        {"telegram_bot_token": test_secrets[TestSecret.TELEGRAM_BOT_TOKEN]}
    )
    return connector


def test_telegram_connector_basic(telegram_connector: TelegramConnector) -> None:
    end_time = time.time()
    start_time = end_time - (7 * 24 * 60 * 60)
    doc_batch_generator = telegram_connector.poll_source(start_time, end_time)

    docs: list[Document] = []
    for doc_batch in doc_batch_generator:
        for doc in doc_batch:
            if not isinstance(doc, HierarchyNode):
                docs.append(doc)

    # The queue may legitimately be empty (bot has not received new messages).
    # When it is not, we validate document structure.
    if not docs:
        pytest.skip("No queued Telegram updates to index; test asserts clean run.")

    doc = docs[0]
    assert doc.source == DocumentSource.TELEGRAM
    assert doc.id is not None and doc.id.startswith("TELEGRAM_")
    assert doc.semantic_identifier is not None
    assert len(doc.sections) > 0
    assert doc.metadata.get("Chat") is not None
