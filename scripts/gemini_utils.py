import time
import json
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Token ledger – written after every Gemini call so the parent process
# (main.py) can diff before/after each subprocess to get per-script costs.
# ---------------------------------------------------------------------------
_LEDGER_PATH = Path(__file__).parent.parent / "data" / ".token_ledger.json"

def _update_ledger(prompt_tokens: int, output_tokens: int) -> None:
    """Atomically adds token counts to the shared JSON ledger file."""
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _LEDGER_PATH.exists():
            ledger = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        else:
            ledger = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        ledger["prompt_tokens"]  += prompt_tokens
        ledger["output_tokens"]  += output_tokens
        ledger["total_tokens"]   += prompt_tokens + output_tokens
        _LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    except Exception as e:
        logging.warning(f"[token_ledger] Could not update ledger: {e}")

def read_ledger() -> dict:
    """Returns the current ledger totals (zeros if the file doesn't exist yet)."""
    try:
        if _LEDGER_PATH.exists():
            return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logging.warning(f"[token_ledger] Could not read ledger: {e}")
    return {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

def reset_ledger() -> None:
    """Resets the ledger to zero (called by main.py at the start of each run)."""
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(
            json.dumps({"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logging.warning(f"[token_ledger] Could not reset ledger: {e}")

# ---------------------------------------------------------------------------
# Gemini pricing (USD per 1 000 000 tokens, as of Gemini 2.5 Flash)
# Adjust MODEL_PRICING if you switch models.
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, dict[str, float]] = {
    # model-name-fragment -> {input: $/1M, output: $/1M}
    "gemini-3.5-flash":  {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash":  {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash":  {"input": 0.10,  "output": 0.40},
    "gemini-1.5-flash":  {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":    {"input": 1.25,  "output": 5.00},
}

def _get_pricing(model: str) -> dict[str, float]:
    """Returns the $/1M token rates for the given model string."""
    model_lower = model.lower()
    for key, rates in MODEL_PRICING.items():
        if key in model_lower:
            return rates
    # Fallback: use flash pricing
    logging.warning(f"[token_ledger] No pricing found for model '{model}'; defaulting to gemini-2.5-flash rates.")
    return MODEL_PRICING["gemini-2.5-flash"]

def tokens_to_usd(prompt_tokens: int, output_tokens: int, model: str) -> float:
    """Converts token counts to estimated USD cost."""
    rates = _get_pricing(model)
    return (prompt_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

# ---------------------------------------------------------------------------

def query_gemini(client, model, contents, config=None, retries=5, delay=20):
    """
    Wrapper for client.models.generate_content that adds automatic retries,
    a mandatory delay after querying to handle rate limits, and token tracking.
    """
    try:
        for attempt in range(1, retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                time.sleep(delay)  # mandatory delay to stay within rate limits

                # --- Token tracking ---
                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    prompt_tok  = getattr(usage, "prompt_token_count",     0) or 0
                    output_tok  = getattr(usage, "candidates_token_count", 0) or 0
                    _update_ledger(prompt_tok, output_tok)

                return response
            except Exception as e:
                logging.warning(f"[Attempt {attempt}/{retries}] Gemini query failed: {e}")
                if attempt < retries:
                    time.sleep(delay * attempt)  # Backoff before retry
                else:
                    raise e
    except Exception as e:
        logging.error(f"query_gemini error: {e}")
        raise e

