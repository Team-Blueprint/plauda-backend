import uuid

from app.conversations import service as conversation_service
from app.conversations.sse import (
    CONVERSATION_CHANNEL,
    EventHub,
    hub,
    sse_frame,
    stream_events,
)
from app.db.models import Conversation
from app.orders import service as order_service
from tests.conftest import register_merchant


async def _start_conversation(db_client, slug: str, **payload) -> dict:
    if payload:
        resp = await db_client.post(f"/public/chat/{slug}/conversations", json=payload)
    else:
        resp = await db_client.post(f"/public/chat/{slug}/conversations")
    assert resp.status_code == 201, resp.text
    return resp.json()


def _visitor_headers(created: dict) -> dict:
    return {"Authorization": f"Bearer {created['visitor_token']}"}


async def test_public_conversation_start_and_token_isolation(db_client, merchant_auth):
    slug = merchant_auth["merchant"]["slug"]
    first = await _start_conversation(db_client, slug, name="Ada", contact="ada@example.com")
    second = await _start_conversation(db_client, slug)
    visitor = _visitor_headers(first)

    resp = await db_client.get(
        f"/public/conversations/{first['conversation_id']}/messages", headers=visitor
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []

    # Token A cannot read conversation B.
    resp = await db_client.get(
        f"/public/conversations/{second['conversation_id']}/messages", headers=visitor
    )
    assert resp.status_code == 404

    # Missing token is rejected.
    resp = await db_client.get(f"/public/conversations/{first['conversation_id']}/messages")
    assert resp.status_code == 401

    resp = await db_client.post("/public/chat/does-not-exist/conversations")
    assert resp.status_code == 404


async def test_handoff_accept_reply_return_close(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    slug = merchant_auth["merchant"]["slug"]
    created = await _start_conversation(db_client, slug)
    visitor = _visitor_headers(created)
    conversation_id = created["conversation_id"]

    resp = await db_client.post(
        f"/public/conversations/{conversation_id}/handoff",
        json={"reason": "needs help"},
        headers=visitor,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "handoff_requested"
    assert resp.json()["handoff_reason"] == "needs help"

    # Pressing the button again is idempotent — no duplicate system message.
    resp = await db_client.post(f"/public/conversations/{conversation_id}/handoff", headers=visitor)
    assert resp.status_code == 200
    assert resp.json()["status"] == "handoff_requested"

    resp = await db_client.get(
        "/conversations", params={"status": "handoff_requested"}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["handoff_reason"] == "needs help"

    resp = await db_client.post(f"/conversations/{conversation_id}/accept", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "human_active"

    resp = await db_client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Hi, I'm the owner."},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "staff"

    resp = await db_client.get(f"/public/conversations/{conversation_id}/messages", headers=visitor)
    messages = resp.json()["items"]
    assert [message["role"] for message in messages] == ["system", "system", "staff"]
    assert messages[-1]["content"] == "Hi, I'm the owner."

    resp = await db_client.post(f"/conversations/{conversation_id}/return-to-ai", headers=headers)
    assert resp.json()["status"] == "ai"

    resp = await db_client.post(f"/public/conversations/{conversation_id}/handoff", headers=visitor)
    assert resp.json()["status"] == "handoff_requested"
    resp = await db_client.post(f"/conversations/{conversation_id}/accept", headers=headers)
    assert resp.json()["status"] == "human_active"

    resp = await db_client.post(f"/conversations/{conversation_id}/close", headers=headers)
    assert resp.json()["status"] == "closed"

    resp = await db_client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "late reply"},
        headers=headers,
    )
    assert resp.status_code == 409

    resp = await db_client.post(f"/public/conversations/{conversation_id}/handoff", headers=visitor)
    assert resp.status_code == 409


async def test_staff_reply_requires_human_active(db_client, merchant_auth):
    headers = merchant_auth["headers"]
    created = await _start_conversation(db_client, merchant_auth["merchant"]["slug"])

    resp = await db_client.post(
        f"/conversations/{created['conversation_id']}/messages",
        json={"content": "too early"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_inbox_is_merchant_scoped(db_client, merchant_auth):
    created = await _start_conversation(db_client, merchant_auth["merchant"]["slug"])
    conversation_id = created["conversation_id"]

    other = await register_merchant(db_client)
    resp = await db_client.get(f"/conversations/{conversation_id}", headers=other["headers"])
    assert resp.status_code == 404
    resp = await db_client.get("/conversations", headers=other["headers"])
    assert resp.json()["total"] == 0
    resp = await db_client.post(
        f"/conversations/{conversation_id}/accept", headers=other["headers"]
    )
    assert resp.status_code == 404


async def test_message_pagination(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    created = await _start_conversation(db_client, merchant_auth["merchant"]["slug"])
    conversation = await db_session.get(Conversation, uuid.UUID(created["conversation_id"]))
    for index in range(3):
        await conversation_service.add_message(
            db_session, conversation, role="system", content=f"m{index}", meta={}
        )

    resp = await db_client.get(
        f"/conversations/{created['conversation_id']}/messages",
        params={"limit": 2, "offset": 1},
        headers=headers,
    )
    body = resp.json()
    assert body["total"] == 3
    assert [message["content"] for message in body["items"]] == ["m1", "m2"]


async def test_order_links_to_conversation(db_client, db_session, merchant_auth):
    headers = merchant_auth["headers"]
    created = await _start_conversation(db_client, merchant_auth["merchant"]["slug"], name="Ada")
    conversation = await db_session.get(Conversation, uuid.UUID(created["conversation_id"]))
    order = await order_service.create_draft(
        db_session,
        merchant_id=conversation.merchant_id,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
    )

    resp = await db_client.get(f"/conversations/{conversation.id}", headers=headers)
    body = resp.json()
    assert body["latest_order_id"] == str(order.id)
    assert body["customer_name"] == "Ada"


async def test_unknown_conversation_status_filter_is_rejected(db_client, merchant_auth):
    resp = await db_client.get("/conversations?status=bogus", headers=merchant_auth["headers"])
    assert resp.status_code == 422


def test_event_hub_fanout_and_frame_format():
    hub = EventHub()
    first = hub.subscribe("merchant", "merchant-1")
    second = hub.subscribe("merchant", "merchant-1")
    hub.publish("merchant", "merchant-1", {"type": "message"})

    assert first.get_nowait() == {"type": "message"}
    assert second.get_nowait() == {"type": "message"}

    hub.unsubscribe("merchant", "merchant-1", first)
    assert hub.subscriber_count("merchant", "merchant-1") == 1

    assert sse_frame({"type": "x"}) == 'data: {"type":"x"}\n\n'


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def test_stream_events_emits_published_event_and_cleans_up():
    key = uuid.uuid4()
    stream = stream_events(_ConnectedRequest(), CONVERSATION_CHANNEL, key, keepalive_seconds=5)

    assert await anext(stream) == ": connected\n\n"
    hub.publish(CONVERSATION_CHANNEL, key, {"type": "message"})
    assert await anext(stream) == 'data: {"type":"message"}\n\n'

    await stream.aclose()
    assert hub.subscriber_count(CONVERSATION_CHANNEL, key) == 0
