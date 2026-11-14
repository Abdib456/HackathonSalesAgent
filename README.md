# HackathonSalesAgent

An AI sales agent for our photography + fashion try-on app, built for the
Shipyard "Make Me Money" hackathon. It brings strangers in from Instagram and
moves them toward a paid credit pack, with as few human touches as possible.

## What it does

1. **Writes reel scripts** with Claude: hook, scenes, on-screen text, voiceover, caption, comment keyword.
2. **Turns each script into a shot list** in `approvals/pending/` for the team to film.
3. **Edits the reel** (ffmpeg, 9:16, captions, "AI-assisted" tag) once the footage is in `footage/reel-NNN/`.
4. **Publishes approved reels** to Instagram *(instagram.py, in progress)*.
5. **DMs the landing page link** to people who comment the keyword *(instagram.py, in progress)*.
6. **Emails the waitlist** when the app launches, and sends the payment link after a free try-on edit.
7. **Reports daily**: profit (net Stripe sales − spend), touches, and which reel made money.

Every £ spent is checked against a £100 cap and logged. Every human step is logged as a touch.

## How a reel goes from idea to live

```
Agent  writes plan           → approvals/pending/reel-001.md      (automatic)
Human  films the shot list   → footage/reel-001/scene-01.mp4 ...  (touch)
Agent  edits the reel        → creatives/reel-001.mp4             (automatic, next cycle)
Human  watches it, moves the plan to approvals/approved/           (touch)
       or rejects it, moves the plan to approvals/rejected/         (touch, optional 'Reason: ...' line)
Agent  publishes, then DMs everyone who comments the keyword      (automatic)
```

## The cycle

`python -m agent.main` runs **one cycle** and exits. A cycle checks where everything
is up to and does whatever is ready: a research brief (once a day), new plans (max 2/day), edits, publishing,
DMs, emails, report. Anything waiting on a human or not set up yet is skipped
and logged, never fatal.

`python -m agent.main --loop` repeats the cycle **every 15 minutes until you
press Ctrl+C**. Stopping is safe: all state is in files, so it carries on where
it left off when restarted.

Cost: most cycles cost £0. Only new scripts call Claude (~4p each, max 2/day),
plus one research summary a day (~5p; the 8 Tavily searches use partner credits).

## Where it runs (decision)

The agent keeps its state in files (footage, approvals, logs, spend), so it must
run **on the same machine where we drop footage and move approvals**.

- **Agent: runs on a laptop** with `caffeinate -i python -m agent.main --loop`
  (macOS; keeps it awake). Free, and all logs stay in one place to commit.
- **Replit Pro: used only to serve `creatives/` at a public URL**, because
  Instagram's API fetches videos from a link rather than taking an upload.
- **Not used: Replit Scheduled Deployments / Reserved VMs for the agent.** They
  run a separate copy of the code and (to be confirmed in Replit's docs) don't
  keep file changes, so footage, approvals and logs wouldn't reach them. Any
  paid hosting would also count against the £100 budget.
- Revisit if Replit confirms persistent files on a Reserved VM covered by Pro credits.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # then fill in the keys (never commit .env)
python -m agent.main     # one cycle; check logs/runs/ to see what it did
```

| Key | What for | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Writing scripts | platform.claude.com → API Keys (prepaid credits) |
| `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` | Publishing, comments, DMs | Meta developer app → Instagram → API setup with Instagram login |
| `TAVILY_API_KEY` | Daily research brief (8 searches/day) | Tavily dashboard (partner credits; keep pay-as-you-go off) |
| `STRIPE_READ_KEY` | Counting sales | Stripe → Developers → restricted key, Read on Checkout Sessions, Refunds, Disputes |
| `STRIPE_PAYMENT_LINK` | Payment nudge emails | Stripe live-mode payment link |
| `LANDING_PAGE_URL` | DMs and launch email | Teammate's landing page |
| `RESEND_API_KEY`, `EMAIL_FROM` | Sending email | resend.com (free tier), domain verified |
| `APP_LIVE` | Set to `true` to send the launch email | — |
| `FONT_PATH` | Only if no font is found for reel text | Any `.ttf` file |

## Folders

| Folder | What's in it | In git? |
|---|---|---|
| `agent/` | The code: `main.py`, `tools/`, `analytics/`, `prompts/` | yes |
| `approvals/pending/`, `approved/`, `rejected/` | Reel plans; moving one to `approved/` = go-ahead to publish, to `rejected/` = never publish, and new plans avoid it | yes |
| `footage/` | Raw clips, photos, voiceovers per reel | no (too large) |
| `creatives/` | Finished reels | videos no, index yes |
| `data/research/` | Daily research brief with source links (AI-generated) | yes |
| `logs/runs/` | Full transcript of every cycle | yes |
| `logs/spend.jsonl`, `logs/touches.jsonl` | Every £ spent, every human step | yes |
| `logs/reports/` | Daily profit + per-reel funnel (counts only) | yes |
| `logs/outbound/` | Copy of every DM and email sent | no (customer data, kept locally for audit) |

## Hackathon rules

*Added with the context commit.*
