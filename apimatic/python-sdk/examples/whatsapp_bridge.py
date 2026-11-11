"""Example: Bridging WhatsApp / Instagram DMs to Plauda using the Strongly-Typed Python SDK."""

from plauda_sdk import ChatTurnRequest, Environment, PlaudaClient


def run_demo() -> None:
    with PlaudaClient(environment=Environment.PRODUCTION) as client:
        # 1. Verify API & Database health (strongly-typed HealthResponse)
        health = client.system.healthz()
        print(f"[Health] status={health.status}, db={health.db}")

        # 2. Fetch public store metadata (strongly-typed PublicStoreMeta)
        store = client.public_chat.get_store_meta("plauda-store")
        print(f"[Store] {store.business_name} ({store.currency})")

        # 3. Start a visitor conversation (auto-binds visitor_bearer_token on client)
        session = client.public_chat.create_conversation(
            slug=store.slug,
            visitor_name="WhatsApp Customer",
        )
        print(f"[Conversation] id={session.conversation_id}, status={session.status.value}")

        # 4. Stream an AI employee turn over SSE
        turn = ChatTurnRequest(
            conversation_id=session.conversation_id,
            content="Hi! What do you have in stock today and what are your delivery zones?",
        )
        for sse_line in client.public_chat.stream_chat_turn(store.slug, turn):
            print(sse_line)


if __name__ == "__main__":
    run_demo()
