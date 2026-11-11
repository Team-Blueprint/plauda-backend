# Plauda — APIMatic Specification & Strongly-Typed Python SDK

Small and social-first businesses sell everywhere: WhatsApp Business, Instagram DMs, Telegram, and custom e-commerce storefronts. To make Plauda's 24/7 AI employee and verified PayPal checkout embeddable on any channel without manual HTTP/JSON wiring, we use **APIMatic** to validate our OpenAPI specification and provide a **strongly-typed Python SDK (`plauda_sdk`)**.

## Contents

| Path | Description |
|---|---|
| [`plauda-openapi.json`](plauda-openapi.json) | APIMatic-compliant OpenAPI `3.0.3` specification with normalized `operationId`s, nullable type mappings, and Production (`https://plauda.fastapicloud.dev`) + Local (`http://localhost:8000`) servers. |
| [`APIMATIC-META.json`](APIMATIC-META.json) | Official APIMatic CodeGen metadata configuring model generation, controller prefixes, retry backoff (`408, 429, 500, 502, 503, 504`), and timeouts. |
| [`python-sdk/plauda_sdk/`](python-sdk/plauda_sdk/) | Strongly-typed Python SDK with typed `dataclass` & `Enum` models (`OrderStatus`, `ConversationStatus`, `Product`, `OrderRecord`, `CreateOrderPaymentLinkResponse`, etc.) and domain controllers (`system`, `auth`, `catalogue`, `public_chat`, `inbox`, `orders`, `payments`, `dashboard`). |
| [`python-sdk/examples/whatsapp_bridge.py`](python-sdk/examples/whatsapp_bridge.py) | Example showing how a WhatsApp/Instagram webhook connects a customer message to Plauda's AI employee in a few lines of strongly-typed Python. |

## Strongly-Typed Python SDK Quickstart

```python
from plauda_sdk import ChatTurnRequest, Environment, PlaudaClient

with PlaudaClient(environment=Environment.PRODUCTION) as client:
    # 1. Strongly-typed health check
    health = client.system.healthz()
    assert health.status == "ok" and health.db == "ok"

    # 2. Fetch store metadata & start a customer conversation
    store = client.public_chat.get_store_meta("plauda-store")
    conv = client.public_chat.create_conversation(store.slug, visitor_name="Ada")

    # 3. Stream a grounded AI employee turn over SSE
    turn = ChatTurnRequest(
        conversation_id=conv.conversation_id,
        content="What do you have in stock today under $25?",
    )
    for event_line in client.public_chat.stream_chat_turn(store.slug, turn):
        print(event_line)
```

## Validating & Regenerating with APIMatic CLI

You can validate [`plauda-openapi.json`](plauda-openapi.json) or generate additional language SDKs (TypeScript, C#, Java, PHP, Ruby, Go) via the official `@apimatic/cli`:

```bash
# Validate the Plauda OpenAPI specification
npx @apimatic/cli api:validate --file apimatic/plauda-openapi.json

# Or import apimatic/plauda-openapi.json + apimatic/APIMATIC-META.json into https://app.apimatic.io
```
