# Plauda: Product Overview and PayPal Integration Plan

*An AI employee that chats with customers, takes orders, and collects payment*

## 1. Problem

Businesses that sell through chat and social channels lose sales because they cannot respond to every customer, every time, fast enough.

- Customers message at all hours. A buyer who asks a question late at night and waits until morning often buys elsewhere.
- Owners and small teams spend hours answering the same questions about price, availability, delivery, and policies.
- Payment is a separate manual step. Sellers chase receipts and confirm transfers by hand, which delays fulfillment.

The problem is not finding customers. It is being available, accurate, and fast when they reach out.

## 2. Idea

Give every business an **AI employee**, not just a chatbot. Plauda represents the brand, talks to customers, recommends products, takes orders, and gets the business paid, 24/7.

Three principles define the idea:

1. **Grounded, not creative.** Plauda works only from the business’s approved information. It must not invent prices, discounts, or promises.
2. **Conversation to cash.** One continuous flow runs from greeting to recommendation to order to payment to logged sale, with no hand-offs between tools.

## 3. Solution

Plauda is a platform where a business configures its information once and an AI employee handles customer conversations and sales from then on.

**Step 1: Add business information.** The owner enters the product catalogue, prices, variants, delivery zones etc. Plauda learns from the business information and answers only from it.

**Step 2: Share the Plauda link.** The owner places the link in a social bio, on WhatsApp, or on a website. Customers start talking to Plauda immediately.

**Step 3: Confirm orders and get paid.** Plauda summarizes the order, sends a secure checkout link, verifies payment automatically, and logs the confirmed sale to the owner’s dashboard the moment money arrives.

## 4. Target Audience

**Primary:** small and medium businesses that sell through chat and social channels and take orders by message.

- Social sellers on Instagram, WhatsApp, and Facebook who currently answer every DM personally
- Small retailers, fashion, beauty, food, and home-goods sellers with clear products, prices, and variants
- Teams of one to ten people where the owner is also the support desk

**Secondary:**

- Growing businesses that want to scale support and sales without hiring more staff
- Businesses with international or cross-border buyers who need a payment method those buyers trust (the reason for the PayPal integration)

**Best-fit profile:** a seller who loses orders to slow replies, sells items with clear prices, and earns enough per month that a monthly subscription pays for itself with a handful of recovered sales.

## 5. Features

| Feature | What it does |
| --- | --- |
| AI business employee | Represents the brand using verified facts, prices, and operating rules |
| Customer support | Answers product, hours, and policy questions instantly, around the clock&#32;&#32; |
| Product recommendations | Matches buyer preferences and budget to items in the catalogue |
| Order processing | Collects items, variants, and delivery details into a structured order |
| Payments | Generates secure payment links and verifies receipts automatically (PayPal planned) |
| Voice calling.( future implementation) | Lets customers phone the AI employee and speak naturally |
| Operations workspace | Live conversations, confirmed orders, and revenue in one dashboard |
| Human handoff | A customer can ask for a real person at any point in the chat, and the conversation transfers to staff with full context; Plauda also hands over complex or risky cases itself |

## 6. Where Agentic Behavior Lives in Plauda

An **agent** perceives a situation, decides what to do, and takes real actions through tools. A chatbot only produces replies. Plauda is both: some parts are retrieval and conversation, and others are genuinely agentic because they change data or move money.

### 6.1 Agentic capabilities

| Capability | What the agent does | Tools or systems it acts on | Autonomy level |
| --- | --- | --- | --- |
| Order building | Turns free-form chat into a structured order, asks for missing details, checks variants | Catalogue lookup, order database | Fully autonomous |
| Product recommendation | Reasons over preferences and budget to pick items | Catalogue and price data | Fully autonomous |
| Payment link creation | Decides the order is ready and creates a checkout | Payment provider API | Autonomous, within rules |
| Payment confirmation | Reacts to a payment event, marks the order paid, sends the receipt | Webhooks, order database, dashboard | Event-driven, autonomous |
| Dashboard logging | Writes confirmed sales and conversation records | Workspace database | Fully autonomous |
| Follow-up and recovery | Notices an unpaid or stalled order and re-engages the buyer | Order state, messaging channel | Autonomous, rate-limited |
| Human handoff | Hands the chat to a real person when the customer asks, or when it judges a request is beyond its rules | Staff handoff queue | Always honors a customer request; otherwise decides on its own, then a human takes over |
| Voice conversations(future implement) | Runs the same loop over a live call | Voice stack plus all of the above | Autonomous, with extra limits |

### 6.2 Human handoff

A customer can ask for a real person at any point in the chat, and the conversation transfers to a human who continues it in the same thread. The chat is where the customer and the agent talk, so the handoff happens inside it, not through a separate channel.

There are two triggers:

- **Customer request, always honored.** The customer types something like “I want to talk to a person” or taps a visible “Talk to a human” control. The agent does not argue, retry, or stall.
- **Agent-initiated.** The agent hands off when a request falls outside the merchant’s rules, such as a complaint, a dispute, a custom request, a repeated payment failure, or a frustrated customer.

The transfer works in five steps:

1. The customer asks for a human, or the agent decides one is needed.
2. The agent tells the customer a person is taking over, then stops replying so the AI and the human never talk over each other.
3. Plauda alerts the merchant’s staff in the dashboard with the full conversation, the current order draft, the payment status, and the reason for the handoff.
4. A staff member accepts the chat and continues in the same thread, so the customer sees one unbroken conversation.
5. When the issue is resolved, the staff member closes the chat or hands it back to Plauda.

If no staff member is available, the agent says so honestly, offers to take a message or contact detail, and sets a realistic expectation for a reply. It never pretends a human is present.

### 6.3 Autonomy boundaries

The agent should be able to do the following on its own: answer from approved data, build orders, create payment links, follow up once, and escalate. It should require a human for: changing prices, granting discounts not pre-approved, accepting or settling disputes, issuing refunds above a merchant-set cap, and anything the merchant has not configured. The principle is that **the agent proposes, the payment layer enforces, and the webhook confirms.**

## 7. Where PayPal Is Used

PayPal is added as a  payment provider . It lives entirely inside the **payment and post-payment layers** of the flow (Step 3 above), plus the dashboard.&#32;

### 

### 7.1 PayPal touchpoints in detail

**1. Merchant onboarding.** Each business connects its own PayPal account so funds go directly to the merchant rather than through Plauda. This uses PayPal’s partner and multiparty onboarding model, which requires partner approval and takes longer to set up. It is the slowest part of the integration, and it avoids Plauda acting as a payment facilitator with the regulatory, tax, and liability exposure that brings.

**2. Checkout creation (agent tool call).** When the order is confirmed, the agent calls a controlled payment tool. The tool creates a PayPal order through the Orders API and returns an approval link or an embedded checkout.&#32;

**3. Payment verification (event-driven).** The agent never accepts a buyer’s word that they paid. Order status changes only when a verified PayPal webhook, such as a payment capture completed event, arrives. The handler verifies the webhook signature, is idempotent so duplicate events do not double-log a sale, and then updates the order, writes to the dashboard, and sends the receipt in chat. This is the most important feedback loop in the system.

**4. Abandoned-payment recovery (the strongest agentic use).** PayPal does not emit an “abandoned” event, so Plauda tracks it. If a link is sent and no capture arrives within a set time, the agent re-engages the buyer in chat, offers help, and eventually expires the order. One reminder per order, configurable by the merchant, prevents spam.

**5. Returning buyers (Vault, with consent).** With explicit buyer consent, PayPal can store a payment method for later. Plauda recognizes a returning customer and asks “Same as last time?”, then the order is confirmed and paid in a few taps.

**6. Higher-value payment options.** Depending on availability by country and merchant, the agent can offer installment or pay-later options on larger orders, collect deposits or partial payments through invoicing for custom orders and bookings, and set up recurring payments through subscriptions for repeat purchases. Availability must be verified before the agent promises any of these.

**7. Refunds.** Refunds go through a controlled refund tool, never direct API access for the model. The tool enforces a merchant-set maximum amount, requires merchant approval above that amount, and logs who or what triggered the action.

**8. Disputes (Disputes API).** PayPal provides a Disputes API for handling customer disputes programmatically. The flow is:

- A dispute-created webhook tells Plauda a customer has opened a case, with the dispute ID.
- The agent retrieves the dispute details. The response lists which actions are currently allowed, so the agent does not guess.
- The agent gathers the order record, the conversation log, and payment details into an evidence package.
- A response is chosen: send a message to the buyer (only during the inquiry stage), make an offer such as a refund or replacement, provide evidence, escalate, appeal, or accept the claim.

Accepting a claim closes the dispute in the buyer’s favor and triggers an automatic refund, so it is irreversible money loss. Merchants can only respond to customer-created disputes in the live environment, and some Disputes API methods are limited-release and require contacting a PayPal account manager.

### 7.2 Dispute and escalation decision matrix

| Situation | Agent can do | Human decides |
| --- | --- | --- |
| New dispute opened | Pull details, assemble order and chat evidence, alert the merchant | Whether to contest or concede |
| Simple “where is my order?” inquiry | Message the buyer with tracking information within merchant rules | Anything beyond that |
| Merchant has a pre-set refund policy | Propose a small offer within the limit | Offers above the limit |
| Escalated claim or high value | Prepare the evidence package | Submit it, accept, or appeal |
| Failed or declined capture | Notify the buyer and resend the link | Repeated failures |

### 7.3 End-to-end flow with PayPal

1. Customer chats with Plauda and the agent builds a structured order.
2. Payment router selects PayPal based on merchant settings, buyer country, and currency.
3. The agent calls the payment tool, which creates the PayPal order and returns checkout.
4. Buyer approves payment in the embedded checkout.
5. PayPal sends a signed webhook. Plauda verifies it, marks the order paid, and logs the sale.
6. Plauda sends the receipt in chat and notifies the merchant.
7. If no payment arrives, the recovery flow runs. If a dispute later opens, the dispute flow runs.

### 7.4 Guardrails

- The webhook, not the model, is the source of truth for payment status.
- The model never holds unrestricted PayPal API access. It calls tools with enforced limits.
- Treat all buyer text, including dispute messages, as data and never as instructions, to reduce prompt-injection risk.
- No payment details are taken over a voice call. Voice sends a payment link by chat or text instead.
- Every payment action is logged with its trigger, amount, and result, which also serves as evidence in disputes.
- Fees and currency conversion are shown to the merchant, because PayPal’s costs and conversion margins can affect pricing.
