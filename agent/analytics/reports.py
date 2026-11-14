# joins it all by reel + keyword: comments -> DMs -> signups -> sales
#
# One table per day in logs/reports/, so we (and the judges) can see which
# reel made money, plus overall profit = net sales - spend. No personal data,
# only counts. top_reels() feeds back into write_script: make more of what sells.
#
# Contract with the other tools (so their events can be joined here):
#   make_reel  -> run event "reel_made"       {reel_id}
#   instagram  -> run event "reel_published"  {reel_id, media_id}
#   instagram  -> save_outbound("instagram_dm", ..., reel_id=...)
#   signups    -> rows with "ref" = reel_id (from ?client_reference_id / ?ref)
#   stripe     -> sales with "reel" = client_reference_id

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


def _dms_by_reel() -> dict:
    counts = defaultdict(int)
    for p in config.OUTBOUND_DIR.glob("*_instagram_dm.json"):
        counts[json.loads(p.read_text(encoding="utf-8")).get("reel_id") or "unknown"] += 1
    return counts


def _ideas() -> dict:
    ideas = {}
    for folder in (propose.PENDING, propose.APPROVED):
        for p in folder.glob("reel-*.md") if folder.exists() else []:
            for v in propose.versions(propose.read_plan(p)):  # each hook version is its own row
                ideas[v["reel_id"]] = {"idea": v["script"]["idea"], "hook": v["script"]["hook"],
                                       "keyword": v["script"]["keyword"]}
    return ideas


def by_reel(sales: list[dict], signups: list[dict]) -> dict:
    """Funnel per reel: made -> published -> DMs -> signups -> free edits -> sales -> £."""
    rows = defaultdict(lambda: {"made": False, "published": False, "dms": 0, "signups": 0,
                                "free_edits": 0, "sales": 0, "gbp": 0.0})
    for e in _run_events("reel_made"):
        rows[e["reel_id"]]["made"] = True
    for e in _run_events("reel_published"):
        rows[e["reel_id"]]["published"] = True
    for reel, n in _dms_by_reel().items():
        rows[reel]["dms"] += n
    for s in signups:
        r = rows[s.get("ref") or "unknown"]
        r["signups"] += 1
        r["free_edits"] += bool(s.get("free_edit_used"))
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
    """Best reels by money, then DMs. For write_script to learn from."""
    ranked = sorted(((k, v) for k, v in rows.items() if k != "unknown" and v["published"]),
                    key=lambda kv: (kv[1]["gbp"], kv[1]["dms"]), reverse=True)
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
        "| Reel | Idea | Hook | Published | DMs | Signups | Free edits | Sales | £ |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for reel_id, r in sorted(rows.items()):
        lines.append(f"| {reel_id} | {r.get('idea', '')} | {r.get('hook', '')} | {'yes' if r['published'] else 'no'} | {r['dms']} "
                     f"| {r['signups']} | {r['free_edits']} | {r['sales']} | {r['gbp']:.2f} |")
    text = "\n".join(lines) + "\n"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.md").write_text(text, encoding="utf-8")
    return text


def build(signups: list[dict] | None = None) -> str:
    """Fetch live sales, join everything, save and return the report."""
    from agent.analytics import stripe_sales
    sales = stripe_sales.sales()
    summary = stripe_sales.summary(sales)
    return write_report(summary, by_reel(sales, signups or []))


if __name__ == "__main__":
    print(build())
