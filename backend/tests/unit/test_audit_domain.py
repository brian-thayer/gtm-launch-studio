import base64
from datetime import UTC, datetime

import pytest

from gtm_studio.domain.audit import (
    AuditAction,
    InvalidCursorError,
    canonical_hash,
    decode_cursor,
    encode_cursor,
)


def test_the_action_names_are_dotted_and_stable() -> None:
    assert [a.value for a in AuditAction] == [
        "auth.login",
        "auth.logout",
        "auth.login_denied",
        "user.provisioned",
        "user.updated",
        "user.roles_synced",
        "user.seeded",
        "user.roles_set",
    ]
    assert all("." in a.value and a.value == a.value.lower() for a in AuditAction)
    assert AuditAction.AUTH_LOGIN == "auth.login"  # a plain string wherever one is expected
    assert str(AuditAction.AUTH_LOGIN) == "auth.login"


def test_canonical_hash_is_known_and_compact() -> None:
    # sha256 of the exact text '{"a":1,"b":[true,null]}': any change to the encoding breaks every stored hash.
    assert canonical_hash({"b": [True, None], "a": 1}) == (
        "1cc69c7fa23616ca2ec3ee70d24390a6225c8832db8a4c814c7e0e7f942f8668"
    )


def test_canonical_hash_does_not_depend_on_key_order_at_any_depth() -> None:
    one = {"a": 1, "b": {"x": [1, 2], "y": "é"}}
    two = {"b": {"y": "é", "x": [1, 2]}, "a": 1}
    assert canonical_hash(one) == canonical_hash(two)
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
    assert canonical_hash([1, 2]) != canonical_hash([2, 1])  # list order is data


def test_canonical_hash_refuses_what_has_no_stable_json_form() -> None:
    with pytest.raises(TypeError):
        canonical_hash({"tags": {"a", "b"}})  # a set would hash differently from run to run
    with pytest.raises(TypeError):
        canonical_hash({"at": datetime(2026, 1, 1, tzinfo=UTC)})
    with pytest.raises(ValueError, match="Out of range"):
        canonical_hash({"x": float("nan")})


def test_a_cursor_round_trips() -> None:
    moment = datetime(2026, 11, 25, 10, 30, 15, 123456, tzinfo=UTC)
    cursor = encode_cursor(moment, "abc-123")
    assert decode_cursor(cursor) == (moment, "abc-123")
    assert base64.urlsafe_b64decode(cursor).decode() == "2026-11-25T10:30:15.123456+00:00|abc-123"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "!!! not base64 !!!",
        "é",
        base64.urlsafe_b64encode(b"no separator").decode(),
        base64.urlsafe_b64encode(b"2026-01-01T00:00:00+00:00|").decode(),  # no ID
        base64.urlsafe_b64encode(b"yesterday|abc").decode(),  # not a time
        base64.urlsafe_b64encode(b"2026-01-01T00:00:00|abc").decode(),  # naive: stored times are aware
        base64.urlsafe_b64encode(b"\xff\xfe|abc").decode(),  # not UTF-8
    ],
)
def test_a_cursor_that_was_not_issued_here_is_rejected(bad: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(bad)
