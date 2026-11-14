# saves each run's full transcript to logs/runs/
#
# Every audit record goes through here: run transcripts, human touches,
# and copies of everything sent to customers. Files are append-only and
# never deleted. Secrets are scrubbed before anything is written.

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from agent import config

_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)


def now() -> str:
    """UTC timestamp, ISO format, e.g. 2026-11-13T14:02:11+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _scrub(text: str) -> str:
    """Replace any secret value from the environment with [REDACTED]."""
    for name, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_NAME.search(name):
            text = text.replace(value, "[REDACTED]")
    return text


def append_jsonl(path: Path, record: dict) -> None:
    """Append one record as a single JSON line, adding a timestamp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"timestamp": now(), **record}, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(_scrub(line) + "\n")


# --- Run transcripts -------------------------------------------------------

def start_run(name: str = "daily") -> Path:
    """Create a new transcript file for this run and return its path."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = config.RUNS_DIR / f"{stamp}_{name}.jsonl"
    append_jsonl(path, {"event": "run_started", "name": name})
    return path


def log_event(run: Path, event: str, **data) -> None:
    """Record one step of a run: a prompt, a model reply, a tool call, an error."""
    append_jsonl(run, {"event": event, **data})


# --- Human touches ---------------------------------------------------------

def log_touch(who: str, action: str, note: str = "") -> None:
    """Record a human intervention, to match against /touch in Discord."""
    append_jsonl(config.TOUCHES_LOG, {"who": who, "action": action, "note": note})


# --- Outbound messages -----------------------------------------------------

def save_outbound(channel: str, to: str, content: str, **meta) -> Path:
    """Save a copy of a DM or email sent to a customer. Call this for every send."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")
    path = config.OUTBOUND_DIR / f"{stamp}_{channel}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": now(), "channel": channel, "to": to, "content": content, **meta}
    path.write_text(_scrub(json.dumps(record, ensure_ascii=False, indent=2, default=str)), encoding="utf-8")
    return path


if __name__ == "__main__":
    # Log a hand touch from the terminal, e.g.
    #   python -m agent.logger touch reel-001 "filmed and edited in CapCut"
    import sys

    if len(sys.argv) != 4 or sys.argv[1] != "touch":
        sys.exit('usage: python -m agent.logger touch <reel-id or -> "what you did"')
    log_touch("human", sys.argv[3], "" if sys.argv[2] == "-" else sys.argv[2])
    print(f"Logged touch: {sys.argv[3]} ({sys.argv[2]}). Mirror it with /touch in Discord.")
