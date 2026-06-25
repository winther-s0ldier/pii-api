"""
LLM abstraction layer — one interface over Gemini, OpenAI, Anthropic, and any
OpenAI-compatible self-hosted endpoint (Ollama, vLLM, Azure, private models).

Built on litellm so adding a provider is a config entry, not new code.
The pipeline always redacts BEFORE anything reaches here, so no provider ever
sees raw PII.
"""
import os
import logging
from typing import AsyncGenerator, Optional

import litellm

logger = logging.getLogger(__name__)

# litellm is chatty by default; keep our logs clean
litellm.drop_params = True          # silently drop params a provider doesn't support
litellm.suppress_debug_info = True

# ── Catalogue ──────────────────────────────────────────────────────────────────
# key = litellm model id. provider env var must be present for the model to be
# offered to users (see get_available_models).
SUPPORTED_MODELS: dict[str, dict] = {
    "gemini/gemini-3.5-flash":       {"display": "Gemini 3.5 Flash",      "tier": "fast",     "provider": "gemini", "env": "GEMINI_API_KEY"},
    "gemini/gemini-3.1-pro-preview": {"display": "Gemini 3.1 Pro",        "tier": "powerful", "provider": "gemini", "env": "GEMINI_API_KEY"},
    "gemini/gemini-3.1-flash-lite":  {"display": "Gemini 3.1 Flash-Lite", "tier": "fast",     "provider": "gemini", "env": "GEMINI_API_KEY"},
}

DEFAULT_MODEL = "gemini/gemini-3.5-flash"
CUSTOM_MODEL_ID = "custom"   # virtual id → org-configured self-hosted endpoint

SYSTEM_PROMPT = (
    "You are a helpful AI assistant. If you receive a message containing redacted information tags (like [TAX_ID], [PERSON], [EMAIL], etc.), you MUST explicitly acknowledge in your reply that the user's sensitive information was safely redacted for privacy, and provide your best answer based on the context.\n\n"
    "CRITICAL WRITING STYLE GUIDELINES (HUMANIZE YOUR TONE):\n"
    "1. Avoid AI Vocabulary: Never use words like delve, crucial, testament, underscore, landscape, tapestry, vibrant, pivotal, foster, or intricate.\n"
    "2. Avoid Sycophancy: Never use servile openers or closers like 'Great question!', 'I hope this helps!', 'You're absolutely right!', or 'Certainly!'. Just answer directly.\n"
    "3. No Formatting Crutches: Do NOT use em dashes (—), en dashes (–), or emojis. Avoid excessive boldface. Avoid formulaic vertical lists with bolded headers.\n"
    "4. Natural Rhythm: Vary your sentence lengths. Avoid predictable, robotic cadences. Do not force ideas into groups of three.\n"
    "5. Direct and Active: Use active voice. Avoid filler phrases ('In order to...', 'Due to the fact...'). Never end with generic upbeat conclusions ('The future looks bright', 'Exciting times lie ahead').\n"
    "6. Be Direct: Get straight to the point. Avoid rhetorical openers like 'Let's dive in' or 'Here's what you need to know'. Avoid fake-candid phrases like 'Honestly?' or 'Real talk'."
)


def _custom_configured(org) -> bool:
    cfg = getattr(org, "llm_config", None) if org else None
    return bool(cfg and cfg.get("base_url") and cfg.get("model_name"))


def get_available_models(user=None, org=None) -> list[dict]:
    """
    Models offered to this user, filtered by:
      - which provider API keys are configured on the server
      - org.allowed_models allowlist (if the org set one)
      - user.allowed_models allowlist (if the user has one)
    Plus the org's custom endpoint if configured.
    """
    org_allow = set(getattr(org, "allowed_models", None) or [])
    user_allow = set(getattr(user, "allowed_models", None) or [])
    default_model = getattr(org, "default_model", None) if org else None

    out = []
    for model_id, meta in SUPPORTED_MODELS.items():
        if not os.getenv(meta["env"]):
            continue
        if org_allow and model_id not in org_allow:
            continue
        if user_allow and model_id not in user_allow:
            continue
        out.append({
            "id": model_id,
            "display": meta["display"],
            "tier": meta["tier"],
            "provider": meta["provider"],
            "is_default": model_id == default_model,
        })

    if _custom_configured(org):
        cfg = org.llm_config
        out.append({
            "id": CUSTOM_MODEL_ID,
            "display": cfg.get("display_name") or f"{getattr(org, 'name', 'Custom')} Model",
            "tier": "custom",
            "provider": "custom",
            "is_default": default_model == CUSTOM_MODEL_ID,
        })

    return out


def resolve_model(requested: Optional[str], session=None, user=None, org=None) -> str:
    """
    Pick the model id to use, in priority order:
      1. explicit request  2. session.model_used  3. user default
      4. org default        5. system default
    Falls back to system default if the chosen model isn't actually available.
    """
    available = {m["id"] for m in get_available_models(user, org)}

    candidates = [
        requested,
        getattr(session, "model_used", None) if session else None,
        (getattr(user, "allowed_models", None) or [None])[0],
        getattr(org, "default_model", None) if org else None,
        DEFAULT_MODEL,
    ]
    for c in candidates:
        if c and c in available:
            return c

    return DEFAULT_MODEL if DEFAULT_MODEL in available or not available else next(iter(available))


def _to_chat_messages(history, system_prompt: str, new_message: str) -> list[dict]:
    """DB messages → OpenAI-style chat array litellm understands."""
    msgs = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = "assistant" if m.role == "model" else "user"
        if m.role == "blocked":
            continue
        msgs.append({"role": role, "content": m.content})
    msgs.append({"role": "user", "content": new_message})
    return msgs


def _call_kwargs(model_id: str, org) -> dict:
    """Provider-specific kwargs for litellm.acompletion."""
    if model_id == CUSTOM_MODEL_ID:
        cfg = org.llm_config
        # OpenAI-compatible servers (Ollama, vLLM, Azure, private) take api_base
        return {
            "model": f"openai/{cfg['model_name']}",
            "api_base": cfg["base_url"],
            "api_key": cfg.get("api_key") or "not-needed",
        }
    return {"model": model_id}


async def stream_response(
    model_id: str,
    history,
    new_message: str,
    org=None,
    system_prompt: str = SYSTEM_PROMPT,
    timeout: int = 45,
) -> AsyncGenerator[str, None]:
    """
    Stream the assistant reply as text chunks. `history` is a list of DB
    Message objects (chronological, excluding the new message).
    Raises on provider error — caller decides how to surface it.
    """
    messages = _to_chat_messages(history, system_prompt, new_message)
    kwargs = _call_kwargs(model_id, org)

    # Preserve existing Gemini grounding behaviour (web search)
    if kwargs["model"].startswith("gemini/"):
        kwargs["tools"] = [{"googleSearch": {}}]

    resp = await litellm.acompletion(
        messages=messages,
        stream=True,
        timeout=timeout,
        **kwargs,
    )
    async for chunk in resp:
        try:
            delta = chunk.choices[0].delta.content
        except (AttributeError, IndexError):
            delta = None
        if delta:
            yield delta
