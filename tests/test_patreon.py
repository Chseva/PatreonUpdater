from unittest.mock import Mock

import pytest
import requests

from patreon_mega_audit.patreon import BASE_URL, PatreonApiError, PatreonClient


def response(payload, status=200):
    result = Mock(ok=status == 200, status_code=status)
    result.json.return_value = payload
    return result


def test_discovery_then_posts_uses_returned_id():
    session = Mock(headers={})
    session.get.side_effect = [response({"data": [{"id": "42"}]}), response({"data": []})]
    client = PatreonClient("test-token", session)
    assert list(client.iter_campaign_posts(client.discover_campaign_id())) == []
    assert session.get.call_args_list[0].args[0] == f"{BASE_URL}/campaigns"
    assert session.get.call_args_list[1].args[0] == f"{BASE_URL}/campaigns/42/posts"


def test_discovery_follows_pagination_and_rejects_ambiguous_selection():
    session = Mock(headers={})
    next_url = f"{BASE_URL}/campaigns?page[cursor]=next"
    session.get.side_effect = [
        response({"data": [{"id": "42"}], "links": {"next": next_url}}),
        response({"data": [{"id": "43"}]}),
    ]
    with pytest.raises(PatreonApiError, match="Multiple campaigns"):
        PatreonClient("test-token", session).discover_campaign_id()
    assert session.get.call_args_list[1].args[0] == next_url


@pytest.mark.parametrize("payload,status,message", [
    ({"data": []}, 200, "No creator campaign"),
    ({}, 401, "rejected the token"),
    ({}, 403, "campaigns permission"),
    ({}, 500, "HTTP 500"),
    ({"data": {}}, 200, "invalid campaign response"),
])
def test_discovery_errors(payload, status, message):
    session = Mock(headers={})
    session.get.return_value = response(payload, status)
    with pytest.raises(PatreonApiError, match=message):
        PatreonClient("test-token", session).discover_campaigns()


def test_connection_error_does_not_expose_token():
    session = Mock(headers={})
    session.get.side_effect = requests.ConnectionError("test-token")
    with pytest.raises(PatreonApiError, match="Could not connect") as error:
        PatreonClient("test-token", session).discover_campaigns()
    assert "test-token" not in str(error.value)
