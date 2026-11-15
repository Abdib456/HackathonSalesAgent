# daily report: profit, touches, and sales per reel
#
# One table per day in logs/reports/, so we (and the judges) can see overall
# profit = net sales - spend, and which reel made money. No personal data, only
# counts. top_reels() feeds back into write_script: make more of what sells.
#
# How the events join up:
#   main.step_approvals -> run event "reel_published" {reel_id} (plan moved to approved/)
#   stripe_sales        -> sales with "reel" = client_reference_id (set by the app from ?ref,
#                          once it passes it on; until then sales show as "unknown")

import json
from collections import defaultdict
from datetime import datetime, timezone

from agent import budget, config
from agent.tools import propose

REPORTS_DIR = config.LOGS_DIR / "reports"


def _run_events(*names: str) -> list[dict]:
    events = []
    for path in sorted(config.RUNS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get("event") in names:
                    events.append(e)
    return events


def _ideas() -> dict:
    ideas = {}
    for folder in (propose.PENDING, propose.APPROVED):
        for p in folder.glob("reel-*.md") if folder.exists() else []:
            plan = propose.read_plan(p)
            ideas[plan["reel_id"]] = {"idea": plan["script"]["idea"], "hook": plan["script"]["hook"]}
    return ideas


def by_reel(sales: list[dict]) -> dict:
    """Per reel: posted? -> sales -> £ (sales without a reel go under "unknown")."""
    rows = defaultdict(lambda: {"published": False, "sales": 0, "gbp": 0.0})
    for e in _run_events("reel_published"):
        rows[e["reel_id"]]["published"] = True
    for s in sales:
        if s["before_freeze"]:
            r = rows[s.get("reel") or "unknown"]
            r["sales"] += 1
            r["gbp"] = round(r["gbp"] + s["gbp"], 2)
    ideas = _ideas()
    for reel_id, r in rows.items():
        r.update(ideas.get(reel_id, {}))
    return dict(rows)


def top_reels(rows: dict, n: int = 3) -> list[dict]:
    """Best posted reels by money. For write_script to learn from."""
    ranked = sorted(((k, v) for k, v in rows.items() if k != "unknown" and v["published"]),
                    key=lambda kv: kv[1]["gbp"], reverse=True)
    return [{"reel_id": k, **v} for k, v in ranked[:n]]


def touches_count() -> int:
    if not config.TOUCHES_LOG.exists():
        return 0
    return sum(1 for l in config.TOUCHES_LOG.read_text(encoding="utf-8").splitlines() if l.strip())


def write_report(stripe_summary: dict, rows: dict) -> str:
    """Save today's report to logs/reports/YYYY-MM-DD.md and return it."""
    spend = budget.total_spent()
    profit = round(stripe_summary["net_gbp"] - spend, 2)
    lines = [
        f"# Report {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "",
        f"- Net sales (live, before freeze, minus refunds/chargebacks): £{stripe_summary['net_gbp']:.2f}"
        f" from {stripe_summary['sales_count']} sales",
        f"- Spend: £{spend:.2f} of £{config.BUDGET_CAP_GBP:.0f}",
        f"- **Profit: £{profit:.2f}**",
        f"- Human touches logged: {touches_count()}", "",
        "| Reel | Idea | Hook | Posted | Sales | £ |",
        "|---|---|---|---|---|---|",
    ]
    for reel_id, r in sorted(rows.items()):
        lines.append(f"| {reel_id} | {r.get('idea', '')} | {r.get('hook', '')} "
                     f"| {'yes' if r['published'] else 'no'} | {r['sales']} | {r['gbp']:.2f} |")
    text = "\n".join(lines) + "\n"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.md").write_text(text, encoding="utf-8")
    return text


def build() -> str:
    """Fetch live sales, join everything, save and return the report."""
    from agent.analytics import stripe_sales
    sales = stripe_sales.sales()
    return write_report(stripe_sales.summary(sales), by_reel(sales))


if __name__ == "__main__":
    print(build())
