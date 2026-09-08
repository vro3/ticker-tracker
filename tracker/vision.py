"""Read a stock screenshot + caption into structured data using Claude."""
import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import config

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": ["string", "null"], "description": "Primary ticker symbol, uppercase, no $ sign. Null if none visible."},
        "company": {"type": ["string", "null"]},
        "exchange": {"type": ["string", "null"]},
        "price": {"type": ["number", "null"], "description": "The main price shown for the ticker."},
        "currency": {"type": ["string", "null"]},
        "price_context": {"type": ["string", "null"], "description": "e.g. 'last', 'after hours', 'pre-market'"},
        "change_text": {"type": ["string", "null"], "description": "Any change shown, e.g. '+2.31 (1.4%) today'"},
        "timeframe_shown": {"type": ["string", "null"], "description": "Chart timeframe if visible, e.g. '1D', '1M', '1Y'"},
        "source_app": {"type": ["string", "null"], "description": "App the screenshot came from if recognizable"},
        "other_tickers": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "description": "0 to 1, how sure you are about ticker and price"},
        "goal": {"type": ["string", "null"], "description": "Plain-English restatement of what the sender said they expect or plan, from the caption. Null if no caption."},
        "direction": {"type": "string", "enum": ["up", "down", "watch", "unknown"]},
        "target_price": {"type": ["number", "null"]},
        "horizon_days": {"type": ["integer", "null"], "description": "Time frame implied by the caption, in days. Null if none."},
        "notes": {"type": ["string", "null"], "description": "Anything else worth knowing, one sentence."},
    },
    "required": ["ticker", "company", "exchange", "price", "currency", "price_context", "change_text",
                 "timeframe_shown", "source_app", "other_tickers", "confidence", "goal", "direction",
                 "target_price", "horizon_days", "notes"],
    "additionalProperties": False,
}

PROMPT = """This screenshot was texted to a small group that shares stock ideas. Extract what it shows.

Rules:
- ticker: the stock the screenshot is focused on (detail view, largest name). If it is a watchlist with no single focus, pick the first row and lower confidence; put the rest in other_tickers. Uppercase, no $ sign. Crypto and ETFs count too.
- price: the main current price shown for that ticker. Not a chart axis label, not a 52-week high.
- The sender's caption is below. Turn it into goal / direction / target_price / horizon_days. "watch" means they are only watching. "unknown" if there is no caption.
- If a field is not visible, use null. Do not guess a ticker from a logo alone unless you are confident.

Caption from sender: {caption}
"""


def media_type(path: Path) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix.lower(), "image/jpeg")


def extract(cfg: dict, image: Path | None, caption: str) -> dict:
    backend = cfg.get("vision_backend", "auto")
    if backend == "auto":
        backend = "api" if config.api_key(cfg) else "cli"
    if backend == "api":
        return _extract_api(cfg, image, caption)
    return _extract_cli(cfg, image, caption)


def _extract_api(cfg: dict, image: Path | None, caption: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=config.api_key(cfg) or None)
    content = []
    if image is not None:
        data = base64.standard_b64encode(image.read_bytes()).decode()
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type(image), "data": data}})
    prompt = PROMPT.format(caption=caption or "(none)")
    if image is None:
        prompt = "There is no screenshot, only a text message. Extract the ticker from the text.\n\n" + prompt
    content.append({"type": "text", "text": prompt})
    resp = client.messages.create(
        model=cfg.get("model", "claude-opus-5"),
        max_tokens=2048,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to read this image")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def _extract_cli(cfg: dict, image: Path | None, caption: str) -> dict:
    """Use the Claude Code CLI (uses the logged-in Claude subscription, no API key needed)."""
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    if not Path(claude).exists():
        raise RuntimeError("claude CLI not found; install Claude Code or set anthropic_api_key")
    prompt = PROMPT.format(caption=caption or "(none)")
    if image is not None:
        prompt = f"Read the image file at {image} (use the Read tool).\n\n" + prompt
    else:
        prompt = "There is no screenshot, only a text message. Extract the ticker from the text.\n\n" + prompt
    prompt += "\n\nRespond with ONLY a JSON object matching this schema, no prose, no code fences:\n" + json.dumps(SCHEMA)
    cmd = [claude, "-p", prompt, "--output-format", "json", "--allowedTools", "Read"]
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {proc.stderr.strip()[:400]}")
    outer = json.loads(proc.stdout)
    result = outer.get("result", "") if isinstance(outer, dict) else str(outer)
    if isinstance(outer, dict) and outer.get("is_error"):
        raise RuntimeError(f"claude CLI: {result[:300]} (run `claude` in Terminal on this Mac to log in)")
    return parse_json_loose(result)


def parse_json_loose(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))
