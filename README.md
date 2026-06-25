# ADOPSHUN AI

**A privacy layer that sits between your users and any large language model.** ADOPSHUN AI detects and removes personally identifiable information (PII) from messages in real time, before a single character reaches an AI model — so your organisation can adopt AI without leaking sensitive data.

It ships as a complete product: a secure chat application, an administration console for managing detection policy, and a programmatic API that other systems can call directly.

---

## What it does

Every message is inspected by a layered detection pipeline before it is forwarded. Based on the type of information found, one of three actions is taken:

- **Block** — the message is stopped entirely (for example, when it contains an API key, a password, or a credit-card number).
- **Redact** — sensitive values are replaced with typed placeholders such as `[EMAIL]` or `[US_SSN]`, and only the redacted version is sent onward.
- **Audit** — the message passes through, but the detection is logged for reporting and compliance.

Nothing sensitive ever leaves your infrastructure. The AI model only ever sees redacted text.

---

## Features

### Detection
- **Layered pipeline** combining deterministic rules with deep-learning contextual recognition.
- **Deterministic stages** — regular expressions (emails, phone numbers, API keys, SSNs, crypto wallets, NHS numbers, PAN cards), a Luhn validator for card numbers, Shannon-entropy detection for secrets and tokens, and a code-injection detector.
- **Contextual recognition** — a fine-tuned GLiNER2 model identifies names, addresses, organisations, and other entities that regular expressions miss.
- **Context awareness** — a dedicated scoring stage reduces false positives by reading the words around each detection. It tells the difference between `password: hunter2` (a real credential) and `your password must be eight characters` (a policy discussion), and never drops a genuine detection on a coincidental keyword match.
- **Three-tier policy** — every entity type is assigned to Block, Redact, or Audit, configurable per user and per organisation.

### Policy management
- **Entity labels** — a drag-and-drop console to move any entity type between the Block, Redact, and Audit tiers. Click any label to see what it detects, with examples and detection methods.
- **Custom labels** — define organisation-specific entities. A description is enough; the system generates a matching detection pattern automatically.
- **Dictionaries** — add exact words and phrases that should always be treated as PII, including extensions to built-in labels.
- **Bulk import and export** — manage labels and dictionaries in spreadsheet form, with a round-trip that preserves dictionary terms.

### Models
- **Multiple language models** — choose between Gemini 3.5 Flash, Gemini 3.1 Pro, and Gemini 3.1 Flash-Lite from a selector in the chat interface.
- **Per-organisation control** — administrators decide which models their team may use and set a default.
- **Per-session locking** — once a conversation begins, its model is fixed for consistency.

### Programmatic API
- **API keys** — call the detection engine directly from your own systems, with no interactive login. Keys carry the `adpsh_` prefix, are stored only as a SHA-256 hash, and are shown in full exactly once.
- **Scopes** — each key is limited to the actions it needs.
- **Per-key rate limiting** — each key has its own configurable request-per-minute limit, isolated from every other key.
- **Usage metering** — total and recent call counts are recorded per key for auditing and billing.
- **Detection-only responses** — the API returns the verdict and redacted text as JSON and never invokes a language model, so callers can use their own.

### Documents and images
- **File upload** — extract and scan text from documents and images. Office formats and text-based PDFs are read directly; scanned PDFs and images are processed with optical character recognition.
- **Clear feedback** — oversized files, unreadable images, and processing errors return a precise message rather than failing silently.

### Administration and access control
- **Role-based access** — individual ("solo") users administer their own policy; organisation administrators manage the whole organisation; organisation members use the chat under the policy set for them.
- **Dashboard** — request volume, action breakdown, detected entity types, and most-flagged sequences, filterable by time window and by user.
- **Organisation management** — invite members in bulk and configure organisation-wide policy and quotas.
- **Guided tours** — first-run walkthroughs tailored to each type of user.

### Security
- Authentication via Clerk (JSON Web Tokens) for the application, and hashed API keys for programmatic access.
- Server-side request-forgery protection on any administrator-supplied endpoint.
- Strict scope enforcement on programmatic requests.
- Data minimisation — the programmatic detection path records only entity *types*, never the raw values.

---

## How the pipeline works

The pipeline stacks deterministic rules with deep learning to balance speed and accuracy.

### Deterministic stages (run first, no ML required)

| Stage | What it catches |
|---|---|
| Regex | Emails, phone numbers, API keys, SSNs, crypto wallets, NHS numbers, PAN cards |
| Luhn validator | Credit and debit card numbers (digit strings 13–19 characters that pass the Luhn checksum) |
| Shannon entropy | High-entropy tokens — cryptographic hashes, access tokens, base64 secrets |
| Code detector | Code injection, SQL, shell commands, markdown fences |

If any of these stages finds a **Block**-tier type, the pipeline returns immediately without calling the ML model. This keeps most blocked requests under 50ms.

### Deep-learning stage (GLiNER2)

Text that passes the deterministic checks is sent to the contextual recognition model, `fastino/gliner2-privacy-filter-PII-multi` — a fine-tuned variant of GLiNER2 that detects PII across multiple languages and identifies contextual entities (names, addresses, organisations) that regular expressions miss. The model accepts entity *descriptions* alongside the text, so it can classify arbitrary entity types at runtime without task-specific fine-tuning.

### Context scoring

Before a detection is acted upon, a context stage examines the surrounding text to suppress false positives — distinguishing genuine credentials and shared values from policy text, examples, and documentation.

### Priority merging

When multiple stages flag the same span, the pipeline merges overlapping detections and enforces the most severe tier:

1. **Block** — secrets, passwords, credit cards, code injection
2. **Redact** — emails, SSNs, passport numbers, driving licences
3. **Audit** — names, locations, organisations, IP addresses

---

## Architecture

```
Browser → Next.js :3000 → FastAPI :8000 → Docker ML :7860
                               ↓
                          PostgreSQL
                               ↓
                     Language model (streaming)
```

- **ML service** (`hf_space/`) — GLiNER2 wrapped in a FastAPI server, runs in Docker.
- **Backend** (`app/`) — FastAPI; handles authentication (Clerk and API keys), pipeline orchestration, language-model routing, chat sessions, statistics, and the administration API.
- **Frontend** (`frontend/`) — Next.js; Clerk authentication, chat interface, and administration console.

In production the ML service runs on a Hugging Face Space (CPU). Locally it runs in Docker and can use your GPU. Language-model routing is handled through a single provider-agnostic client, so additional providers and self-hosted endpoints can be added with minimal change as the product grows.

---

## Local setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker Desktop (with the WSL2 backend on Windows)
- An NVIDIA GPU is optional but strongly recommended (see the GPU section below)
- A [Clerk](https://clerk.com) account (the free tier is sufficient)

### 1. Clone and configure environment variables

```bash
git clone <repo-url>
cd pi-api
```

Create a `.env` file in the project root:

```ini
# Required
DATABASE_URL="postgresql://user:password@localhost:5432/piapi"
GEMINI_API_KEY="your-gemini-api-key"

# Clerk — get these from your Clerk dashboard
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_..."
CLERK_SECRET_KEY="sk_test_..."
CLERK_JWKS_URL="https://<your-instance>.clerk.accounts.dev/.well-known/jwks.json"

# ML service — points to the local Docker container
HF_SPACE_URL="http://127.0.0.1:7860"

# Optional
HF_TOKEN="your-huggingface-token"   # only needed if you hit HF Hub rate limits
MAX_UPLOAD_MB="50"                  # maximum upload size; must match your reverse proxy
```

> **No model key?** The application still works in pseudo-model mode — PII detection and redaction function fully, but the chat reply is a placeholder. This is useful for offline testing.

### 2. Start the ML service (Docker)

**CPU only (slower, around 2–3 seconds per request):**
```bash
docker build -t pi-api-ml ./hf_space
docker run -d -p 7860:7860 -e PYTHONUNBUFFERED=1 --name pi_ml_api pi-api-ml
```

**With GPU acceleration (around 150ms per request — recommended):**

Requires an NVIDIA GPU and Docker Desktop with the WSL2 backend.

```bash
docker build -t pi-api-ml ./hf_space
docker run -d --gpus all -p 7860:7860 -e PYTHONUNBUFFERED=1 --name pi_ml_api pi-api-ml
```

Wait for `GLiNER2 ready.` in the logs before proceeding:
```bash
docker logs -f pi_ml_api
```

The model (around 400 MB) is baked into the image during build and loads from the local cache — no internet connection is required at runtime.

### 3. Start the backend

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend auto-creates all database tables on first start via SQLAlchemy. Schema changes to existing tables are applied through the migrations in `alembic/`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Using the API

Create a key in the administration console (**Admin → API Keys**), then call the detection endpoint directly:

```bash
curl -X POST https://your-api-host/api/v1/check \
  -H "Authorization: Bearer adpsh_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "my SSN is 123-45-6789"}'
```

The response contains the action taken, the redacted message, and the list of detections — no language model is invoked:

```json
{
  "action": "REDACT",
  "was_redacted": true,
  "message": "my SSN is [US_SSN]",
  "detections": [
    { "type": "ssn", "start": 10, "end": 21, "value": "123-45-6789" }
  ]
}
```

The key inherits the policy (tiers, custom labels, and dictionaries) of the organisation that owns it.

---

## GPU acceleration

The ML service automatically uses a GPU if one is available (`torch.cuda.is_available()`). On CPU, dynamic quantisation (`torch.qint8`) is applied automatically to reduce memory usage and improve throughput.

**Observed latency (RTX 4050, 6 GB VRAM):**

| Mode | First request (JIT warmup) | Subsequent requests |
|---|---|---|
| CPU | 2,000–3,000ms | 2,000–3,000ms |
| GPU | around 1,100ms | 125–175ms |

Any NVIDIA GPU with 4 GB or more of VRAM and CUDA 11.8+ drivers will work.

---

## Deployment notes

- The production backend installs dependencies and restarts automatically on each push to `main` (see `.github/workflows/deploy.yml`).
- The reverse proxy must allow request bodies at least as large as `MAX_UPLOAD_MB` and should use a generous read timeout (120 seconds is recommended) so that OCR has time to run.
- New tables are created automatically on start; new columns on existing tables are applied via the Alembic migrations in `alembic/`.

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Google Gemini key — powers chat replies, automatic label generation, and tier prediction |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes | Clerk publishable key (frontend) |
| `CLERK_SECRET_KEY` | Yes | Clerk secret key (backend) |
| `CLERK_JWKS_URL` | Yes | Clerk JWKS endpoint for JWT validation |
| `HF_SPACE_URL` | Yes | URL of the ML service (`http://127.0.0.1:7860` locally) |
| `HF_TOKEN` | No | Hugging Face token — only needed if hitting download rate limits |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (defaults to `localhost:3000`) |
| `MAX_UPLOAD_MB` | No | Maximum upload size in megabytes (defaults to 50) |
