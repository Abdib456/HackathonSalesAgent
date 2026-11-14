# daily research brief: what's working in fashion / try-on reels this week
#
# Once a day: ~8 Tavily searches (official search API, no scraping), then one
# Claude call that turns the results into a short brief with source links.
# Saved to data/research/YYYY-MM-DD.md; step_new_plans passes the latest
# brief into write_script.
#
# Tavily only sees the query strings below, so they decide what comes back.
# The summary uses the same agent/prompts/system.md + brand.md as
# write_script, so once that context is filled in, Claude keeps only what's
# relevant to our app. Edit QUERIES to retarget the searches.
#
# Spend: Tavily runs on partner credits (assumed £0, confirm in #support and
# change TAVILY_GBP_PER_SEARCH if not). Each search still goes through
# budget.check/record so the log shows every call. Keep pay-as-you-go off.

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from agent import budget, config, logger
from agent.tools.write_script import MODEL, _cost_gbp, _system_prompt

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_GBP_PER_SEARCH = 0.0  # partner credits; 1 credit per basic search
RESULTS_PER_QUERY = 5
SNIPPET_CHARS = 600  # per result, keeps the Claude prompt (and cost) small
MAX_TOKENS = 4000
RESEARCH_DIR = config.ROOT / "data" / "research"

QUERIES = [
    "AI virtual outfit try-on app trends",
    "fashion Instagram reels hooks that go viral",
    "UK fashion trends this week",
    "outfit ideas reels before and after",
    "virtual try-on app marketing Instagram",
    "what to wear event outfit trend UK",
    "AI photo editing app launch Instagram growth",
    "Instagram reels algorithm changes",
]

TASK = """Below are this week's web search results. Write a short research brief
for whoever plans our next Instagram reels.

Sections:
1. Trends worth riding (3-5 bullets)
2. Hook and format ideas seen working (3-5 bullets)
3. What similar apps are doing (2-4 bullets)
4. Anything to avoid

Rules:
- Only use what's in the results. Cite each point with its source URL in brackets.
- Skip anything not relevant to the product described above.
- No invented numbers or claims. Keep it under 350 words. Markdown, no preamble.
"""


def brief_path(day: str | None = None) -> Path:
    return RESEARCH_DIR / f"{day or datetime.now(timezone.utc).date().isoformat()}.md"


def done_today() -> bool:
    return brief_path().exists()


def latest_brief() -> str:
    """The newest brief's summary (without the sources list), or '' if none yet."""
    files = sorted(RESEARCH_DIR.glob("*.md")) if RESEARCH_DIR.exists() else []
    if not files:
        return ""
    text = files[-1].read_text(encoding="utf-8")
    return text.split("\n## All sources")[0].split("\n", 1)[-1].strip()  # drop title line and sources


def _search(query: str) -> list[dict]:
    """One Tavily search over the past week."""
    budget.check(TAVILY_GBP_PER_SEARCH, "tavily: search")
    body = {"query": query, "topic": "general", "search_depth": "basic",
            "max_results": RESULTS_PER_QUERY, "time_range": "week"}
    req = urllib.request.Request(
        TAVILY_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {config.require('TAVILY_API_KEY')}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    budget.record(TAVILY_GBP_PER_SEARCH, "tavily: search", query=query, credits=1)
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "content": (r.get("content") or "")[:SNIPPET_CHARS]} for r in data.get("results", [])]


def _summarise(results: dict, run: Path) -> tuple[str, str]:
    """One Claude call: results -> brief. Returns (brief, model used)."""
    system = _system_prompt()
    blocks = []
    for query, items in results.items():
        blocks.append(f"### Search: {query}")
        blocks += [f"- {r['title']} ({r['url']})\n  {r['content']}" for r in items]
    user = f"{TASK}\n\n" + "\n".join(blocks)

    estimate = _cost_gbp("worst", (len(system) + len(user)) // 3, MAX_TOKENS)
    budget.check(estimate, "claude: research summary")
    logger.log_event(run, "claude_request", tool="research", model=MODEL, system=system, prompt=user)

    client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low"},  # summarising, not planning
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    cost = _cost_gbp(response.model, response.usage.input_tokens, response.usage.output_tokens)
    budget.record(cost, "claude: research summary", model=response.model, request_id=response._request_id,
                  input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
    if response.stop_reason in ("refusal", "max_tokens"):
        logger.log_event(run, "claude_failed", tool="research", stop_reason=response.stop_reason)
        raise RuntimeError(f"research summary stopped early: {response.stop_reason}")

    brief = next(b.text for b in response.content if b.type == "text").strip()
    logger.log_event(run, "claude_reply", tool="research", model=response.model, cost_gbp=round(cost, 4), brief=brief)
    return brief, response.model


def research(run: Path) -> Path:
    """Run today's searches, summarise them, save data/research/<date>.md."""
    results = {}
    for query in QUERIES:
        try:
            results[query] = _search(query)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            # one failed search shouldn't lose the rest
            logger.log_event(run, "research_search_failed", query=query, error=str(e))
    found = sum(len(v) for v in results.values())
    if not found:
        raise RuntimeError("research: every Tavily search failed or returned nothing")

    brief, model = _summarise(results, run)
    sources = "\n".join(f"- [{r['title'] or r['url']}]({r['url']})" for items in results.values() for r in items)
    path = brief_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Research brief {path.stem} (Tavily search + {model} summary, AI-generated)\n\n"
                    f"{brief}\n\n## All sources\n{sources}\n", encoding="utf-8")
    logger.log_event(run, "research_done", path=str(path.relative_to(config.ROOT)),
                     searches=len(results), results=found)
    return path


if __name__ == "__main__":
    run = logger.start_run("research")
    print(f"Saved {research(run)}")
    print(f"Spent so far: £{budget.total_spent():.2f} of £{config.BUDGET_CAP_GBP:.0f}")
