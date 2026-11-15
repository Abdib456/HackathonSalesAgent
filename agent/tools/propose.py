# writes a reel plan + spend amount for approval
#
# Turns a script from write_script into a human-readable plan in
# approvals/pending/<reel-id>.md: what to film, what to say, which hooks scored best.
#
# POSTING=manual (default): the team films, edits and posts by hand, then moves
# the plan to approvals/approved/ ("posted", one touch). POSTING=api: the team
# drops footage, the agent edits, and moving the plan to approved/ is the
# go-ahead to publish (one touch). Either way, moving it to approvals/rejected/
# (one touch, optional "Reason: ..." line) means never, and new plans avoid it.
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


def _manual_steps(reel_id: str) -> str:
    landing = config.LANDING_PAGE_URL
    if landing:
        from agent.tools.email import with_param  # stdlib-only helper, no cycle
        bio = f"`{with_param(landing, 'ref', reel_id)}` (the `ref` lets the report credit sales to this reel)"
    else:
        bio = "your landing page (set `LANDING_PAGE_URL` in `.env` to get a tracked link here)"
    return f"""## Next steps (posting by hand)
1. **Film and edit** in Edits or CapCut, using the shot list and any hook above.
   Put an "AI-assisted" label on screen. Log it as a touch:
   `python -m agent.logger touch {reel_id} "filmed and edited in CapCut"` (and `/touch` in Discord).
2. **Post** on Instagram with the caption below. Keep its AI note; turn on Instagram's
   AI label if it asks. Set the bio link to {bio}.
3. **Move this file to `approvals/approved/`.** That tells the agent it's posted, frees a slot for
   the next plan, and logs the posting as a touch (mirror it with `/touch`).

Not worth filming? Move it to `approvals/rejected/` instead, optionally with a line
`Reason: ...` at the top. New plans will steer away from it.
"""


def _api_steps(reel_id: str) -> str:
    return f"""## Next steps (agent edits and publishes)
1. Drop the files into `footage/{reel_id}/`, named by scene number (`scene-01.mp4`, `scene-02.jpg`,
   plus `voiceover.m4a`). The agent edits the reel on its next run and saves it as
   `creatives/{reel_id}.mp4`, plus a version for each other hook scoring {MIN_VERSION_SCORE}+
   ({reel_id}b, {reel_id}c: same footage, different opening text).
2. Watch them. Delete any version you don't want from `creatives/`. If they're good,
   move this file to `approvals/approved/`. That is your go-ahead to publish (one a day)
   and is logged as a touch.
"""


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
{f"**Comment keyword:** {script['keyword']}" if script.get('keyword') else "**Call to action:** link in bio"}

## Hooks considered (Claude's scores; the top one is the suggestion)
| Score | Hook | Style | Why |
|-------|------|-------|-----|
{hooks}

## Shot list
A guide: adapt it freely. Photos are fine for static shots.

| # | Time | Shot | On-screen text | Voiceover |
|---|------|------|----------------|-----------|
{rows}

## Full voiceover ({"AI voiceover: `voiceovers/" + reel_id + ".mp3` (made on the agent's next run), or record it yourself" if config.ai_voice() else "record in one take"})
{voiceover}

## Caption
{script['caption']}

{_manual_steps(reel_id) if config.MANUAL else _api_steps(reel_id)}
<!-- machine-readable plan, don't edit below -->
```json
{json.dumps(plan, indent=2, ensure_ascii=False)}
```
"""


def propose(script: dict, run: Path, paid_spend_gbp: float = 0.0) -> Path:
    """Write the plan to approvals/pending/ and create its footage folder."""
    reel_id = _next_reel_id()
    PENDING.mkdir(parents=True, exist_ok=True)
    if not config.MANUAL:  # footage folders are only for the agent's own editing
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
    action = ("posted reel by hand (moved plan to approvals/approved/)" if config.MANUAL
              else "approved finished reel (moved plan to approvals/approved/)")
    return [plan for _, plan in _plans_in(APPROVED, action)]


def rejected_ideas() -> list[dict]:
    """Plans or reels the human rejected, with their optional "Reason: ..." line. Logs each once as a touch."""
    ideas = []
    for path, plan in _plans_in(REJECTED, "rejected plan or reel (moved plan to approvals/rejected/)"):
        reason = _REASON.search(path.read_text(encoding="utf-8").split("<!-- machine-readable")[0])
        ideas.append({"reel_id": plan["reel_id"], "idea": plan["script"]["idea"], "hook": plan["script"]["hook"],
                      "reason": reason.group(1).strip() if reason else ""})
    return ideas
