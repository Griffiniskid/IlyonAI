import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from datetime import timezone
from typing import Any, List, Optional

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.schemas.request import AgentRequest
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Chat, ChatMessage, User
from app.api.auth import get_optional_user

router = APIRouter()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _clean_agent_output(text: str) -> str:
    """
    Strip leaked ReAct scaffolding from the agent's final output.

    LangChain's ZERO_SHOT_REACT agent sometimes leaks its internal trace when
    the LLM doesn't follow the exact ReAct format — e.g. it outputs:
        Question: Hello
        Thought: ...
        Action: None
    instead of a clean Final Answer.  We detect this and extract the useful part.
    """
    if not text:
        return text

    # 1. If the text starts with "Question:" or "Thought:", it's leaked ReAct format.
    if re.match(r"^(Question|Thought|Action|Observation):", text.strip()):
        # First priority: extract a proper Final Answer if one is embedded
        final_match = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
        if final_match:
            return final_match.group(1).strip()

        # Second priority: a Thought that reads like a real answer (not meta-commentary)
        thought_match = re.search(
            r"Thought:\s*(.+?)(?=\n(?:Action|Observation|Final Answer|Question):|$)",
            text, re.DOTALL
        )
        if thought_match:
            thought = thought_match.group(1).strip()
            skip_phrases = ("i need to", "i should call", "i must use", "i will use", "let me check")
            if len(thought) > 20 and not any(thought.lower().startswith(p) for p in skip_phrases):
                return thought

        # Last resort: strip all ReAct labels AND the Question line entirely
        cleaned = re.sub(r"^Question:.*$", "", text, flags=re.MULTILINE)
        cleaned = re.sub(
            r"(Thought|Action Input|Action|Observation|Final Answer):\s*",
            "", cleaned
        ).strip()
        cleaned = re.sub(r"\bNone\b\s*", "", cleaned).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cleaned:
            return cleaned

    return text

# ── Simple per-key rate limiter ───────────────────────────────────────────────
# Stores last request timestamp per user_id (or IP for anonymous users).
# Minimum gap between requests: 0.5 seconds.
_last_request: dict[str, float] = {}
_MIN_GAP = 0.5  # seconds


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    last = _last_request.get(key, 0.0)
    if now - last < _MIN_GAP:
        wait = round(_MIN_GAP - (now - last), 1)
        raise HTTPException(status_code=429, detail=f"Too many requests. Please wait {wait}s.")
    _last_request[key] = now


def _auto_title(text: str) -> str:
    """Generate a chat title from the first user message (max 40 chars)."""
    clean = text.strip().replace("\n", " ")
    return clean[:40] + ("…" if len(clean) > 40 else "")


def _normalize_short_swap_query(query: str) -> str:
    """Normalize shorthand swap prompts like '🔄 Swap BNB → USDT'."""
    q = (query or "").strip()
    m = re.match(r"^\s*🔄\s*Swap\s+(?:([0-9]*\.?[0-9]+)\s+)?([A-Za-z0-9]+)\s*[→>-]+\s*([A-Za-z0-9]+)\s*$", q, re.IGNORECASE)
    if m:
        amount = m.group(1) or "0.01"
        src = m.group(2).upper()
        dst = m.group(3).upper()
        return f"Swap {amount} {src} to {dst}"
    return q


def _try_direct_swap(query: str, user_address: str, chain_id: int) -> Optional[str]:
    """
    Detect 'swap all/my X to Y' patterns and handle directly without the agent.
    Returns JSON string if handled, None if the agent should handle it.
    """
    import json
    from app.agents.crypto_agent import _build_swap_tx

    q = query.strip()
    # Normalize: insert space before common words glued to token name
    # e.g. "MARCOfrom" → "MARCO from", "BNBto" → "BNB to"
    q = re.sub(r'([A-Za-z0-9])(from|to|for|into|that|on)\b', r'\1 \2', q, flags=re.IGNORECASE)
    # Match: "swap all/my X to/for Y", "swap X that i have to Y", etc.
    patterns = [
        # "swap all BNB to USDT", "swap my BNB to USDT"
        r"swap\s+(?:all|my|entire|full)\s+([A-Za-z0-9]+)\s+(?:to|for|into)\s+([A-Za-z0-9]+)",
        # "swap all BNB that I have to USDT", "swap all BNB from my wallet to USDT"
        r"swap\s+(?:all|my|entire|full)\s+([A-Za-z0-9]+)\s+.*?(?:to|for|into)\s+([A-Za-z0-9]+)",
        # "swap BNB that i have on my wallet for USDT"
        r"swap\s+([A-Za-z0-9]+)\s+that\s+i\s+have\s+.*?(?:to|for|into)\s+([A-Za-z0-9]+)",
    ]
    # Map native token symbols to their chain IDs
    _NATIVE_CHAIN = {
        "BNB": 56, "WBNB": 56, "ETH": 1, "WETH": 1, "MATIC": 137,
        "AVAX": 43114, "FTM": 250, "CRO": 25, "MNT": 5000,
    }

    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            token_in = m.group(1).upper()
            token_out = m.group(2).upper()
            # Auto-detect chain from token (e.g. BNB → chain 56)
            effective_chain = _NATIVE_CHAIN.get(token_in, chain_id)
            swap_input = json.dumps({
                "chain": "evm",
                "token_in": token_in,
                "token_out": token_out,
                "amount": "all",
                "chain_id": effective_chain,
            })
            return _build_swap_tx(swap_input, user_address, effective_chain)
    return None


@router.post("/agent")
async def run_agent(
    request: Request,
    body: AgentRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    # Rate limit: 1 request per 0.5 seconds per user (or per IP for anonymous)
    rate_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")
    _check_rate_limit(rate_key)

    from app.agents.crypto_agent import build_agent  # imported lazily to avoid import-time errors

    direct_query = _normalize_short_swap_query(body.query)

    # ── Try direct swap-all handling (bypasses agent for "swap all X to Y") ──
    # Only use the direct result if the swap SUCCEEDED — errors fall through to the agent
    # so the AI can reason about the failure and suggest alternatives.
    direct_swap_result = _try_direct_swap(
        direct_query, body.user_address, body.chain_id
    )
    if direct_swap_result:
        try:
            _parsed_direct = json.loads(direct_swap_result)
            _direct_ok = _parsed_direct.get("status") == "ok"
        except (json.JSONDecodeError, AttributeError):
            _direct_ok = False

        if _direct_ok:
            # Success — save to chat history and return directly (fast path)
            provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
            if current_user:
                if provided_chat_id_early:
                    chat = db.query(Chat).filter(
                        Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                    ).first()
                else:
                    chat = None
                if not chat:
                    chat_id = str(uuid.uuid4())
                    chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                    db.add(chat)
                    db.flush()
                db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
                db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_swap_result))
                chat.updated_at = datetime.now(timezone.utc)
                db.commit()
                return {"session_id": chat.id, "chat_id": chat.id, "response": direct_swap_result}
            return {"session_id": body.session_id, "chat_id": None, "response": direct_swap_result}
        # Error from direct swap — fall through to let the agent handle it with reasoning

    # ── Determine session identity (no DB write yet — avoids orphan chats on error) ──
    provided_chat_id: Optional[str] = getattr(body, "chat_id", None)

    if current_user and provided_chat_id:
        existing = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
        effective_session_id = provided_chat_id if existing else str(uuid.uuid4())
    elif current_user:
        effective_session_id = str(uuid.uuid4())
    else:
        effective_session_id = body.session_id

    effective_query = direct_query

    # ── Build ordered list of models/providers to try ────────────────────────
    from app.agents.crypto_agent import _OPENROUTER_MODELS

    models_to_try: list[Optional[str]] = []
    if settings.api_keys.get("openai"):
        models_to_try.append("__openai__")
    if settings.api_keys.get("openrouter"):
        models_to_try.extend(_OPENROUTER_MODELS)
    if settings.api_keys.get("groq"):
        models_to_try.append("__groq__")
    if not models_to_try:
        raise HTTPException(status_code=503, detail="No LLM API key configured. Add openrouter, groq, or openai to API_KEYS in server/.env.")

    # ── Run the agent with provider fallback ─────────────────────────────────
    last_exc: Optional[Exception] = None

    for model in models_to_try:
        try:
            agent = build_agent(
                session_id=effective_session_id,
                user_address=body.user_address,
                solana_address=body.solana_address or "",
                chain_id=body.chain_id,
                openrouter_model=model,
            )
            result = await asyncio.wait_for(
                agent.ainvoke({"input": effective_query}),
                timeout=90.0,
            )
            response_text = _clean_agent_output(result.get("output", ""))

            # Safety net: if agent hit iteration limit, replace with user-friendly message
            if "agent stopped" in response_text.lower() and "iteration limit" in response_text.lower():
                response_text = (
                    "I wasn't able to fully process your request. "
                    "This can happen with complex multi-step operations. "
                    "Could you try rephrasing or breaking it into smaller steps? "
                    "For example, I can find the best pool for you, or help with a swap."
                )

            chat: Optional[Chat] = None
            if current_user:
                if provided_chat_id:
                    chat = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
                if not chat:
                    chat = Chat(
                        id=effective_session_id,
                        user_id=current_user.id,
                        title=_auto_title(body.query),
                    )
                    db.add(chat)
                    db.flush()
                db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
                db.add(ChatMessage(chat_id=chat.id, role="assistant", content=response_text))
                chat.updated_at = datetime.now(timezone.utc)
                if chat.title == "New Chat":
                    chat.title = _auto_title(body.query)
                db.commit()

            return {
                "session_id": effective_session_id,
                "chat_id": chat.id if chat else None,
                "response": response_text,
            }
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_exc = exc
            continue
        except Exception as exc:
            err_str = str(exc)

            # Retry on transient provider failures and quota/rate failures
            if (
                "429" in err_str
                or "rate" in err_str.lower()
                or "timed out" in err_str.lower()
                or "402" in err_str
                or "insufficient_quota" in err_str.lower()
                or "billing" in err_str.lower()
                or "credit" in err_str.lower()
                or "service unavailable" in err_str.lower()
                or "temporarily unavailable" in err_str.lower()
            ):
                last_exc = exc
                continue

            # Retry on auth errors too (next provider may work)
            if "401" in err_str or "user not found" in err_str.lower() or "unauthorized" in err_str.lower():
                last_exc = exc
                continue

            # Retry on provider package/config issues (e.g. optional provider not installed)
            if (
                isinstance(exc, ImportError)
                or "module not found" in err_str.lower()
                or "no module named" in err_str.lower()
                or "api key" in err_str.lower()
                or "configuration" in err_str.lower()
            ):
                last_exc = exc
                continue

            # Retry with next provider when a tool receives structured args unexpectedly
            if (
                "too many arguments to single-input tool" in err_str.lower()
                or "consider using structuredtool" in err_str.lower()
            ):
                last_exc = exc
                continue

            # LLM responded in plain text instead of ReAct format — extract and return
            if (
                "could not parse llm output" in err_str.lower()
                or "invalid format" in err_str.lower()
                or "output parsing" in err_str.lower()
                or "missing 'action'" in err_str.lower()
            ):
                import re as _re
                match = _re.search(r"Could not parse LLM output:\s*`(.*)`", err_str, _re.S)
                llm_text = _clean_agent_output(match.group(1).strip() if match else err_str)
                recovered_chat: Optional[Chat] = None
                if current_user:
                    try:
                        if provided_chat_id:
                            recovered_chat = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
                        if not recovered_chat:
                            recovered_chat = Chat(
                                id=effective_session_id,
                                user_id=current_user.id,
                                title=_auto_title(body.query),
                            )
                            db.add(recovered_chat)
                            db.flush()
                        db.add(ChatMessage(chat_id=recovered_chat.id, role="user", content=body.query))
                        db.add(ChatMessage(chat_id=recovered_chat.id, role="assistant", content=llm_text))
                        recovered_chat.updated_at = datetime.now(timezone.utc)
                        db.commit()
                    except Exception:
                        db.rollback()
                return {
                    "session_id": effective_session_id,
                    "chat_id": recovered_chat.id if recovered_chat else None,
                    "response": llm_text,
                }

            last_exc = exc

    if last_exc is not None:
        err_str = str(last_exc)
        if isinstance(last_exc, (asyncio.TimeoutError, TimeoutError)):
            raise HTTPException(status_code=504, detail="The AI agent took too long to respond. Please try again in a moment.")
        if (
            "context length" in err_str.lower()
            or "too many tokens" in err_str.lower()
            or "maximum context" in err_str.lower()
            or "max_tokens" in err_str.lower()
        ):
            raise HTTPException(status_code=400, detail="The current chat context is too large. Start a new chat and retry the request.")
        if "402" in err_str or "insufficient_quota" in err_str.lower() or "billing" in err_str.lower() or "credit" in err_str.lower():
            raise HTTPException(status_code=402, detail="AI provider credits are insufficient right now. Please top up credits or use another provider key.")
        if "429" in err_str or "rate" in err_str.lower():
            raise HTTPException(status_code=429, detail="All AI providers are currently rate-limited. Please wait a moment and try again.")
        if "401" in err_str or "user not found" in err_str.lower() or "unauthorized" in err_str.lower():
            raise HTTPException(status_code=401, detail="All configured AI provider keys failed authentication. Please update API_KEYS in server/.env and restart.")
        if isinstance(last_exc, ImportError) or "no module named" in err_str.lower():
            raise HTTPException(status_code=503, detail="An optional AI provider dependency is missing on the server. Please install required provider packages.")

    raise HTTPException(status_code=500, detail="The AI backend failed unexpectedly. Please try again.")


class RpcRequest(BaseModel):
    rpc_url: str
    method: str
    params: List[Any]


@router.post("/rpc-proxy")
async def rpc_proxy(req: RpcRequest):
    """Proxy for cross-chain RPC calls to bypass browser CORS."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                req.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": req.method, "params": req.params},
                timeout=10.0,
            )
            return {"result": resp.json().get("result", "0x0")}
    except Exception as e:
        return {"result": "0x0", "error": str(e)}
