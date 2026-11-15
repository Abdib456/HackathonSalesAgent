# entry point: runs one full cycle
#
#   python -m agent.main          one cycle, then exit
#   python -m agent.main --loop   a cycle every 15 minutes, forever
#
# Each cycle looks at where everything is up to and does whatever is ready.
# The agent researches, writes reel plans (and AI voiceovers), learns from
# sales and rejections, and reports profit. Humans film, edit and post by hand,
# then move the plan to approvals/approved/ (= posted).
# Anything not set up yet (missing keys) is skipped and logged, never fatal.
#
# To add a step (e.g. DMs, emails): write a step_<name>(run) function below and
# add it to the list in cycle(). See "Scaling later" in the README.

import os
import sys
import time
import traceback
from datetime import datetime, timezone

from agent import budget, config, logger
from agent.analytics import reports
from agent.tools import propose, research, voiceover
from agent.tools.write_script import write_script

LOOP_MINUTES = 15
TARGET_WAITING_PLANS = 2   # keep this many plans ready for filming, no more
MAX_NEW_PLANS_PER_DAY = 2  # limits Claude spend and how much the team has to film
MAX_REJECTED_IN_BRIEF = 5  # most recent rejections passed to write_script
MAX_RESEARCH_CHARS = 4000  # cap on the research brief passed to write_script

# Used until there's sales data to learn from. Taken from the audience and claims
# in agent/prompts/system.md: keep them in step if that changes.
DEFAULT_ANGLES = [
    "a photo you love, let down by the outfit: change just the clothes, keep everything else",
    "other AI editors warp your face and jewellery; only the area you outline changes",
    "see a piece on yourself, in your own photo, before you buy it",
]


def _configured(*keys: str) -> bool:
    return all(os.getenv(k) for k in keys)


def _skip(run, step: str, reason: str) -> None:
    logger.log_event(run, "step_skipped", step=step, reason=reason)


# --- Steps -----------------------------------------------------------------

def step_approvals(run) -> None:
    """Log plan moves as touches, and record each plan in approved/ as a posted reel.

    Runs every cycle, so touches are logged even when no other step needs the plans.
    The report and learning loop then treat a posted plan like any other reel.
    """
    approved = propose.approved_plans()
    propose.rejected_ideas()
    published = {e["reel_id"] for e in reports._run_events("reel_published")}
    for plan in approved:
        if plan["reel_id"] not in published:
            logger.log_event(run, "reel_published", reel_id=plan["reel_id"], manual=True)


def step_research(run) -> None:
    """Once a day: Tavily searches + Claude summary -> data/research/<date>.md."""
    if not _configured("TAVILY_API_KEY", "ANTHROPIC_API_KEY"):
        return _skip(run, "research", "TAVILY_API_KEY / ANTHROPIC_API_KEY not set")
    if research.done_today():
        return  # normal for 95 of 96 cycles a day, not worth a log line
    research.research(run)


def step_new_plans(run) -> None:
    """Keep a couple of reel plans ready for the team to film."""
    if not _configured("ANTHROPIC_API_KEY"):
        return _skip(run, "new_plans", "ANTHROPIC_API_KEY not set")
    waiting = list(propose.PENDING.glob("reel-*.md")) if propose.PENDING.exists() else []
    today = datetime.now(timezone.utc).date().isoformat()
    made_today = sum(1 for e in reports._run_events("plan_proposed") if e["timestamp"].startswith(today))
    if len(waiting) >= TARGET_WAITING_PLANS or made_today >= MAX_NEW_PLANS_PER_DAY:
        return _skip(run, "new_plans", f"{len(waiting)} waiting, {made_today} made today")

    # Learn from sales (Stripe, free read). Only from a reel that actually sold:
    # copying a posted reel with no sales would lock every future plan onto it.
    sales = []
    if _configured("STRIPE_READ_KEY"):
        try:
            from agent.analytics import stripe_sales
            sales = stripe_sales.sales()
        except Exception as e:  # a Stripe hiccup shouldn't stop the plan being written
            logger.log_event(run, "sales_unavailable", step="new_plans", error=str(e))
    best = [r for r in reports.top_reels(reports.by_reel(sales), n=1) if r["gbp"] > 0]
    if best and best[0].get("idea"):
        brief = f"A fresh variation on our best reel so far: '{best[0]['idea']}' (hook: '{best[0]['hook']}')"
    else:
        # Rotate through all angles over time (made_today is only ever 0 or 1).
        made_ever = len(reports._run_events("plan_proposed"))
        brief = DEFAULT_ANGLES[made_ever % len(DEFAULT_ANGLES)]

    # Steer away from what the human rejected (latest few, to keep the prompt short).
    rejected = propose.rejected_ideas()[-MAX_REJECTED_IN_BRIEF:]
    if rejected:
        brief += "\n\nAvoid ideas like these, which we rejected:\n" + "\n".join(
            f"- '{r['idea']}' (hook: '{r['hook']}')" + (f", reason: {r['reason']}" if r["reason"] else "")
            for r in rejected)

    findings = research.latest_brief()[:MAX_RESEARCH_CHARS]
    if findings:
        brief += "\n\nThis week's research (use it if it helps, don't copy it):\n" + findings
    propose.propose(write_script(brief, run), run)


def step_voiceovers(run) -> None:
    """AI voiceover (ElevenLabs) for each plan waiting to be filmed, once."""
    if not config.ai_voice():
        return _skip(run, "voiceovers", "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set")
    for path in sorted(propose.PENDING.glob("reel-*.md")) if propose.PENDING.exists() else []:
        try:
            voiceover.make_voiceover(propose.read_plan(path), run)
        except budget.BudgetExceeded:
            raise
        except Exception as e:  # e.g. bad key or no credits: log once, retry next cycle
            logger.log_event(run, "voiceover_failed", reel_id=path.stem, error=str(e))
            break


def step_report(run) -> None:
    if not _configured("STRIPE_READ_KEY"):
        return _skip(run, "report", "STRIPE_READ_KEY not set")
    reports.build()


# --- Cycle -----------------------------------------------------------------

def cycle() -> None:
    run = logger.start_run("cycle")
    steps = [
        ("approvals", lambda: step_approvals(run)),
        ("research", lambda: step_research(run)),
        ("new_plans", lambda: step_new_plans(run)),
        ("voiceovers", lambda: step_voiceovers(run)),
        ("report", lambda: step_report(run)),
    ]
    for name, fn in steps:
        try:
            fn()
        except budget.BudgetExceeded as e:
            logger.log_event(run, "budget_blocked", step=name, error=str(e))
            print(e)
        except Exception as e:  # one broken step must not stop the others
            logger.log_event(run, "step_failed", step=name, error=str(e), trace=traceback.format_exc()[-1500:])
            print(f"[{name}] failed: {e}")
    logger.log_event(run, "run_finished", spent_total_gbp=budget.total_spent())
    print(f"Cycle done. Spend £{budget.total_spent():.2f} of £{config.BUDGET_CAP_GBP:.0f}. Log: {run.name}")


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            cycle()
            time.sleep(LOOP_MINUTES * 60)
    else:
        cycle()
