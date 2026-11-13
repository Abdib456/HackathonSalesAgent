# waitlist emails: launch announcement, and the Stripe payment link after a free try-on edit
#
# Sent through Resend's free tier (3,000 emails/month, £0). Every email:
#   - is only sent once per person per kind (checked against logs/outbound/)
#   - is skipped if the person unsubscribed (data/unsubscribed.txt)
#   - has an unsubscribe line (UK PECR rules for marketing email)
#   - is copied to logs/outbound/ (audit rule)

import json
import urllib.error
import urllib.request
from pathlib import Path

from agent import config, logger

RESEND_URL = "https://api.resend.com/emails"
UNSUBSCRIBED = config.ROOT / "data" / "unsubscribed.txt"

TEMPLATES = {
    "launch": {
        "subject": "It's live: try outfits on before you buy",
        "body": "You joined the waitlist, so you're first to know: the app is live.\n\n"
                "Your first try-on edit is free: {landing}\n",
    },
    "payment_nudge": {
        "subject": "Liked your free try-on? Get more edits",
        "body": "Thanks for trying your free edit.\n\n"
                "Want more looks? Credit packs start at £3.49 for 5 edits: {payment_link}\n",
    },
}

FOOTER = "\n—\nYou're getting this because you signed up with this email. " \
         "Reply STOP to unsubscribe and we won't email you again."


def _unsubscribed() -> set[str]:
    if not UNSUBSCRIBED.exists():
        return set()
    return {l.strip().lower() for l in UNSUBSCRIBED.read_text(encoding="utf-8").splitlines() if l.strip()}


def unsubscribe(address: str) -> None:
    """Add someone to the do-not-email list (e.g. they replied STOP)."""
    UNSUBSCRIBED.parent.mkdir(parents=True, exist_ok=True)
    with open(UNSUBSCRIBED, "a", encoding="utf-8") as f:
        f.write(address.strip().lower() + "\n")


def already_sent(address: str, kind: str) -> bool:
    for p in config.OUTBOUND_DIR.glob("*_email.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("to") == address.lower() and rec.get("kind") == kind:
            return True
    return False


def send(address: str, kind: str, run: Path) -> bool:
    """Send one templated email. Returns True if sent, False if skipped."""
    address = address.strip().lower()
    if address in _unsubscribed():
        logger.log_event(run, "email_skipped", kind=kind, reason="unsubscribed")
        return False
    if already_sent(address, kind):
        logger.log_event(run, "email_skipped", kind=kind, reason="already sent")
        return False

    t = TEMPLATES[kind]
    links = {}
    if "{landing}" in t["body"]:
        links["landing"] = config.require("LANDING_PAGE_URL")
    if "{payment_link}" in t["body"]:
        links["payment_link"] = config.require("STRIPE_PAYMENT_LINK")
    body = t["body"].format(**links) + FOOTER

    payload = {"from": config.require("EMAIL_FROM"), "to": [address], "subject": t["subject"], "text": body}
    req = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.require('RESEND_API_KEY')}",
                 "Content-Type": "application/json", "User-Agent": "sales-agent/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            provider_id = json.loads(resp.read()).get("id")
    except urllib.error.HTTPError as e:
        logger.log_event(run, "email_failed", kind=kind, status=e.code, error=e.read().decode()[:300])
        return False

    logger.save_outbound("email", address, body, kind=kind, subject=t["subject"], provider_id=provider_id)
    logger.log_event(run, "email_sent", kind=kind, provider_id=provider_id)
    return True
