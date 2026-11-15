# AI voiceover for each reel plan (ElevenLabs text-to-speech)
#
# Turns the plan's full voiceover script into voiceovers/reel-NNN.mp3, so the
# team can drop it into Edits/CapCut instead of recording one. Skipped until
# ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are in .env.
#
# It's AI-generated audio, so the reel must say so: keep the caption's AI note
# and the on-screen "AI-assisted" label, and turn on Instagram's AI label.
# Only use a voice we have the rights to: an ElevenLabs library voice, or a
# clone of a teammate's own voice with their consent.
#
# Spend: runs on partner credits (assumed £0, confirm in #support and change
# GBP_PER_1K_CHARS if not). Each call still goes through budget.check/record,
# with the character count, so the log shows every use. A 30s script is
# ~400 characters.

import json
import os
import urllib.request
from pathlib import Path

from agent import budget, config, logger

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
DEFAULT_MODEL = "eleven_multilingual_v2"
GBP_PER_1K_CHARS = 0.0  # partner credits
VOICEOVERS = config.ROOT / "voiceovers"


def path_for(reel_id: str) -> Path:
    return VOICEOVERS / f"{reel_id}.mp3"


def script_text(plan: dict) -> str:
    """The plan's voiceover lines, in scene order, as one take."""
    return " ".join(s["voiceover"].strip() for s in plan["script"]["scenes"] if s.get("voiceover", "").strip())


def make_voiceover(plan: dict, run: Path) -> Path | None:
    """Generate voiceovers/<reel_id>.mp3 once. Returns its path, or None if there's no script."""
    reel_id = plan["reel_id"]
    out = path_for(reel_id)
    if out.exists():
        return out
    text = script_text(plan)
    if not text:
        return None

    cost = len(text) / 1000 * GBP_PER_1K_CHARS
    budget.check(cost, "elevenlabs: voiceover")
    voice_id = config.require("ELEVENLABS_VOICE_ID")
    model = os.getenv("ELEVENLABS_MODEL") or DEFAULT_MODEL
    logger.log_event(run, "voiceover_request", reel_id=reel_id, voice_id=voice_id, model=model,
                     characters=len(text), text=text)
    req = urllib.request.Request(
        API.format(voice_id=voice_id),
        data=json.dumps({"text": text, "model_id": model}).encode(),
        headers={"xi-api-key": config.require("ELEVENLABS_API_KEY"),
                 "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        audio = resp.read()
    budget.record(cost, "elevenlabs: voiceover", reel_id=reel_id, characters=len(text), model=model)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    logger.log_event(run, "voiceover_made", reel_id=reel_id, path=str(out.relative_to(config.ROOT)),
                     bytes=len(audio))
    return out


if __name__ == "__main__":
    # Make (or remake, after deleting the .mp3) one plan's voiceover:
    #   python -m agent.tools.voiceover approvals/pending/reel-001.md
    import sys

    from agent.tools.propose import read_plan

    run = logger.start_run("voiceover")
    print(make_voiceover(read_plan(Path(sys.argv[1])), run) or "No voiceover lines in that plan.")
