# writes a reel plan + spend amount for approval
#
# Turns a script from write_script into a human-readable plan in
# approvals/pending/<reel-id>.md: what to film, what to say, where to drop
# the files. The agent edits once footage arrives; the human approves the
# finished reel by moving the file to approvals/approved/ (one touch), or
# rejects the plan or reel by moving it to approvals/rejected/ (one touch,
# optionally with a "Reason: ..." line). Rejected ideas are steered away from.
# The machine-readable script is embedded at the bottom so the plan is one file.
#
# Hook versions: one plan + one filming session -> up to 3 reels from the same
# footage, each opening with a different top-scoring hook (reel-001, reel-001b,
# reel-001c). One approval covers them all; they publish a day apart and are
# tracked separately, so the reports show which hook actually got DMs.

import copy
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
HOOK_VERSIONS = 3        # reels per plan, including the main one
MIN_VERSION_SCORE = 7    # don't spend a post on a weak hook

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
   on its next run and saves it as `creatives/{reel_id}.mp4`, plus a version for each
   other hook scoring {MIN_VERSION_SCORE}+ ({reel_id}b, {reel_id}c: same footage, different opening text).
2. Watch them. Delete any version you don't want from `creatives/`. If they're good,
   move this file to `approvals/approved/`. That is your go-ahead to publish (one a day)
   and is logged as a touch.

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


def base_id(reel_id: str) -> str:
    """'reel-001b' -> 'reel-001'."""
    return re.match(r"reel-\d+", reel_id).group(0)


def versions(plan: dict) -> list[dict]:
    """The plan as up to HOOK_VERSIONS reels: the main one, then one per other strong hook."""
    out, seen = [plan], {plan["script"]["hook"].strip().lower()}
    for h in plan["script"].get("hooks", [])[1:]:
        text = h["text"].strip()
        if len(out) >= HOOK_VERSIONS or h["score"] < MIN_VERSION_SCORE or text.lower() in seen:
            continue
        seen.add(text.lower())
        v = copy.deepcopy(plan)
        v["reel_id"] = f"{plan['reel_id']}{'abcdefgh'[len(out)]}"
        v["version_of"] = plan["reel_id"]
        v["script"]["hook"] = text
        v["script"]["scenes"][0]["on_screen_text"] = text
        out.append(v)
    return out


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
