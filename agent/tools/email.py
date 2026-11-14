# waitlist emails: launch announcement, and the Stripe payment link after a free try-on edit
#
# Sent through Resend's free tier (3,000 emails/month, £0). Every email:
#   - is only sent once per person per kind (checked against logs/outbound/)
#   - is skipped if the person unsubscribed (data/unsubscribed.txt)
#   - has an unsubscribe line (UK PECR rules for marketing email)
#   - is copied to logs/outbound/ (audit rule)
#   - carries the signup's reel ref on its links, so sales can be traced to a reel:
#     landing ?ref=reel-NNN, Stripe payment link ?client_reference_id=reel-NNN
#     (Stripe stores that on the Checkout Session; stripe_sales reads it back)

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from agent import config, logger

RESEND_URL = "https://api.resend.com/emails"
UNSUBSCRIBED = config.ROOT / "data" / "unsubscribed.txt"
# Stripe only accepts letters, digits, - and _ in client_reference_id (max 200)
_VALID_REF = re.compile(r"^[A-Za-z0-9_-]{1,200}$")

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


def with_param(url: str, key: str, value: str) -> str:
    """Add ?key=value to a URL (keeping any query it already has). Skips invalid refs."""
    if not value or not _VALID_REF.match(value):
        return url
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query) + [(key, value)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def send(address: str, kind: str, run: Path, ref: str = "") -> bool:
    """Send one templated email. `ref` is the reel the person signed up from.

    Returns True if sent, False if skipped."""
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
        links["landing"] = with_param(config.require("LANDING_PAGE_URL"), "ref", ref)
    if "{payment_link}" in t["body"]:
        links["payment_link"] = with_param(config.require("STRIPE_PAYMENT_LINK"), "client_reference_id", ref)
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

    logger.save_outbound("email", address, body, kind=kind, subject=t["subject"], provider_id=provider_id, ref=ref)
    logger.log_event(run, "email_sent", kind=kind, provider_id=provider_id, ref=ref)
    return True
