# edits the ~25-30s Instagram reel from the script + our own footage/images, adds AI label
#
# No AI here: ffmpeg follows the plan from write_script exactly.
#   footage/reel-NNN/scene-01.mp4 (or .mov/.jpg/.png), scene-02..., voiceover.m4a (optional)
#   -> creatives/reel-NNN.mp4  (1080x1920, 30fps, on-screen text, "AI-assisted" tag)
# Free: ffmpeg comes from the imageio-ffmpeg pip package, so it also works on Replit.

import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

import imageio_ffmpeg

from agent import config, logger

FOOTAGE = config.ROOT / "footage"
CREATIVES = config.ROOT / "creatives"
W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac"}
AI_TAG = "AI-assisted"

# First font that exists wins. Set FONT_PATH in .env to override (e.g. on Replit).
FONT_CANDIDATES = [
    os.getenv("FONT_PATH", ""),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
]


def _font() -> str:
    for f in FONT_CANDIDATES:
        if f and Path(f).exists():
            return f
    raise RuntimeError("No font found for on-screen text. Set FONT_PATH in .env to a .ttf file.")


def _duration(seconds: str) -> float:
    """'0-2' -> 2.0, '2-20' -> 18.0. Falls back to 3s if the script is vague."""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", seconds)]
    return max(nums[1] - nums[0], 0.5) if len(nums) >= 2 else 3.0


def _find(folder: Path, stem: str, exts: set) -> Path | None:
    for p in sorted(folder.glob(f"{stem}.*")):
        if p.suffix.lower() in exts:
            return p
    return None


def missing_footage(plan: dict) -> list[str]:
    """Scene files still needed for this reel. Empty list = ready to edit."""
    folder = FOOTAGE / plan["reel_id"]
    scenes = plan["script"]["scenes"]
    return [f"scene-{i:02d}" for i in range(1, len(scenes) + 1)
            if not _find(folder, f"scene-{i:02d}", VIDEO_EXT | IMAGE_EXT)]


def _esc(path: Path | str) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ffmpeg(args: list) -> None:
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *map(str, args)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")


def _scene(src: Path, text: str, dur: float, out: Path, tmp: Path, font: str) -> None:
    """One scene: fill the 9:16 frame, exact length, caption text near the top."""
    textfile = tmp / f"{out.stem}.txt"
    textfile.write_text(textwrap.fill(text, 22), encoding="utf-8")
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration={dur},"
        # expansion=none: show text literally, so "50% off" doesn't crash ffmpeg
        f"drawtext=fontfile='{_esc(font)}':expansion=none:textfile='{_esc(textfile)}':fontsize=68:fontcolor=white:"
        f"borderw=5:bordercolor=black:line_spacing=14:x=(w-text_w)/2:y=h*0.16"
    )
    inp = ["-loop", "1", "-i", src] if src.suffix.lower() in IMAGE_EXT else ["-i", src]
    _ffmpeg([*inp, "-t", dur, "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", "-r", FPS, out])


def make_reel(plan: dict, run: Path) -> Path | None:
    """Edit the reel and its hook versions (same footage, different scene-1 text).

    Returns the main reel's path, or None if footage is still missing.
    """
    from agent.tools.propose import versions  # propose imports nothing from here; avoids a cycle

    reel_id = plan["reel_id"]
    missing = missing_footage(plan)
    if missing:
        logger.log_event(run, "reel_waiting_for_footage", reel_id=reel_id, missing=missing)
        return None

    folder = FOOTAGE / reel_id
    font = _font()
    scenes = plan["script"]["scenes"]
    total = sum(_duration(s["seconds"]) for s in scenes)
    CREATIVES.mkdir(parents=True, exist_ok=True)
    voiceover = _find(folder, "voiceover", AUDIO_EXT)
    audio = ["-i", voiceover] if voiceover else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    tag = (f"drawtext=fontfile='{_esc(font)}':text='{AI_TAG}':fontsize=34:fontcolor=white@0.85:"
           f"box=1:boxcolor=black@0.4:boxborderw=10:x=w-text_w-40:y=h-text_h-160")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # Scenes 2+ are the same in every version, so render them once
        rest = []
        for i, s in enumerate(scenes[1:], start=2):
            part = tmp / f"part-{i:02d}.mp4"
            _scene(_find(folder, f"scene-{i:02d}", VIDEO_EXT | IMAGE_EXT), s["on_screen_text"],
                   _duration(s["seconds"]), part, tmp, font)
            rest.append(part)

        for v in versions(plan):
            out = CREATIVES / f"{v['reel_id']}.mp4"
            first = tmp / f"first-{v['reel_id']}.mp4"
            _scene(_find(folder, "scene-01", VIDEO_EXT | IMAGE_EXT), v["script"]["scenes"][0]["on_screen_text"],
                   _duration(scenes[0]["seconds"]), first, tmp, font)
            concat_list = tmp / f"parts-{v['reel_id']}.txt"
            concat_list.write_text("".join(f"file '{p}'\n" for p in [first, *rest]), encoding="utf-8")
            _ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list, *audio,
                     "-map", "0:v", "-map", "1:a", "-vf", tag, "-af", "apad", "-t", total,
                     "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
            logger.log_event(run, "reel_made", reel_id=v["reel_id"], version_of=reel_id, hook=v["script"]["hook"],
                             path=str(out.relative_to(config.ROOT)), seconds=total, voiceover=bool(voiceover))

    # Filming/recording is a human step the rules count as a touch (once, however many versions)
    logger.log_touch("human", "filmed footage" + (" + recorded voiceover" if voiceover else ""), reel_id)
    return CREATIVES / f"{reel_id}.mp4"
