import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_critic.models import CritiqueRequest
from agent_critic.server import create_app

from .conftest import make_request

VALID_BODY = {
    "route": "coding",
    "system_prompt": "You are a coding assistant.",
    "user_prompt": "Return the last element of a list.",
    "assistant_response": "def last(xs): return xs[-1]",
}


def test_valid_request_constructs():
    req = make_request()
    assert req.system_prompt and req.user_prompt and req.assistant_response


@pytest.mark.parametrize("field", ["system_prompt", "user_prompt", "assistant_response"])
def test_missing_one_field_names_it(field):
    body = {k: v for k, v in VALID_BODY.items() if k != field}
    with pytest.raises(ValidationError, match=field):
        CritiqueRequest(**body)


def test_empty_or_whitespace_counts_as_missing():
    with pytest.raises(ValidationError, match="assistant_response"):
        CritiqueRequest(**{**VALID_BODY, "assistant_response": "   "})


def test_missing_all_three_listed_together():
    with pytest.raises(ValidationError) as exc:
        CritiqueRequest(route="coding")
    message = str(exc.value)
    assert "system_prompt" in message
    assert "user_prompt" in message
    assert "assistant_response" in message


def test_endpoint_missing_fields_returns_400(config_path):
    with TestClient(create_app(config_path)) as client:
        resp = client.post("/v1/critique", json={"route": "coding", "system_prompt": "s"})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert "user_prompt" in error
    assert "assistant_response" in error
    assert "system_prompt" not in error  # the one that was provided
