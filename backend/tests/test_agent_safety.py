import uuid

from pydantic_ai.models.test import TestModel
from sqlalchemy import select

from app.agent.handoff import HandoffDecision, classify_handoff, detect_handoff_request
from app.agent.rate_limit import RateLimitCheck, SlidingWindowLimiter
from app.agent.routes import _client_ip
from app.config import get_settings
from app.db.models import Conversation, Message


def test_deterministic_handoff_phrases():
    assert detect_handoff_request("Can I talk to a human please?")
    assert detect_handoff_request("I need to speak with a real person")
    assert detect_handoff_request("connect me to customer support")
    assert detect_handoff_request("Do you deliver on Sundays?") is None
    assert detect_handoff_request("Do you sell human hair wigs?") is None


async def test_classifier_returns_structured_decision():
    model = TestModel(custom_output_args={"should_handoff": True, "reason": "The buyer is angry"})
    decision = await classify_handoff(
        "This is unacceptable and I want compensation",
        model=model,
        timeout_seconds=5,
    )
    assert decision == HandoffDecision(should_handoff=True, reason="The buyer is angry")


def test_sliding_window_limiter_denies_and_recovers():
    limiter = SlidingWindowLimiter()
    checks = [RateLimitCheck(scope="ip", key="1.2.3.4", limit=2)]

    assert limiter.consume(checks, window_seconds=60, now=100).allowed
    assert limiter.consume(checks, window_seconds=60, now=101).allowed
    denied = limiter.consume(checks, window_seconds=60, now=102)
    assert denied.allowed is False
    assert denied.scope == "ip"
    assert denied.retry_after == 58
    assert limiter.consume(checks, window_seconds=60, now=161).allowed


def test_sliding_window_limiter_ignores_disabled_scope():
    limiter = SlidingWindowLimiter()
    checks = [RateLimitCheck(scope="ip", key="1.2.3.4", limit=0)]
    for _ in range(100):
        assert limiter.consume(checks, window_seconds=60).allowed


def test_client_ip_prefers_x_forwarded_for():
    from starlette.requests import Request

    req_forwarded = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"198.51.100.10, 10.0.0.1")],
            "client": ("10.0.0.1", 12345),
        }
    )
    assert _client_ip(req_forwarded) == "198.51.100.10"

    req_direct = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("198.51.100.20", 12345),
        }
    )
    assert _client_ip(req_direct) == "198.51.100.20"


async def _conversation(db_client, slug: str) -> dict:
    response = await db_client.post(f"/public/chat/{slug}/conversations", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _events(response) -> list[dict]:
    import json

    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


async def test_chat_turn_rate_limit_returns_429(db_client, merchant_auth, monkeypatch):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)
    limiter = SlidingWindowLimiter()
    limiter.consume(
        [RateLimitCheck(scope="ip", key="203.0.113.77", limit=1)],
        window_seconds=60,
    )
    settings = get_settings().model_copy(update={"chat_rate_limit_per_ip": 1})
    monkeypatch.setattr("app.agent.routes.chat_turn_limiter", limiter)
    monkeypatch.setattr("app.agent.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.agent.routes._client_ip", lambda request: "203.0.113.77")

    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={"conversation_id": conversation["conversation_id"], "content": "Hi"},
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert "Too many messages" in response.json()["detail"]


async def test_explicit_request_hands_off_without_running_agent(
    db_client, db_session, merchant_auth, monkeypatch
):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)
    monkeypatch.setattr(
        "app.agent.routes.get_agent_model",
        lambda: TestModel(call_tools=[], custom_output_text="should not run"),
    )

    async def unexpected(*args, **kwargs):
        raise AssertionError("classifier must not run after a deterministic handoff")

    monkeypatch.setattr("app.agent.routes.classify_handoff", unexpected)
    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={
            "conversation_id": conversation["conversation_id"],
            "content": "I want to talk to a human",
        },
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 200, response.text
    events = _events(response)
    assert events[0]["type"] == "system"
    assert events[0]["kind"] == "handoff"
    assert events[-1] == {"type": "done"}

    row = await db_session.get(Conversation, uuid.UUID(conversation["conversation_id"]))
    assert row is not None
    assert row.status == "handoff_requested"
    assert row.handoff_reason == "Buyer asked for a human"
    messages = list(
        await db_session.scalars(
            select(Message).where(Message.conversation_id == row.id).order_by(Message.created_at)
        )
    )
    assert [message.role for message in messages] == ["customer", "system"]
    assert all(message.role != "agent" for message in messages)


async def test_classifier_can_trigger_handoff(db_client, db_session, merchant_auth, monkeypatch):
    slug = merchant_auth["merchant"]["slug"]
    conversation = await _conversation(db_client, slug)
    monkeypatch.setattr(
        "app.agent.routes.get_agent_model",
        lambda: TestModel(call_tools=[], custom_output_text="should not run"),
    )

    async def angry(*args, **kwargs):
        return HandoffDecision(should_handoff=True, reason="Buyer is frustrated")

    monkeypatch.setattr("app.agent.routes.classify_handoff", angry)
    response = await db_client.post(
        f"/public/chat/{slug}/messages",
        json={
            "conversation_id": conversation["conversation_id"],
            "content": "This is the third time and nobody has helped me.",
        },
        headers={"Authorization": f"Bearer {conversation['visitor_token']}"},
    )

    assert response.status_code == 200, response.text
    events = _events(response)
    assert events[0]["kind"] == "handoff"
    assert events[-1] == {"type": "done"}

    row = await db_session.get(Conversation, uuid.UUID(conversation["conversation_id"]))
    assert row is not None
    assert row.status == "handoff_requested"
    assert row.handoff_reason == "Buyer is frustrated"
