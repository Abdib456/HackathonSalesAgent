# loads .env, budget cap, landing page URL
#
# One place for every setting, so no other file reads os.environ or
# hardcodes a key. Secrets come only from .env (gitignored).

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Budget (GBP): hard cap and the points where the agent warns the human
BUDGET_CAP_GBP = 100.0
BUDGET_WARNINGS_GBP = (50.0, 75.0, 90.0)

# Most APIs bill in USD. Slightly pessimistic rate so spend is never under-counted.
USD_TO_GBP = 0.80

# Log locations (kept forever as audit evidence)
LOGS_DIR = ROOT / "logs"
RUNS_DIR = LOGS_DIR / "runs"
OUTBOUND_DIR = LOGS_DIR / "outbound"
SPEND_LOG = LOGS_DIR / "spend.jsonl"
TOUCHES_LOG = LOGS_DIR / "touches.jsonl"

# Non-secret settings
LANDING_PAGE_URL = os.getenv("LANDING_PAGE_URL", "")
STRIPE_PAYMENT_LINK = os.getenv("STRIPE_PAYMENT_LINK", "")  # live-mode payment link


def require(name: str) -> str:
    """Return a secret from .env, or stop with a clear error.

    Checked only when a tool needs it, so the agent can run before every key
    exists. The value itself is never printed.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing. Add it to .env (see .env.example).")
    return value
