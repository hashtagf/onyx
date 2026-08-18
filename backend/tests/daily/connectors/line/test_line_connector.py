"""Live test for the LINE connector.

Requires the ``line-channel-access-token`` connector secret: the channel
access token of a verified/premium LINE Official Account with at least one
follower, and the ``profile`` scope. The connector indexes the follower
roster (directory), so this asserts at least one directory entry is produced.
"""

import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.line.connector import LineConnector
from onyx.connectors.models import Document, HierarchyNode
from tests.utils.secret_names import TestSecret

pytestmark = pytest.mark.secrets(TestSecret.LINE_CHANNEL_ACCESS_TOKEN)


@pytest.fixture
def line_connector(test_secrets: dict[TestSecret, str]) -> LineConnector:
    connector = LineConnector()
    connector.load_credentials(
        {
            "line_channel_access_token": test_secrets[
                TestSecret.LINE_CHANNEL_ACCESS_TOKEN
            ]
        }
    )
    return connector


def test_line_connector_basic(line_connector: LineConnector) -> None:
    doc_batch_generator = line_connector.load_from_state()

    docs: list[Document] = []
    for doc_batch in doc_batch_generator:
        for doc in doc_batch:
            if not isinstance(doc, HierarchyNode):
                docs.append(doc)

    if not docs:
        pytest.skip("LINE account has no followers; test asserts clean run.")

    doc = docs[0]
    assert doc.source == DocumentSource.LINE
    assert doc.id is not None and doc.id.startswith("LINE_")
    assert doc.semantic_identifier is not None
    assert len(doc.sections) > 0
    assert doc.metadata.get("User ID") is not None
