import json
import uuid

from pydantic_ai.models.test import TestModel
from sqlalchemy import select

from app.agent.agent import AgentConfigError
from app.db.models import Conversation


def _events(response) -> list[dict]:
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


async def _conversation(db_client, slug: str) -> dict:
    response = await db_client.post(f"/public/chat/{slug}/conversations", json={})
    assert response.status_code == 201, response.text
    return response.json()


async def test_chat_turn_streams_agent_reply_and_persists_it(db_client, merchant_auth, monkeypatch):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)
    monkeypatch.setattr(
        "app.agent.routes.get_agent_model",
        lambda: TestModel(call_tools=[], custom_output_text="Hello from the assistant."),
    )

    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={"conversation_id": conversation["conversation_id"], "content": "Hi"},
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 200, response.text
    events = _events(response)
    assert any(event["type"] == "delta" for event in events)
    assert events[-1] == {"type": "done"}

    messages = await db_client.get(
        f"/public/conversations/{conversation['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )
    assert messages.status_code == 200, messages.text
    items = messages.json()["items"]
    assert [item["role"] for item in items] == ["customer", "agent"]
    assert items[-1]["content"] == "Hello from the assistant."


async def test_chat_turn_returns_503_when_agent_is_not_configured(
    db_client, merchant_auth, monkeypatch
):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)

    def unavailable():
        raise AgentConfigError("missing key")

    monkeypatch.setattr("app.agent.routes.get_agent_model", unavailable)
    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={"conversation_id": conversation["conversation_id"], "content": "Hi"},
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


async def test_chat_turn_does_not_call_agent_when_human_is_active(
    db_client, merchant_auth, db_session, monkeypatch
):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)
    row = await db_session.scalar(
        select(Conversation).where(Conversation.id == uuid.UUID(conversation["conversation_id"]))
    )
    row.status = "human_active"
    await db_session.commit()

    def unexpected():
        raise AssertionError("the agent must not run during a human handoff")

    monkeypatch.setattr("app.agent.routes.get_agent_model", unexpected)
    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={"conversation_id": conversation["conversation_id"], "content": "Hello?"},
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 200, response.text
    events = _events(response)
    assert events[0]["type"] == "system"
    assert events[-1] == {"type": "done"}
