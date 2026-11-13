# entry point: runs one full cycle
#
#   python -m agent.main          one cycle, then exit (Replit Scheduled Deployment)
#   python -m agent.main --loop   a cycle every 15 minutes, forever (Reserved VM / laptop)
#
# Each cycle looks at where everything is up to and does whatever is ready.
# Anything waiting on a human (footage, approval) or not set up yet (missing
# keys, instagram.py / signups.py not written) is skipped and logged, never fatal.
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
from agent.tools import email, make_reel, propose
from agent.tools.write_script import write_script

LOOP_MINUTES = 15
TARGET_WAITING_PLANS = 2   # keep this many plans ready for filming, no more
MAX_NEW_PLANS_PER_DAY = 2  # limits Claude spend and how much the team has to film

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

    best = reports.top_reels(reports.by_reel([], []), n=1)
    if best and best[0].get("idea"):
        brief = f"A fresh variation on our best reel so far: '{best[0]['idea']}' (hook: '{best[0]['hook']}')"
    else:
        brief = DEFAULT_ANGLES[made_today % len(DEFAULT_ANGLES)]
    propose.propose(write_script(brief, run), run)


def step_make_reels(run) -> None:
    """Edit any plan whose footage has arrived (pending, or approved before it was edited)."""
    plans = [p for d in (propose.PENDING, propose.APPROVED) if d.exists() for p in d.glob("reel-*.md")]
    for path in sorted(plans):
        if not (make_reel.CREATIVES / f"{path.stem}.mp4").exists():
            make_reel.make_reel(propose.read_plan(path), run)  # logs "waiting" if footage missing


def step_publish(run) -> None:
    """Publish reels the human approved."""
    publish = _optional("tools.instagram", "publish")
    if not publish:
        return _skip(run, "publish", "instagram.publish not written yet")
    published = {e["reel_id"] for e in reports._run_events("reel_published")}
    for plan in propose.approved_plans():  # also logs each approval as a touch
        video = make_reel.CREATIVES / f"{plan['reel_id']}.mp4"
        if plan["reel_id"] not in published and video.exists():
            publish(plan, video, run)


def step_dms(run) -> None:
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
            email.send(s["email"], "launch", run)
    if _configured("STRIPE_PAYMENT_LINK"):
        for s in signups:
            if s.get("free_edit_used") and not s.get("paid"):
                email.send(s["email"], "payment_nudge", run)


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
        ("new_plans", lambda: step_new_plans(run)),
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
