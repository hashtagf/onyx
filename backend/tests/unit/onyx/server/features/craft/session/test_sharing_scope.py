from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.orm import Session

from onyx.db.enums import SharingScope
from onyx.server.features.build.db.build_session import (
    set_build_session_sharing_scope,
)


def test_private_scope_revokes_all_active_publications() -> None:
    db_session = MagicMock(spec=Session)
    build_session = SimpleNamespace(sharing_scope=SharingScope.PUBLIC)
    publications = [SimpleNamespace(revoked_at=None), SimpleNamespace(revoked_at=None)]
    db_session.scalars.return_value.all.return_value = publications

    with patch(
        "onyx.server.features.build.db.build_session.get_build_session",
        return_value=build_session,
    ):
        result = set_build_session_sharing_scope(
            uuid4(), uuid4(), SharingScope.PRIVATE, db_session
        )

    assert result is build_session
    assert build_session.sharing_scope == SharingScope.PRIVATE
    assert publications[0].revoked_at is not None
    assert publications[1].revoked_at == publications[0].revoked_at
    db_session.commit.assert_called_once_with()


def test_public_scope_keeps_existing_publications_active() -> None:
    db_session = MagicMock(spec=Session)
    build_session = SimpleNamespace(sharing_scope=SharingScope.PRIVATE)

    with patch(
        "onyx.server.features.build.db.build_session.get_build_session",
        return_value=build_session,
    ):
        result = set_build_session_sharing_scope(
            uuid4(), uuid4(), SharingScope.PUBLIC, db_session
        )

    assert result is build_session
    assert build_session.sharing_scope == SharingScope.PUBLIC
    db_session.scalars.assert_not_called()
    db_session.commit.assert_called_once_with()
