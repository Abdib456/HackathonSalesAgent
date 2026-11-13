# tracks every £ spent, blocks anything over £100
#
# Every paid call (Claude, video tools, email sending, ads) goes through here:
#   1. check(estimate)  before the call: refuses if it would pass the cap
#   2. record(actual)   after the call: logs it to logs/spend.jsonl
# Spend comes off profit, so the log is also the evidence for the judges.

import json

from agent import config, logger


class BudgetExceeded(Exception):
    """Raised when a spend would take the total over the cap."""


def total_spent() -> float:
    """Sum of every GBP amount in logs/spend.jsonl."""
    if not config.SPEND_LOG.exists():
        return 0.0
    total = 0.0
    with open(config.SPEND_LOG, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += float(json.loads(line)["gbp"])
    return round(total, 4)


def remaining() -> float:
    return round(config.BUDGET_CAP_GBP - total_spent(), 4)


def check(estimate_gbp: float, what: str) -> None:
    """Call before any paid action. Raises BudgetExceeded if it won't fit."""
    if estimate_gbp > remaining():
        raise BudgetExceeded(
            f"Blocked '{what}': £{estimate_gbp:.2f} needed, "
            f"only £{remaining():.2f} of £{config.BUDGET_CAP_GBP:.0f} left."
        )


def record(gbp: float, what: str, **details) -> list[str]:
    """Log a spend that happened. Returns any threshold warnings it triggered."""
    before = total_spent()
    logger.append_jsonl(config.SPEND_LOG, {"gbp": round(gbp, 4), "for": what, **details})
    after = before + gbp

    warnings = []
    for line in config.BUDGET_WARNINGS_GBP:
        if before < line <= after:
            msg = f"BUDGET WARNING: spend passed £{line:.0f} (now £{after:.2f} of £{config.BUDGET_CAP_GBP:.0f})"
            print(msg)
            warnings.append(msg)
    return warnings
