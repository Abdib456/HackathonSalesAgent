# writes a reel plan for the team to film
#
# Turns a script from write_script into a human-readable plan in
# approvals/pending/<reel-id>.md: what to film, what to say, which hooks scored best,
# the caption, and the bio link.
#
# The team films, edits and posts by hand, then moves the plan to
# approvals/approved/ (= posted, one touch). Moving it to approvals/rejected/
# (one touch, optional "Reason: ..." line) means never, and new plans avoid it.
# The machine-readable script is embedded at the bottom so the plan is one file.

import json
import re
import urllib.parse
from pathlib import Path

from agent import config, logger

APPROVALS = config.ROOT / "approvals"
PENDING = APPROVALS / "pending"
APPROVED = APPROVALS / "approved"
REJECTED = APPROVALS / "rejected"

_JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
_REASON = re.compile(r"^\s*reason:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# Stripe only accepts letters, digits, - and _ in client_reference_id (max 200)
_VALID_REF = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


def with_param(url: str, key: str, value: str) -> str:
    """Add ?key=value to a URL (keeping any query it already has). Skips invalid refs."""
    if not value or not _VALID_REF.match(value):
        return url
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query) + [(key, value)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _next_reel_id() -> str:
    used = [int(m.group(1)) for d in (PENDING, APPROVED, REJECTED) if d.exists()
            for p in d.iterdir() if (m := re.match(r"reel-(\d+)", p.name))]
    return f"reel-{max(used, default=0) + 1:03d}"


def _next_steps(reel_id: str) -> str:
    landing = config.LANDING_PAGE_URL
    if landing:
        bio = f"`{with_param(landing, 'ref', reel_id)}` (the `ref` lets the report credit sales to this reel)"
    else:
        bio = "your landing page (set `LANDING_PAGE_URL` in `.env` to get a tracked link here)"
    return f"""## Next steps
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


def _render(reel_id: str, script: dict) -> str:
    rows = "\n".join(
        f"| {i:02d} | {s['seconds']}s | {s['shot']} | {s['on_screen_text']} | {s['voiceover']} |"
        for i, s in enumerate(script["scenes"], start=1)
    )
    voiceover = " ".join(s["voiceover"] for s in script["scenes"] if s["voiceover"])
    cell = lambda t: str(t).replace("|", "\\|")  # a | in the text would break the table
    hooks = "\n".join(f"| {h['score']}/10 | {cell(h['text'])} | {cell(h['style'])} | {cell(h['reason'])} |"
                      for h in script.get("hooks", []))
    plan = {"reel_id": reel_id, "script": script}
    voice_note = (f"AI voiceover: `voiceovers/{reel_id}.mp3` (made on the agent's next run), or record it yourself"
                  if config.ai_voice() else "record in one take")
    return f"""# {reel_id}: {script['idea']}

**Hook (first 2s):** {script['hook']}
**Call to action:** link in bio

## Hooks considered (Claude's scores; the top one is the suggestion)
| Score | Hook | Style | Why |
|-------|------|-------|-----|
{hooks}

## Shot list
A guide: adapt it freely. Photos are fine for static shots.

| # | Time | Shot | On-screen text | Voiceover |
|---|------|------|----------------|-----------|
{rows}

## Full voiceover ({voice_note})
{voiceover}

## Caption
{script['caption']}

{_next_steps(reel_id)}
<!-- machine-readable plan, don't edit below -->
```json
{json.dumps(plan, indent=2, ensure_ascii=False)}
```
"""


def propose(script: dict, run: Path) -> Path:
    """Write the plan to approvals/pending/."""
    reel_id = _next_reel_id()
    PENDING.mkdir(parents=True, exist_ok=True)
    path = PENDING / f"{reel_id}.md"
    path.write_text(_render(reel_id, script), encoding="utf-8")
    logger.log_event(run, "plan_proposed", reel_id=reel_id, path=str(path.relative_to(config.ROOT)))
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
    """Reels the human has posted (plan moved to approved/). Logs each move once as a touch."""
    return [plan for _, plan in _plans_in(APPROVED, "posted reel by hand (moved plan to approvals/approved/)")]


def rejected_ideas() -> list[dict]:
    """Plans the human rejected, with their optional "Reason: ..." line. Logs each once as a touch."""
    ideas = []
    for path, plan in _plans_in(REJECTED, "rejected plan or reel (moved plan to approvals/rejected/)"):
        reason = _REASON.search(path.read_text(encoding="utf-8").split("<!-- machine-readable")[0])
        ideas.append({"reel_id": plan["reel_id"], "idea": plan["script"]["idea"], "hook": plan["script"]["hook"],
                      "reason": reason.group(1).strip() if reason else ""})
    return ideas
