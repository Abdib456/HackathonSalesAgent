# payments + utm metadata, the source of truth
#
# Reads (never writes) Stripe with the read-only key, the same account
# connected to Shipyard. Counts what the judges count:
#   paid LIVE-mode Checkout Sessions (Payment Links) before the freeze,
#   minus refunds and chargebacks.
# Attribution: payment link URLs carry ?client_reference_id=reel-NNN, which
# Stripe stores on the session, so we can see which reel made the money.

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from agent import config

API = "https://api.stripe.com/v1"


def _list(path: str, **params) -> list[dict]:
    """GET a Stripe list endpoint, following pagination."""
    key = config.require("STRIPE_READ_KEY")
    if key.startswith(("sk_test", "rk_test")):
        raise RuntimeError("STRIPE_READ_KEY is a TEST key. Only live-mode sales count.")
    items, params = [], {"limit": 100, **params}
    while True:
        url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = json.loads(resp.read())
        items += page["data"]
        if not page.get("has_more"):
            return items
        params["starting_after"] = page["data"][-1]["id"]


def _when(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def sales() -> list[dict]:
    """Every paid live-mode checkout. Emails stay in memory only, never logged."""
    out = []
    for s in _list("checkout/sessions", status="complete"):
        if s.get("payment_status") != "paid" or not s.get("livemode"):
            continue
        out.append({
            "id": s["id"],
            "created": _when(s["created"]).isoformat(),
            "before_freeze": _when(s["created"]) < config.FREEZE_UTC,
            "gbp": s["amount_total"] / 100,
            "currency": s["currency"],
            "reel": s.get("client_reference_id"),
            "payment_link": s.get("payment_link"),
            "email": (s.get("customer_details") or {}).get("email"),
        })
    return out


def refunds_gbp() -> float:
    return sum(r["amount"] for r in _list("refunds") if r["status"] in ("succeeded", "pending")) / 100


def chargebacks_gbp() -> float:
    """Disputes count against us unless we've won them."""
    return sum(d["amount"] for d in _list("disputes") if d["status"] != "won") / 100


def summary() -> dict:
    s = sales()
    counted = [x for x in s if x["before_freeze"]]
    gross = sum(x["gbp"] for x in counted)
    refunds, chargebacks = refunds_gbp(), chargebacks_gbp()
    return {
        "sales_count": len(counted),
        "gross_gbp": round(gross, 2),
        "refunds_gbp": round(refunds, 2),
        "chargebacks_gbp": round(chargebacks, 2),
        "net_gbp": round(gross - refunds - chargebacks, 2),
        "after_freeze_not_counted": len(s) - len(counted),
        "non_gbp_sales": sum(1 for x in s if x["currency"] != "gbp"),
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
