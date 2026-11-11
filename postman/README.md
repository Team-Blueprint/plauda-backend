# Plauda Postman Collection & Environments

This folder contains the complete **Postman Collection (v2.1)** and **Postman Environments** for the **Plauda API** (generated from [`docs/contracts/openapi.json`](../docs/contracts/openapi.json) and enhanced with automated `pm.test` assertions and variable chaining).

## Files

| File | Description |
|---|---|
| [`Plauda_API.postman_collection.json`](Plauda_API.postman_collection.json) | Complete collection with **49 requests across 11 domain folders**, pre-populated JSON bodies, Bearer auth inheritance, and post-response test scripts. |
| [`Plauda_Production.postman_environment.json`](Plauda_Production.postman_environment.json) | Production environment targeting `https://plauda.fastapicloud.dev` and store `plauda-store`. |
| [`Plauda_Local.postman_environment.json`](Plauda_Local.postman_environment.json) | Local development environment targeting `http://localhost:8000`. |

## Automated Variable Chaining (`pm.test`)

You do **not** need to manually copy-paste tokens or IDs between requests:

1. **Merchant Auth (`POST /auth/login` or `POST /auth/register`):**
   - Automatically verifies `200/201` status and stores `access_token` $\rightarrow$ `{{merchant_token}}`, `merchant.slug` $\rightarrow$ `{{store_slug}}`, and `merchant.id` $\rightarrow$ `{{merchant_id}}`.
2. **Catalogue & Delivery Setup (`POST /products`, `POST /delivery-zones`):**
   - Automatically captures `{{product_id}}`, `{{variant_id}}`, and `{{zone_id}}`.
3. **Customer Chat & AI Agent (`POST /public/chat/{{store_slug}}/conversations`):**
   - Automatically captures `{{conversation_id}}` and `{{visitor_token}}` so you can immediately run `POST /public/chat/{{store_slug}}/messages` (SSE AI agent turn) or `POST /public/conversations/{{conversation_id}}/handoff`.

## How to Import into Postman

1. Open **Postman** $\rightarrow$ click **Import**.
2. Drag and drop the `postman/` folder (or select `Plauda_API.postman_collection.json` and `Plauda_Production.postman_environment.json`).
3. Select **Plauda Production (FastAPI Cloud)** in the top-right Environment dropdown.
4. Run **1. System & Health $\rightarrow$ Healthz** to confirm `{"status": "ok", "db": "ok"}`.

## Running via Newman CLI

You can also run the health and public storefront checks directly from the command line using [Newman](https://learning.postman.com/docs/collections/using-newman-cli/command-line-integration-with-newman/):

```bash
npx newman run postman/Plauda_API.postman_collection.json \
  -e postman/Plauda_Production.postman_environment.json \
  --folder "1. System & Health"
```
