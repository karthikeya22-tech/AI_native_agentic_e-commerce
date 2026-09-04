# AI-Native Agentic E-Commerce

A proof-of-concept demonstrating how AI can power intelligent commerce decisions — product discovery, merchant growth recommendations, and conversational shopping — while keeping every financial action **explainable, bounded, gated, and auditable**.

> **AI controls reasoning. Backend controls authority.**

---

## Overview

This system uses large language models (LLMs) and semantic search to help buyers find products through natural language and to help merchants identify growth opportunities. Critically, AI never directly executes financial transactions or modifies business-critical state. All authority over money, inventory, and order lifecycle remains with the deterministic backend.

The platform is built as a full-stack POC:

- **Backend:** FastAPI + PostgreSQL (Supabase) + pgvector + SQLAlchemy + Alembic
- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **AI:** OpenAI-compatible LLM integration + local embedding model (BAAI/bge-small-en-v1.5)
- **Payments:** Razorpay TEST mode only — no real money is ever charged

---

## Problem Statement

E-commerce platforms face several challenges that AI can address:

| Problem | How AI Helps |
|---|---|
| Buyers describe needs in natural language, not keywords | Intent extraction converts free-text into structured search criteria |
| Keyword matching misses semantically related products | Vector embeddings enable meaning-based product discovery |
| Merchants lack visibility into catalog weaknesses | Readiness scoring identifies gaps across product attributes |
| Growth suggestions are generic and manual | Deterministic opportunity detection surfaces actionable, evidence-backed recommendations |
| Financial actions must be trustworthy and traceable | Approval gates, server-side verification, and append-only audit trails ensure accountability |

---

## Key Features

### Buyer Experience
- **Natural language intent extraction** — free-text messages parsed into structured category, budget, brand, requirements, and preferences
- **Semantic product search** — pgvector cosine similarity with deterministic business-rule filters applied before ranking
- **Conversational shopping assistant** — full chat flow: intent extraction → retrieval → LLM-generated product recommendations
- **Checkout with Razorpay test mode** — server-side order creation, payment verification, and inventory update

### Merchant Growth
- **AI Commerce Readiness scoring** — deterministic 0–100 score per product across 7 dimensions (description, category, price, inventory, delivery info, return policy, metadata)
- **Growth opportunity detection** — rule-based engine converts readiness issues into structured opportunities with evidence and financial impact estimates
- **Simulated discount execution** — approved opportunities can be executed with hard guardrails (max 10% discount), no real financial mutation

### Safety and Auditability
- **Approval gates** — every growth opportunity requires explicit merchant approval before any action
- **Append-only audit trail** — 17 event types logged with timestamps, actors, and sanitized metadata; merchant-isolated and secret-free
- **Server-side price authority** — backend re-reads product price from database at checkout; frontend price is never trusted
- **Idempotent payment verification** — duplicate verification attempts return existing state without re-charging
- **Deterministic fallback** — regex-based intent extraction activates when LLM is unavailable
- **No LLM financial authority** — the LLM never calculates discount amounts, processes payments, or modifies order state

---

## System Architecture

```
Buyer                                              Merchant
  │                                                  │
  ▼                                                  ▼
Natural Language Query                        Business/Product Signals
  │                                                  │
  ▼                                                  ▼
Intent Extraction (LLM)                       Readiness Scoring (Deterministic)
  │                                                  │
  ▼                                                  ▼
pgvector Semantic Search                      Opportunity Detection (Rule-based)
  │                                                  │
  ▼                                                  ▼
LLM Reasoning over Retrieved Products         AI Recommendations (LLM rephrasing)
  │                                                  │
  ▼                                                  ▼
Controlled Backend                            Approval Gate
  │                                                  │
  ▼                                                  ▼
Checkout + Razorpay Test Mode                 Bounded Simulated Execution
  │                                                  │
  ▼                                                  ▼
Append-Only Audit Trail ◄────────────────────────────┘
```

**Key architectural boundaries:**
- The LLM is a reasoning and language layer only
- The backend is the sole authority for business rules, pricing, payments, and state transitions
- Payment integration is Razorpay TEST mode — no real money is required or charged

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI 0.115.0 |
| Language | Python 3.11+ |
| ORM | SQLAlchemy 2.0.34 |
| Database | PostgreSQL (Supabase) |
| Vector search | pgvector 0.5.0 |
| Migrations | Alembic 1.13.1 |
| Embedding model | BAAI/bge-small-en-v1.5 (384 dimensions, local) |
| Embedding library | sentence-transformers |
| LLM integration | OpenAI-compatible API via httpx 0.27.2 |
| Frontend framework | Next.js 14.2.0 (App Router) |
| Frontend language | TypeScript 5.x |
| Styling | Tailwind CSS 3.4 |
| Payments | Razorpay (TEST mode, raw httpx — no SDK dependency) |

---

## Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry point, routers, CORS, health checks
│   │   ├── core/
│   │   │   └── config.py            # Pydantic BaseSettings (env vars, .env loading)
│   │   ├── db/
│   │   │   └── session.py           # SQLAlchemy engine, session factory, base class
│   │   ├── models/
│   │   │   ├── user.py              # User model (buyer/merchant/admin roles)
│   │   │   ├── merchant.py          # Merchant model with readiness score
│   │   │   ├── product.py           # Product model with pgvector embedding column
│   │   │   ├── order.py             # Order model with Razorpay fields
│   │   │   └── policy.py            # MerchantPolicy for negotiation rules
│   │   ├── api/v1/
│   │   │   ├── schemas.py           # All Pydantic request/response schemas
│   │   │   ├── merchants.py         # Merchant + growth API endpoints
│   │   │   ├── buyer.py             # Buyer intent, search, chat endpoints
│   │   │   ├── checkout.py          # Checkout, payment verification, webhook
│   │   │   ├── merchant_service.py  # Merchant creation logic
│   │   │   ├── order_service.py     # Order lifecycle (create, verify, webhook)
│   │   │   ├── razorpay_service.py  # Razorpay TEST mode integration
│   │   │   ├── readiness_service.py # Deterministic readiness scoring
│   │   │   ├── growth_opportunities_service.py  # Rule-based opportunity detection
│   │   │   ├── growth_service.py    # LLM-based growth recommendations
│   │   │   ├── approval_service.py  # Approval gate lifecycle
│   │   │   ├── simulated_execution_service.py   # Bounded simulated actions
│   │   │   └── audit_service.py     # Append-only audit trail
│   │   ├── ai/
│   │   │   ├── provider.py          # LLM provider abstraction (OpenAI-compatible)
│   │   │   ├── intent_service.py    # NL intent extraction + deterministic fallback
│   │   │   └── growth_service.py    # LLM growth recommendation generation
│   │   └── services/
│   │       ├── embeddings/
│   │       │   ├── model.py         # BAAI/bge-small-en-v1.5 wrapper
│   │       │   ├── product_text.py  # Product-to-text formatter for embeddings
│   │       │   └── pipeline.py      # Batched embedding generation
│   │       └── retrieval/
│   │           └── product_search.py # pgvector semantic search with filters
│   ├── alembic/                     # Database migrations (3 migrations)
│   ├── scripts/
│   │   ├── seed_demo_data.py        # Seed merchants, products, policies
│   │   ├── generate_product_embeddings.py  # CLI embedding generation
│   │   └── manual_buyer_chat_real.py       # Integration test script
│   ├── tests/                       # 247 tests across 15 test files
│   └── requirements.txt             # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # Root layout
│   │   │   ├── merchant/            # Merchant onboarding, dashboard, products, growth
│   │   │   └── buyer/               # Store selection, chat, checkout
│   │   ├── hooks/
│   │   │   └── useBuyerChat.ts      # Buyer chat API hook
│   │   ├── types/
│   │   │   └── buyer-chat.ts        # TypeScript interfaces for buyer flows
│   │   └── components/              # Reusable UI components (Button, Card, Input, Sidebar)
│   ├── package.json                 # Next.js, React, Tailwind dependencies
│   └── .env.local                   # NEXT_PUBLIC_API_BASE_URL
├── scripts/                         # Placeholder (empty)
├── docs/                            # Placeholder (empty)
└── .env.example                     # Environment variable template
```

---

## AI Architecture

### LLM Provider Abstraction

The system uses an OpenAI-compatible chat completions protocol via raw `httpx`. Any provider that exposes the `/chat/completions` endpoint (OpenAI, Azure, local models, etc.) can be used by configuring `LLM_BASE_URL`.

### How AI Is Used

| Function | AI or Deterministic? | Details |
|---|---|---|
| Intent extraction | LLM (with deterministic fallback) | Converts NL buyer messages to structured intent (category, budget, brand, requirements) |
| Product search | Deterministic (pgvector) | Cosine similarity over 384-dim embeddings with SQL-level business-rule filters |
| Buyer chat response | LLM | Generates conversational response with retrieved products as context |
| Readiness scoring | Deterministic | Rule-based scoring across 7 product dimensions, no LLM involvement |
| Growth opportunities | Deterministic | Rule engine converts readiness issues into structured opportunities |
| Growth recommendations | LLM (rephrasing only) | LLM rephrases deterministic issues into merchant-friendly language; never invents facts |
| Discount calculation | Deterministic | Hard math with guardrails (max 10%), no LLM involvement |
| Payment processing | Deterministic | Server-side Razorpay integration, HMAC-SHA256 verification |
| Audit logging | Deterministic | Thread-safe append-only store with merchant isolation |

### Deterministic Fallback

When the LLM is unavailable or returns invalid output, `intent_service.py` provides a regex-based `deterministic_extract_intent()` function that extracts category, budget, and brand patterns from the buyer's message. The system degrades gracefully rather than failing.

---

## Semantic Search

### Embedding Model

- **Model:** BAAI/bge-small-en-v1.5
- **Dimensions:** 384
- **Runtime:** Local via sentence-transformers (no API key required)
- **Normalization:** Embeddings are L2-normalized for cosine similarity

### Product Text Preparation

Product embeddings are generated from a canonical text representation that includes:
- Product name and category
- Description
- Delivery information
- Return policy
- Metadata

**Excluded from embeddings:** price, inventory quantity, merchant policies. Business rules never influence vector similarity — they are applied as SQL filters.

### Search Process

1. Structured intent (from LLM or fallback) is converted to a query text string
2. Query text is encoded to a 384-dimensional vector
3. **Deterministic SQL filters** are applied first: `merchant_id`, `is_active = True`, `inventory_quantity > 0`, `embedding IS NOT NULL`, optional `category`, `budget_min`, `budget_max`
4. Surviving products are ranked by pgvector cosine distance
5. Top 5 results are returned with similarity scores

---

## Merchant Growth Workflow

### Readiness Assessment

Each product is scored on a 0–100 scale across 7 dimensions:

| Dimension | What is evaluated |
|---|---|
| Description | Completeness and quality of product description |
| Category | Presence and appropriateness of category |
| Price | Reasonableness and formatting |
| Inventory | Stock availability |
| Delivery info | Delivery terms and information |
| Return policy | Return/exchange policy clarity |
| Metadata | Completeness of supplementary product data |

### Opportunity Detection

Readiness issues are converted into structured opportunities, each containing:
- **Issue:** What is wrong or missing
- **Evidence:** Specific data supporting the finding
- **Financial impact:** Estimated revenue effect (illustrative, not guaranteed)
- **Proposed action:** What the merchant should do
- **Guardrails:** Hard limits on any proposed financial action

### Approval and Execution

1. Opportunities are presented to the merchant
2. Merchant explicitly approves or denies each opportunity
3. Approved opportunities can be executed (simulated discount)
4. Execution enforces hard guardrails (max 10% discount)
5. All events are recorded in the audit trail

**Note:** Simulated execution does not modify real product prices or financial state. It demonstrates the approval-to-execution workflow with deterministic math.

---

## Checkout and Payments

### Flow

1. **Buyer initiates checkout** — selects a product and quantity
2. **Server-side order creation** — backend re-reads product price from database, calculates total, creates internal order record
3. **Razorpay order creation** — backend creates a Razorpay test-mode order via raw HTTP (no SDK dependency)
4. **Payment widget** — frontend loads Razorpay Checkout.js and opens the payment modal
5. **Server-side verification** — on payment success, frontend sends payment details to backend; backend verifies HMAC-SHA256 signature
6. **Order state update** — order transitions from `payment_created` → `paid`
7. **Inventory update** — inventory is decremented exactly once (idempotent)

### Order State Transitions

```
pending → payment_created → paid
                          → payment_failed → cancelled
```

### Safety Rules

- Backend re-reads the product price from the database — never trusts the frontend
- Payment signature verification occurs server-side only
- Duplicate verification attempts are idempotent (return existing state, no re-charge)
- Inventory is decremented only after verified payment
- All checkout events are recorded in the audit trail

### Test Mode

- **Razorpay is TEST/SANDBOX mode only** — no real money is required or charged
- Test card: `4111 1111 1111 1111` (success) / `4000 0000 0000 0002` (failure)
- The Razorpay test key ID is returned to the frontend from the backend checkout response — it is not hardcoded in the frontend

---

## Auditability and Safety

### Audit Trail

- **Append-only** in-memory store with thread-safe access
- **Merchant-isolated** — cross-merchant queries return empty results
- **Secret-free** — forbidden keys (API keys, passwords, tokens, PII, card numbers) are automatically stripped from metadata
- **17 event types** covering the full lifecycle: opportunity creation, approval, execution, checkout, payment verification, order state changes, inventory updates, and LLM failures

### Core Safety Principle

> **AI controls reasoning. Backend controls authority.**

- The LLM never calculates financial metrics, discount amounts, or payment values
- The LLM never directly modifies database records or order state
- The backend validates all business rules before any state change
- Approval gates require explicit human consent for growth actions
- Payment verification uses cryptographic signature validation
- Every financial action produces an audit event

### Failure Handling

- LLM failures are logged and the system falls back to deterministic extraction
- Audit trail failures do not block financial operations (non-blocking)
- Invalid state transitions are rejected with explicit error messages
- Idempotent operations prevent duplicate side effects

---

## Environment Variables

> **Never commit `.env` files.** Store secrets in `.env` at the project root.

### Backend (`backend/`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key |
| `LLM_API_KEY` | No | API key for LLM provider (default: empty) |
| `LLM_MODEL` | No | LLM model name (default: `gpt-4o-mini`) |
| `LLM_BASE_URL` | No | LLM API base URL (default: `https://api.openai.com/v1`) |
| `LLM_TIMEOUT_SECONDS` | No | LLM request timeout (default: `30.0`) |
| `RAZORPAY_KEY_ID` | No | Razorpay test mode key ID |
| `RAZORPAY_KEY_SECRET` | No | Razorpay test mode key secret |
| `RAZORPAY_WEBHOOK_SECRET` | No | Razorpay webhook verification secret |
| `CORS_ORIGINS` | No | Allowed CORS origins (default: `["http://localhost:3000"]`) |

### Frontend (`frontend/`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | No | Backend API URL (default: `http://127.0.0.1:8000`) |

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL database (or Supabase project)
- Razorpay test account (for payment testing)

### 1. Clone and configure

```powershell
git clone <repository-url>
cd AI_native_agentic_e-commerce
copy .env.example .env
```

Edit `.env` and fill in your database and API credentials.

### 2. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install the embedding dependency separately (not in requirements.txt):

```powershell
pip install sentence-transformers
```

### 3. Database migration

```powershell
cd backend
alembic upgrade head
```

### 4. Seed demo data (optional)

```powershell
cd backend
python -m scripts.seed_demo_data
```

This creates 3 merchants with 10 products each and negotiation policies.

### 5. Generate product embeddings

```powershell
cd backend
python -m scripts.generate_product_embeddings
```

Use `--rebuild` to regenerate all embeddings, or `--batch-size N` to control batch size.

### 6. Start the backend

```powershell
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### 7. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## API Documentation

Once the backend is running, interactive API documentation is available at:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

### Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/health/db` | Database connectivity check |
| `GET` | `/api/v1/merchants` | List active merchants |
| `POST` | `/api/v1/merchants` | Onboard a new merchant |
| `GET` | `/api/v1/merchants/{id}/products` | List merchant products |
| `POST` | `/api/v1/merchants/{id}/products` | Create a product |
| `GET` | `/api/v1/merchants/{id}/readiness` | Get AI readiness score |
| `GET` | `/api/v1/merchants/{id}/growth-recommendations` | Get growth recommendations |
| `POST` | `/api/v1/merchants/{id}/growth-opportunities` | Generate growth opportunities |
| `POST` | `/api/v1/merchants/{id}/growth-opportunities/{opp_id}/approve` | Approve/deny opportunity |
| `POST` | `/api/v1/merchants/{id}/growth-opportunities/{opp_id}/execute` | Execute simulated discount |
| `GET` | `/api/v1/merchants/{id}/audit-events` | List audit events |
| `POST` | `/api/v1/buyer/intent` | Extract buyer intent from NL message |
| `POST` | `/api/v1/buyer/search` | Semantic product search |
| `POST` | `/api/v1/buyer/chat` | AI shopping assistant chat |
| `POST` | `/api/v1/buyer/checkout` | Create order + Razorpay payment order |
| `POST` | `/api/v1/buyer/verify-payment` | Verify Razorpay payment signature |
| `POST` | `/api/v1/buyer/webhook/razorpay` | Razorpay webhook handler |

---

## Testing

The backend includes **247 tests** across 15 test files covering all major subsystems.

### Run all tests

```powershell
cd backend
pytest
```

### Run a specific test file

```powershell
cd backend
pytest tests/test_checkout.py
pytest tests/test_audit_trail.py
pytest tests/test_buyer_chat.py
```

### Test coverage

| Area | Test File | What is tested |
|---|---|---|
| Approval lifecycle | `test_approval.py` | Approval gate state transitions |
| Audit trail | `test_audit_trail.py` | Event recording, isolation, ordering |
| Buyer chat | `test_buyer_chat.py` | Chat endpoint, LLM integration, fallbacks |
| Buyer intent | `test_buyer_intent.py` | Intent extraction, deterministic fallback |
| Buyer search | `test_buyer_search.py` | Semantic search, filters, ranking |
| Checkout | `test_checkout.py` | Order creation, payment verification, webhooks |
| Growth opportunities | `test_growth_opportunities.py` | Opportunity detection, guardrails |
| Growth recommendations | `test_growth_recommendations.py` | LLM recommendation generation |
| Merchant onboarding | `test_merchant_onboarding.py` | Merchant creation, validation |
| Merchant listing | `test_merchants_list.py` | Merchant listing endpoint |
| Merchant products | `test_merchant_products.py` | Product CRUD operations |
| JSON parsing | `test_parse_json_response.py` | LLM response parsing |
| Product embeddings | `test_product_embeddings.py` | Embedding pipeline, generation |
| Readiness scoring | `test_readiness.py` | Deterministic readiness scoring |
| Simulated execution | `test_simulated_execution.py` | Bounded execution, guardrails |

---

## Example End-to-End Workflow

### Buyer Flow

```
1. Buyer navigates to /buyer and selects a merchant
2. Buyer sends: "I need a wireless headphone under ₹2000 with good bass"
3. Backend extracts structured intent:
   { category: "headphones", budget_max: 2000, requirements: ["wireless", "good bass"] }
4. pgvector semantic search finds matching products (deterministic filters applied)
5. LLM generates conversational response with product recommendations
6. Buyer selects "Buy Now" on a product
7. Backend creates order, reads price from DB, creates Razorpay test order
8. Buyer completes payment via Razorpay test widget
9. Backend verifies payment signature, updates order to "paid", decrements inventory
10. All events recorded in audit trail
```

### Merchant Flow

```
1. Merchant onboards at /merchant with business details
2. Merchant adds products at /merchant/products
3. Dashboard shows AI Commerce Readiness score (deterministic, 0-100)
4. Merchant generates growth opportunities at /merchant/growth
5. System detects issues: missing return policy, incomplete descriptions, low inventory
6. Each opportunity includes evidence, financial impact estimates, and guardrails
7. Merchant reviews and approves/denies each opportunity
8. Approved opportunities can be executed (simulated discount, max 10%)
9. Full audit trail available for each opportunity
```

---

## Security and Safety Notes

- **Never commit secrets.** `.env` files are gitignored. Use `.env.example` as a template.
- **Razorpay TEST mode only.** No real money is required or charged for this POC.
- **Frontend does not control authoritative price.** The backend re-reads product price from the database at checkout.
- **LLM does not directly control financial execution.** The LLM provides reasoning; the backend enforces business rules and processes payments.
- **Payment verification is server-side only.** HMAC-SHA256 signature validation occurs in the backend.
- **Inventory updates are idempotent.** Duplicate payment verifications do not decrement inventory multiple times.
- **Audit trail is secret-free.** API keys, passwords, tokens, and PII are automatically stripped from logged metadata.
- **Audit trail is merchant-isolated.** Cross-merchant data access is blocked at the service layer.

---

## Limitations

This is a **proof of concept**, not a production system. Known limitations include:

- **In-memory stores** — audit trail, approval state, and execution state are stored in memory; they reset on server restart
- **No authentication** — merchant identity is established via onboarding form and stored in browser session; there is no login system
- **No frontend tests** — backend has comprehensive test coverage; frontend has no test suite
- **Single-tenant design** — each merchant operates in isolation; no cross-merchant features
- **Simulated financial execution** — growth opportunity execution demonstrates the workflow but does not modify real product prices
- **No persistent LLM context** — each buyer chat request is stateless; conversation history is not persisted server-side
- **Embedding model not in requirements.txt** — sentence-transformers must be installed separately

---

## Future Improvements

> The following are potential enhancements, not currently implemented.

- Persistent audit trail (database-backed instead of in-memory)
- User authentication and session management
- Conversation history persistence
- Real discount/pricing execution with proper safeguards
- Multi-merchant marketplace features
- Frontend test suite
- Rate limiting and request throttling
- Webhook retry logic and dead-letter queue
- Admin dashboard for cross-merchant analytics

---

> **"AI controls reasoning. Backend controls authority."**
>
> **"Every money action is explainable, bounded, gated, and auditable."**
