# writes the reel script, caption, and comment-keyword CTA
#
# One Claude call per reel idea. In the same call Claude writes 5 hooks and
# scores them; the code (not Claude) picks the highest score and puts it on
# screen in scene 1. The rest are kept, ranked, for hook versions later.
# Product and brand context come from
# agent/prompts/*.md, so this file stays generic. Every call is checked
# against the budget first, recorded after, and logged to the run transcript.

import json
from pathlib import Path

import anthropic

from agent import budget, config, logger

MODEL = "claude-opus-5-5"
MAX_TOKENS = 8000  # thinking + answer; a script is short

# USD per million tokens (input, output). Anything not listed (e.g. a
# fallback model) is priced at the higher rate so spend is never under-counted.
PRICES_USD = {"claude-opus-5-5": (4.0, 20.0)}
FALLBACK_PRICE_USD = (5.0, 25.0)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

TASK = """Write one Instagram reel for the product described above.

Rules:
- 25-30 seconds total. The first 2 seconds must hook a stranger scrolling past.
{cta}
- Only use footage we can film ourselves or app screen recordings. No
  celebrities, brands, music or content we don't own.
- The reel is made with AI help: the caption must include a short, honest AI note.
- No fake claims, fake reviews or invented user numbers.

Hooks:
- Write 5 hooks, each in a different style: question, bold claim,
  before/after, POV, number.
- Score each 1-10, honestly and strictly, on: would it stop a stranger
  scrolling within 2 seconds; is it specific, not generic; can it be read on
  screen in under 8 words; is it true. Give a one-line reason.
- Build the reel around the highest-scoring hook: it is scene 1's on-screen text.
"""

N_HOOKS = 5

CTA = {
    "manual": "- End with a call to action: tap the link in our bio to try it.\n"
              "- Set keyword to an empty string (no comment keyword).",
    "api": "- End with a call to action: comment ONE keyword to get the link by DM.\n"
           "- The keyword is a single short word in capitals, easy to type.",
}


def _task() -> str:
    return TASK.format(cta=CTA["manual" if config.MANUAL else "api"])

SCHEMA = {
    "type": "object",
    "properties": {
        "idea": {"type": "string", "description": "One-line summary of the reel"},
        "hooks": {
            "type": "array",
            "description": f"{N_HOOKS} candidate hooks: on-screen text for the first 2 seconds",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "style": {"type": "string", "description": "question, bold claim, before/after, POV or number"},
                    "score": {"type": "integer", "description": "1-10"},
                    "reason": {"type": "string"},
                },
                "required": ["text", "style", "score", "reason"],
                "additionalProperties": False,
            },
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "string", "description": "e.g. 0-2"},
                    "shot": {"type": "string", "description": "What to film or show"},
                    "on_screen_text": {"type": "string"},
                    "voiceover": {"type": "string"},
                },
                "required": ["seconds", "shot", "on_screen_text", "voiceover"],
                "additionalProperties": False,
            },
        },
        "keyword": {"type": "string"},
        "caption": {"type": "string"},
    },
    "required": ["idea", "hooks", "scenes", "keyword", "caption"],
    "additionalProperties": False,
}


def _system_prompt() -> str:
    parts = [(PROMPTS_DIR / name).read_text(encoding="utf-8") for name in ("system.md", "brand.md")]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _cost_gbp(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = PRICES_USD.get(model, FALLBACK_PRICE_USD)
    usd = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return usd * config.USD_TO_GBP


def pick_hook(script: dict) -> dict:
    """Rank the hooks by score (ties keep Claude's order), use the best one in scene 1."""
    hooks = [h for h in script.get("hooks", []) if h.get("text", "").strip()]
    if not hooks or not script.get("scenes"):
        raise RuntimeError("write_script returned no usable hooks or scenes")
    for h in hooks:
        h["score"] = max(1, min(10, int(h["score"])))
    script["hooks"] = sorted(hooks, key=lambda h: h["score"], reverse=True)
    script["hook"] = script["hooks"][0]["text"]
    script["scenes"][0]["on_screen_text"] = script["hook"]
    return script


def write_script(brief: str, run: Path) -> dict:
    """Ask Claude for one reel script. `brief` is today's angle, e.g. 'before/after try-on'."""
    system = _system_prompt()
    user = f"{_task()}\nToday's angle: {brief}"

    # Worst case: every output token used, input estimated at ~3 chars per token
    estimate = _cost_gbp("worst", (len(system) + len(user)) // 3, MAX_TOKENS)
    budget.check(estimate, "claude: write_script")
    logger.log_event(run, "claude_request", tool="write_script", model=MODEL, brief=brief, system=system, prompt=user)

    client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if Opus declines, Anthropic retries on its recommended model
    )

    cost = _cost_gbp(response.model, response.usage.input_tokens, response.usage.output_tokens)
    budget.record(cost, "claude: write_script", model=response.model, request_id=response._request_id,
                  input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)

    if response.stop_reason in ("refusal", "max_tokens"):
        logger.log_event(run, "claude_failed", tool="write_script", stop_reason=response.stop_reason)
        raise RuntimeError(f"write_script stopped early: {response.stop_reason}")

    text = next(b.text for b in response.content if b.type == "text")
    script = pick_hook(json.loads(text))
    logger.log_event(run, "claude_reply", tool="write_script", model=response.model, cost_gbp=round(cost, 4), script=script)
    return script


if __name__ == "__main__":
    import sys

    run = logger.start_run("write_script")
    result = write_script(" ".join(sys.argv[1:]) or "before/after outfit try-on", run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSpent so far: £{budget.total_spent():.2f} of £{config.BUDGET_CAP_GBP:.0f}")
