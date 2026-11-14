# writes a reel plan + spend amount for approval
#
# Turns a script from write_script into a human-readable plan in
# approvals/pending/<reel-id>.md: what to film, what to say, where to drop
# the files. The agent edits once footage arrives; the human approves the
# finished reel by moving the file to approvals/approved/ (one touch), or
# rejects the plan or reel by moving it to approvals/rejected/ (one touch,
# optionally with a "Reason: ..." line). Rejected ideas are steered away from.
# The machine-readable script is embedded at the bottom so the plan is one file.

import json
import re
from pathlib import Path

from agent import config, logger

APPROVALS = config.ROOT / "approvals"
PENDING = APPROVALS / "pending"
APPROVED = APPROVALS / "approved"
REJECTED = APPROVALS / "rejected"
FOOTAGE = config.ROOT / "footage"

_JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
_REASON = re.compile(r"^\s*reason:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _next_reel_id() -> str:
    used = [int(m.group(1)) for d in (PENDING, APPROVED, REJECTED, FOOTAGE) if d.exists()
            for p in d.iterdir() if (m := re.match(r"reel-(\d+)", p.name))]
    return f"reel-{max(used, default=0) + 1:03d}"


def _render(reel_id: str, script: dict, paid_spend_gbp: float) -> str:
    rows = "\n".join(
        f"| {i:02d} | {s['seconds']}s | {s['shot']} | {s['on_screen_text']} | {s['voiceover']} |"
        for i, s in enumerate(script["scenes"], start=1)
    )
    voiceover = " ".join(s["voiceover"] for s in script["scenes"] if s["voiceover"])
    cell = lambda t: str(t).replace("|", "\\|")  # a | in the text would break the table
    hooks = "\n".join(f"| {h['score']}/10 | {cell(h['text'])} | {cell(h['style'])} | {cell(h['reason'])} |"
                      for h in script.get("hooks", []))
    plan = {"reel_id": reel_id, "paid_spend_gbp": paid_spend_gbp, "script": script}
    return f"""# {reel_id}: {script['idea']}

**Hook (first 2s):** {script['hook']}
**Comment keyword:** {script['keyword']}
**Paid spend requested:** £{paid_spend_gbp:.2f}

## Hooks considered (Claude's scores; the top one is used)
| Score | Hook | Style | Why |
|-------|------|-------|-----|
{hooks}

## Shot list
Film each scene and drop the file into `footage/{reel_id}/` named by scene number,
e.g. `scene-01.mp4`, `scene-02.jpg`. Photos are fine for static shots.

| # | Time | Shot | On-screen text | Voiceover |
|---|------|------|----------------|-----------|
{rows}

## Full voiceover (record in one take, save as `footage/{reel_id}/voiceover.m4a`)
{voiceover}

## Caption
{script['caption']}

## Next steps
1. Drop the files into `footage/{reel_id}/`. The agent edits the reel automatically
   on its next run and saves it as `creatives/{reel_id}.mp4`.
2. Watch the finished reel. If it's good, move this file to `approvals/approved/`.
   That is your go-ahead to publish and is logged as a touch.

<!-- machine-readable plan, don't edit below -->
```json
{json.dumps(plan, indent=2, ensure_ascii=False)}
```
"""


def propose(script: dict, run: Path, paid_spend_gbp: float = 0.0) -> Path:
    """Write the plan to approvals/pending/ and create its footage folder."""
    reel_id = _next_reel_id()
    PENDING.mkdir(parents=True, exist_ok=True)
    (FOOTAGE / reel_id).mkdir(parents=True, exist_ok=True)
    path = PENDING / f"{reel_id}.md"
    path.write_text(_render(reel_id, script, paid_spend_gbp), encoding="utf-8")
    logger.log_event(run, "plan_proposed", reel_id=reel_id, path=str(path.relative_to(config.ROOT)),
                     paid_spend_gbp=paid_spend_gbp)
    return path


def read_plan(path: Path) -> dict:
    """Get the embedded plan back out of a .md file."""
    match = _JSON_BLOCK.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"No plan data found in {path.name}")
    return json.loads(match.group(1))


def _plans_in(folder: Path, action: str) -> list[tuple[Path, dict]]:
    """Plans the human moved into `folder`. Logs each move once as a touch."""
    if not folder.exists():
        return []
    logged = set()  # (action, reel_id) pairs, so other touches on the same reel don't hide this one
    if config.TOUCHES_LOG.exists():
        for line in config.TOUCHES_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                t = json.loads(line)
                logged.add((t.get("action"), t.get("note")))

    plans = []
    for path in sorted(folder.glob("reel-*.md")):
        plan = read_plan(path)
        if (action, plan["reel_id"]) not in logged:
            logger.log_touch("human", action, plan["reel_id"])
        plans.append((path, plan))
    return plans


def approved_plans() -> list[dict]:
    """Finished reels the human has approved to publish. Logs each approval once as a touch."""
    return [plan for _, plan in _plans_in(APPROVED, "approved finished reel (moved plan to approvals/approved/)")]


def rejected_ideas() -> list[dict]:
    """Plans or reels the human rejected, with their optional "Reason: ..." line. Logs each once as a touch."""
    ideas = []
    for path, plan in _plans_in(REJECTED, "rejected plan or reel (moved plan to approvals/rejected/)"):
        reason = _REASON.search(path.read_text(encoding="utf-8").split("<!-- machine-readable")[0])
        ideas.append({"reel_id": plan["reel_id"], "idea": plan["script"]["idea"], "hook": plan["script"]["hook"],
                      "reason": reason.group(1).strip() if reason else ""})
    return ideas
