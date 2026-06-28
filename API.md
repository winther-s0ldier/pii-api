# ADOPSHUN AI — API Reference

The ADOPSHUN AI API lets you place PII detection and redaction between your application and any large language model, without using the chat interface. You send text, we return a verdict and a redacted version; no language model is ever invoked on our side, so you remain in control of which model you use.

- **Base URL:** `https://api.adopshun.com`
- **Content type:** `application/json`
- **Authentication:** API key (Bearer token)

---

## Authentication

Create a key in the admin console under **Admin → API Keys**. The full key is shown once at creation; store it securely. Keys are prefixed `adpsh_`.

Send it as a Bearer token on every request:

```
Authorization: Bearer adpsh_xxxxxxxxxxxxxxxxxxxxxxxx
```

A key inherits the policy (tiers, custom labels, and dictionaries) of the organisation that owns it. Keys cannot access admin endpoints.

### Scopes

Each key is limited to the actions it was granted:

| Scope | Grants |
|---|---|
| `check` | PII detection (`/api/v1/check`, `/api/v1/check_batch`, `/api/v1/preview`, `/api/v1/document/upload`) |
| `read:stats` | Read-only statistics (reserved) |

A request with a key that lacks the required scope returns `403`.

### Rate limits

Each key has its own per-minute limit (configurable at creation, default 60 requests/minute). Exceeding it returns `429`.

---

## Detect PII

```
POST /api/v1/check
```

Runs the detection pipeline over a single message and returns the verdict. No language model is called.

### Request

```json
{
  "message": "my email is bob@acme.com",
  "allowed_pii": [],
  "ignored_values": []
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | yes | The text to scan |
| `allowed_pii` | string[] | no | Entity types to allow through without redaction |
| `ignored_values` | string[] | no | Specific values to ignore |

### Response

```json
{
  "action": "REDACT",
  "was_redacted": true,
  "message": "my email is [EMAIL]",
  "tokenized": "my email is [EMAIL_0f32dc]",
  "vault": { "[EMAIL_0f32dc]": "bob@acme.com" },
  "detections": [
    { "type": "email", "subtype": "email", "confidence": "medium",
      "start": 12, "end": 24, "value": "bob@acme.com" }
  ]
}
```

| Field | Description |
|---|---|
| `action` | `BLOCK`, `REDACT`, `AUDIT`, or `CLEAN` (see below) |
| `was_redacted` | `true` when `action` is `REDACT` |
| `message` | The text with PII replaced by typed placeholders such as `[EMAIL]` |
| `tokenized` | The text with value-specific reversible tokens such as `[EMAIL_0f32dc]` |
| `vault` | Map of token to real value, for restoring values in your model's reply |
| `detections` | Each entity found, with its type, character span, and value |

### Actions

| Action | Meaning | What to do |
|---|---|---|
| `BLOCK` | The message contains high-risk data (API keys, passwords, card numbers) | Do not forward it to your model |
| `REDACT` | PII was found and replaced | Forward `message` (or `tokenized`) to your model |
| `AUDIT` | Lower-risk entities found; logged | Forward as you see fit |
| `CLEAN` | No PII | Forward the original text |

---

## Using it as a layer in front of your own model

```
1. POST the user's text to /api/v1/check
2. If action == "BLOCK": stop, show the user a privacy warning
3. Otherwise: send `tokenized` to your own LLM
4. Restore values in the model's reply using `vault`
```

The `tokenized`/`vault` pair gives you reversible tokenisation: your model only ever sees `[EMAIL_0f32dc]`, and you swap the tokens back for real values in its response. If you prefer simple one-way redaction, use `message` instead and ignore `vault`.

### Example (Python)

```python
import requests

KEY = "adpsh_xxxxxxxx"
HEAD = {"Authorization": f"Bearer {KEY}"}

def guard_and_ask(user_text, call_your_model):
    r = requests.post("https://api.adopshun.com/api/v1/check",
                      headers=HEAD, json={"message": user_text}).json()

    if r["action"] == "BLOCK":
        return "That message contained sensitive data and was blocked."

    # Send tokens to your own model; never the real PII
    reply = call_your_model(r["tokenized"])

    # Restore real values in the model's reply
    for token, value in (r.get("vault") or {}).items():
        reply = reply.replace(token, value)
    return reply
```

---

## Detect PII in bulk

```
POST /api/v1/check_batch
```

### Request

```json
{ "messages": ["first message", "second message"], "allowed_pii": [] }
```

Up to 100 messages per request. Returns one result per message:

```json
{
  "results": [
    { "status": "success", "action": "CLEAN", "was_redacted": false, "message": "first message", "redacted_types": [] },
    { "status": "blocked", "action": "BLOCK", "warning": "...", "blocked_types": [ ... ] }
  ]
}
```

---

## Errors

| Status | Meaning |
|---|---|
| `400` | Malformed request, or the document/text could not be processed |
| `401` | Missing or invalid API key |
| `403` | The key lacks the required scope, or attempted to reach an admin endpoint |
| `413` | Uploaded file exceeds the size limit |
| `422` | An uploaded image contained no readable text |
| `429` | Rate limit exceeded for this key |

Error bodies are JSON: `{ "detail": "..." }`.

---

## Notes

- We do not store the raw values you send on the programmatic path; only detection **types** are logged for usage metering. The `vault` is returned to you and never retained.
- All detection runs against your organisation's configured tiers, custom labels, and dictionaries — manage these in the admin console.
