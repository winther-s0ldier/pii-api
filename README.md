# PII Detection — Hybrid Model Architecture

A three-service stack for detecting and anonymising personally identifiable information (PII) in real time.

> **Running the live demo?** The hosted version (Render + Hugging Face Space) runs the ML model on CPU, which adds 2–3 seconds to each detection. For sub-200ms inference, run the stack locally with GPU acceleration enabled (see below).

---

## How it works

The pipeline stacks deterministic rules with deep learning to balance speed and accuracy.

### Deterministic stages (run first, no ML required)

| Stage | What it catches |
|---|---|
| Regex | Emails, phone numbers, API keys, SSNs, crypto wallets, NHS numbers, PAN cards |
| Luhn validator | Credit and debit card numbers (digit strings 13–19 chars that pass the Luhn checksum) |
| Shannon entropy | High-entropy tokens — cryptographic hashes, access tokens, base64 secrets |
| Code detector | Code injection, SQL, shell commands, markdown fences |

If any of these stages finds a **BLOCK**-tier type (API key, credit card, code), the pipeline returns immediately without calling the ML model. This keeps most blocked requests under 50ms.

### Deep learning stage (GLiNER2)

Text that passes the deterministic checks is sent to the contextual NER model. We use `fastino/gliner2-privacy-filter-PII-multi`, a fine-tuned variant of GLiNER2 that detects PII across multiple languages and identifies contextual entities (names, addresses, organisations) that regular expressions miss.

GLiNER takes entity *descriptions* as input alongside the text, which lets it classify arbitrary entity types at runtime without task-specific fine-tuning. This avoids the overhead of large language models.

### Priority merging

When multiple stages flag the same span, the pipeline merges overlapping detections and enforces the most severe tier:

1. **BLOCK** — secrets, passwords, credit cards, code injection
2. **REDACT** — emails, SSNs, passport numbers, driver's licences
3. **AUDIT** — names, locations, organisations, IP addresses

---

## Architecture

```
Browser → Next.js :3000 → FastAPI :8000 → Docker ML :7860
                               ↓
                          PostgreSQL
                               ↓
                        LLM (streaming)
```

- **ML service** (`hf_space/`) — GLiNER2 wrapped in a FastAPI server, runs in Docker
- **Backend** (`app/`) — FastAPI, handles auth (Clerk JWT), pipeline orchestration, chat sessions, stats
- **Frontend** (`frontend/`) — Next.js, Clerk auth, chat UI, admin dashboard

In production the ML service runs on a Hugging Face Space (CPU). Locally it runs in Docker and can use your GPU.

---

## Local setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker Desktop (with the WSL2 backend on Windows)
- An NVIDIA GPU is optional but strongly recommended (see GPU section below)
- A [Clerk](https://clerk.com) account (free tier is sufficient)

### 1. Clone and configure environment variables

```bash
git clone <repo-url>
cd pi-api
```

Create a `.env` file in the project root:

```ini
# Required
DATABASE_URL="postgresql://user:password@localhost:5432/piapi"
LLM_API_KEY="your-llm-api-key"

# Clerk — get these from your Clerk dashboard
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_..."
CLERK_SECRET_KEY="sk_test_..."
CLERK_JWKS_URL="https://<your-instance>.clerk.accounts.dev/.well-known/jwks.json"

# ML service — points to the local Docker container
HF_SPACE_URL="http://127.0.0.1:7860"

# Optional
HF_TOKEN="your-huggingface-token"   # only needed if you hit HF Hub rate limits
```

> **No LLM key?** The app still works in pseudo-LLM mode — PII detection and redaction function fully, but the chat reply will be a placeholder. Useful for offline testing.

### 2. Start the ML service (Docker)

**CPU only (slower, ~2–3s per request):**
```bash
docker build -t pi-api-ml ./hf_space
docker run -d -p 7860:7860 -e PYTHONUNBUFFERED=1 --name pi_ml_api pi-api-ml
```

**With GPU acceleration (~150ms per request — recommended):**

Requires an NVIDIA GPU and Docker Desktop with the WSL2 backend.

```bash
docker build -t pi-api-ml ./hf_space
docker run -d --gpus all -p 7860:7860 -e PYTHONUNBUFFERED=1 --name pi_ml_api pi-api-ml
```

Wait for `GLiNER2 ready.` in the logs before proceeding:
```bash
docker logs -f pi_ml_api
```

The model (~400 MB) is baked into the image during build and loads from the local cache — no internet connection required at runtime.

### 3. Start the backend

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend auto-creates all database tables on first start via SQLAlchemy.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## GPU acceleration

The ML service automatically uses a GPU if one is available (`torch.cuda.is_available()`). On CPU, dynamic quantisation (`torch.qint8`) is applied automatically to reduce memory usage and improve throughput.

**Observed latency (RTX 4050, 6 GB VRAM):**

| Mode | First request (JIT warmup) | Subsequent requests |
|---|---|---|
| CPU | 2,000–3,000ms | 2,000–3,000ms |
| GPU | ~1,100ms | 125–175ms |

Any NVIDIA GPU with 4 GB+ VRAM and CUDA 11.8+ drivers will work.

---

## Why is the hosted version slower?

The live demo runs on:
- **Render free tier** — FastAPI backend, shared CPU, cold starts after inactivity
- **Hugging Face Space** — ML model on CPU (no GPU available on the free tier)

Cold starts (after ~15 minutes of inactivity) can add 10–30 seconds on the first request while the HF Space wakes up. Subsequent requests settle to 2–3 seconds for the ML stage. Running locally with a GPU removes both of these constraints.

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `LLM_API_KEY` | ✅ | LLM API key for chat responses |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | ✅ | Clerk publishable key (frontend) |
| `CLERK_SECRET_KEY` | ✅ | Clerk secret key (backend) |
| `CLERK_JWKS_URL` | ✅ | Clerk JWKS endpoint for JWT validation |
| `HF_SPACE_URL` | ✅ | URL of the ML service (`http://127.0.0.1:7860` locally) |
| `HF_TOKEN` | ❌ | Hugging Face token — only needed if hitting download rate limits |
| `ALLOWED_ORIGINS` | ❌ | Comma-separated CORS origins (defaults to `localhost:3000`) |
