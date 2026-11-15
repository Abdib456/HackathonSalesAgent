# entry point: runs one full cycle
#
#   python -m agent.main          one cycle, then exit
#   python -m agent.main --loop   a cycle every 15 minutes, forever (on the laptop)
#
# Each cycle looks at where everything is up to and does whatever is ready.
# Anything waiting on a human or not set up yet (missing keys, instagram.py /
# signups.py not written) is skipped and logged, never fatal.
#
# POSTING=manual (default, see config.py): research, plans and the report run;
# humans film, edit and post, and moving a plan to approved/ marks it posted.
# make_reels / publish / dms only run with POSTING=api.
#
# Contract for the parts still to be written:
#   agent/tools/instagram.py   publish(plan, video_path, run) -> media_id   (logs "reel_published")
#                              reply_to_keyword_comments(run) -> int        (DMs sent)
#   agent/analytics/signups.py fetch() -> [{"email", "signed_up", "free_edit_used", "paid", "ref"}]

import os
import sys
import time
import traceback
from datetime import datetime, timezone

from agent import budget, config, logger
from agent.analytics import reports
from agent.tools import email, make_reel, propose, research, voiceover
from agent.tools.write_script import write_script

LOOP_MINUTES = 15
TARGET_WAITING_PLANS = 2   # keep this many plans ready for filming, no more
MAX_NEW_PLANS_PER_DAY = 2  # limits Claude spend and how much the team has to film
MAX_REJECTED_IN_BRIEF = 5  # most recent rejections passed to write_script
MAX_RESEARCH_CHARS = 4000  # cap on the research brief passed to write_script
VERSION_GAP_HOURS = 24     # hook versions of the same footage go out a day apart

# Used until there's sales data to learn from. Move to agent/prompts/ with the context commit.
DEFAULT_ANGLES = [
    "before/after: one photo, three outfits tried on",
    "stop buying clothes you never wear",
    "getting ready for an event with nothing to wear",
]


def _configured(*keys: str) -> bool:
    return all(os.getenv(k) for k in keys)


def _optional(module: str, attr: str):
    """A function from a module that may not be written yet, or None."""
    try:
        mod = __import__(f"agent.{module}", fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


def _skip(run, step: str, reason: str) -> None:
    logger.log_event(run, "step_skipped", step=step, reason=reason)


# --- Steps -----------------------------------------------------------------

def step_research(run) -> None:
    """Once a day: Tavily searches + Claude summary -> data/research/<date>.md."""
    if not _configured("TAVILY_API_KEY", "ANTHROPIC_API_KEY"):
        return _skip(run, "research", "TAVILY_API_KEY / ANTHROPIC_API_KEY not set")
    if research.done_today():
        return  # normal for 95 of 96 cycles a day, not worth a log line
    research.research(run)


def step_approvals(run) -> None:
    """Log plan moves as touches (approved/ = posted or go-ahead, rejected/ = no).

    Runs every cycle, so touches are logged even when no other step needs the plans.
    With manual posting, an approved plan *is* a posted reel, so it's recorded as
    published here; the report and learning loop then treat it like any other reel.
    """
    approved = propose.approved_plans()
    propose.rejected_ideas()
    if config.MANUAL:
        published = {e["reel_id"] for e in reports._run_events("reel_published")}
        for plan in approved:
            if plan["reel_id"] not in published:
                logger.log_event(run, "reel_published", reel_id=plan["reel_id"], manual=True)


def step_new_plans(run) -> None:
    """Keep a couple of reel plans ready for the team to film."""
    if not _configured("ANTHROPIC_API_KEY"):
        return _skip(run, "new_plans", "ANTHROPIC_API_KEY not set")
    waiting = [p for p in propose.PENDING.glob("reel-*.md")
               if not (make_reel.CREATIVES / f"{p.stem}.mp4").exists()] if propose.PENDING.exists() else []
    today = datetime.now(timezone.utc).date().isoformat()
    made_today = sum(1 for e in reports._run_events("plan_proposed") if e["timestamp"].startswith(today))
    if len(waiting) >= TARGET_WAITING_PLANS or made_today >= MAX_NEW_PLANS_PER_DAY:
        return _skip(run, "new_plans", f"{len(waiting)} waiting, {made_today} made today")

    # Learn from sales (Stripe, free read, at most twice a day) and DMs. Only from a
    # reel people actually responded to: a posted reel with 0 sales and 0 DMs isn't
    # "best", and copying it would lock every future plan onto it.
    sales = []
    if _configured("STRIPE_READ_KEY"):
        try:
            from agent.analytics import stripe_sales
            sales = stripe_sales.sales()
        except Exception as e:  # a Stripe hiccup shouldn't stop the plan being written
            logger.log_event(run, "sales_unavailable", step="new_plans", error=str(e))
    best = [r for r in reports.top_reels(reports.by_reel(sales, []), n=1) if r["gbp"] > 0 or r["dms"] > 0]
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
    if not _configured("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        return _skip(run, "voiceovers", "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set")
    for path in sorted(propose.PENDING.glob("reel-*.md")) if propose.PENDING.exists() else []:
        try:
            voiceover.make_voiceover(propose.read_plan(path), run)
        except budget.BudgetExceeded:
            raise
        except Exception as e:  # e.g. bad key or no credits: log once, retry next cycle
            logger.log_event(run, "voiceover_failed", reel_id=path.stem, error=str(e))
            break


def step_make_reels(run) -> None:
    """Edit any plan whose footage has arrived (pending, or approved before it was edited)."""
    if config.MANUAL:
        return _skip(run, "make_reels", "POSTING=manual: the team edits by hand")
    plans = [p for d in (propose.PENDING, propose.APPROVED) if d.exists() for p in d.glob("reel-*.md")]
    for path in sorted(plans):
        if not (make_reel.CREATIVES / f"{path.stem}.mp4").exists():
            make_reel.make_reel(propose.read_plan(path), run)  # logs "waiting" if footage missing


def step_publish(run) -> None:
    """Publish reels the human approved: the main reel first, then one hook version a day."""
    if config.MANUAL:
        return _skip(run, "publish", "POSTING=manual: the team posts by hand")
    publish = _optional("tools.instagram", "publish")
    if not publish:
        return _skip(run, "publish", "instagram.publish not written yet")
    events = reports._run_events("reel_published")
    published = {e["reel_id"] for e in events}
    now = datetime.now(timezone.utc)
    for plan in propose.approved_plans():
        last = max((datetime.fromisoformat(e["timestamp"]) for e in events
                    if propose.base_id(e["reel_id"]) == plan["reel_id"]), default=None)
        if last and (now - last).total_seconds() < VERSION_GAP_HOURS * 3600:
            continue  # a version of this footage went out recently
        for v in propose.versions(plan):  # versions you deleted from creatives/ are skipped
            video = make_reel.CREATIVES / f"{v['reel_id']}.mp4"
            if v["reel_id"] not in published and video.exists():
                publish(v, video, run)
                break  # at most one post per plan per cycle


def step_dms(run) -> None:
    if config.MANUAL:
        return _skip(run, "dms", "POSTING=manual: reels say 'link in bio', no DMs")
    reply = _optional("tools.instagram", "reply_to_keyword_comments")
    if not reply:
        return _skip(run, "dms", "instagram.reply_to_keyword_comments not written yet")
    reply(run)


def step_emails(run, signups: list[dict]) -> None:
    if not signups:
        return _skip(run, "emails", "no signups data")
    if not _configured("RESEND_API_KEY", "EMAIL_FROM"):
        return _skip(run, "emails", "RESEND_API_KEY / EMAIL_FROM not set")
    if os.getenv("APP_LIVE", "").lower() == "true":
        for s in signups:
            email.send(s["email"], "launch", run, ref=s.get("ref") or "")
    if _configured("STRIPE_PAYMENT_LINK"):
        for s in signups:
            if s.get("free_edit_used") and not s.get("paid"):
                email.send(s["email"], "payment_nudge", run, ref=s.get("ref") or "")


def step_report(run, signups: list[dict]) -> None:
    if not _configured("STRIPE_READ_KEY"):
        return _skip(run, "report", "STRIPE_READ_KEY not set")
    reports.build(signups)


# --- Cycle -----------------------------------------------------------------

def cycle() -> None:
    run = logger.start_run("cycle")
    fetch = _optional("analytics.signups", "fetch")
    signups = []
    steps = [
        ("approvals", lambda: step_approvals(run)),
        ("research", lambda: step_research(run)),
        ("new_plans", lambda: step_new_plans(run)),
        ("voiceovers", lambda: step_voiceovers(run)),
        ("make_reels", lambda: step_make_reels(run)),
        ("publish", lambda: step_publish(run)),
        ("dms", lambda: step_dms(run)),
        ("signups", lambda: signups.extend(fetch() if fetch else [])),
        ("emails", lambda: step_emails(run, signups)),
        ("report", lambda: step_report(run, signups)),
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
