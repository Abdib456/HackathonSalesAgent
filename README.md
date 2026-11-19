# HackathonSalesAgent

An AI marketing agent for our photography + fashion try-on app, built for the
Shipyard "Make Me Money" hackathon. It does the research, scripting and reporting
behind our Instagram reels; we film, edit and post them by hand. Strangers buy in
our web app through a live Stripe payment link.

## What actually ran (written 19 Nov, after the freeze)

The rest of this README describes how the agent is designed to work. This section
records what it actually did during the hackathon, as shown by the logs in this repo.

- **One full test cycle, 15 Nov at 18:49 UK** (`logs/runs/2026-11-15T18-49-45_cycle.jsonl`):
  - Research: 8 Tavily searches and one Claude summary → `data/research/2026-11-15.md`.
  - One reel plan written by Claude → `approvals/pending/reel-001.md`.
  - Voiceover: the first attempt failed (ElevenLabs `402 Payment Required`). A retry
    at 19:06 recorded no result. A third at 19:13, with a different voice, made
    the MP3 (`logs/runs/2026-11-15T19-13-00_voiceover.jsonl`). The MP3 is not in git.
  - Profit report: **skipped**, because `STRIPE_READ_KEY` was not set. So
    `logs/reports/` holds no report.
- **Total agent spend: £0.13** (two Claude calls; Tavily and ElevenLabs used partner
  credits, logged at £0). See `logs/spend.jsonl`.
- **The 15-minute loop:** [CONFIRM: "was not run" / "ran on ... from ... to ..., logs in ..."].
- **Touches** were logged with `/touch` in Discord, not in `logs/touches.jsonl` (empty).
  The Discord log is the full record.
- **Reels:** `reel-001` was not moved to `approved/`, so the repo records no reel as
  posted. [CONFIRM: whether any reel was posted by hand, and which.]
- **Sales:** [CONFIRM: number and total from Stripe, or "none"]. Stripe proof is in the
  evidence pack, not in this repo.
- These logs were committed on 19 Nov (commit `cc122d3`), after the freeze. They are
  unchanged from the 15 Nov run.

## What the agent does

1. **Researches** what's working in fashion / try-on reels this week (Tavily search + a Claude summary, with sources).
2. **Writes reel plans** with Claude: idea, 5 hooks scored 1-10, shot list, voiceover, caption with an AI note, "link in bio" call to action.
3. **Voices them** (optional, ElevenLabs): an AI voiceover MP3 per plan, ready to drop into the edit.
4. **Learns**: new plans lean towards reels that made money and away from plans we rejected.
5. **Reports**: profit (live Stripe sales − refunds/chargebacks − spend), touches, and sales per reel.

Every £ spent is checked against the £100 cap and logged. Every human step is logged as a touch.

## The flow, start to finish

| # | Step | Who | Touch? |
|---|------|-----|--------|
| 1 | Daily research brief → `data/research/YYYY-MM-DD.md` | Agent | — |
| 2 | Reel plan → `approvals/pending/reel-NNN.md` (keeps 2 ready, max 2 new a day) | Agent | — |
| 2b | AI voiceover → `voiceovers/reel-NNN.mp3` (only with ElevenLabs keys) | Agent | — |
| 3 | Read the plan. Weak? Move it to `approvals/rejected/` (optional `Reason: ...` line) | Human | yes (logged automatically) |
| 4 | Film and edit it in Edits / CapCut (with the AI voiceover, or record one), with an "AI-assisted" label on screen | Human | yes (log it, see below) |
| 5 | Post on Instagram with the plan's caption; set the bio link the plan gives you | Human | yes |
| 6 | Move the plan to `approvals/approved/`: marks it posted and frees a slot for the next plan | Human | logged automatically as the posting touch |
| 7 | A stranger taps the bio link, signs up, uses the free try-on, pays in the app | Customer + app | — |
| 8 | Report → `logs/reports/YYYY-MM-DD.md`, refreshed every cycle | Agent | — |

About 3 touches per posted reel. Log the ones the agent can't see (filming, editing) with:

```bash
python -m agent.logger touch reel-001 "filmed and edited in CapCut"
```

and mirror every touch with `/touch` (and every spend with `/spend`) in Discord.

**Which reel sold?** The plan's bio link is `LANDING_PAGE_URL?ref=reel-NNN`. If the app
passes that `ref` to Stripe as `client_reference_id`, the report credits each sale to
its reel and the agent learns from it. It doesn't yet, so sales count but show as
"unknown", and new plans rotate through the starting angles plus the research.

## The cycle

`python -m agent.main` runs **one cycle** and exits; `--loop` repeats it **every 15
minutes** until Ctrl+C. Stopping is safe: all state is in files.

Each cycle: log plan moves as touches → research (once a day) → new plans (if fewer
than 2 waiting) → AI voiceovers for waiting plans (once each) → report. Anything not set up yet is skipped and logged, never fatal.

Cost: most cycles cost £0. Plans call Claude (~4p each, max 2/day), plus one research
summary a day (~5p). The 8 daily Tavily searches and the voiceovers (~400 characters
each) use partner credits.

## Where it runs

Anywhere with Python 3.10+ and the `.env` keys. On a Mac: `caffeinate -i python -m agent.main --loop`
(keeps it awake). The agent's state is files (plans you move by hand, logs we commit), so
wherever it runs is where you move the plans and commit the logs from.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill in the keys (never commit .env)
python -m agent.main     # one cycle; check logs/runs/ to see what it did
```

| Key | What for | Needed? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Plans and the research summary | **yes** |
| `TAVILY_API_KEY` | Daily research brief | **yes** (partner credits; keep pay-as-you-go off) |
| `STRIPE_READ_KEY` | The profit report. Restricted `rk_live_` key, Core = Read, same Stripe account as Shipyard | **yes** |
| `LANDING_PAGE_URL` | The tracked bio link in each plan | recommended |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | AI voiceovers. Voice ID from ElevenLabs → Voices (a library voice, or a teammate's own cloned voice with their consent) | optional (both = on) |
| `ELEVENLABS_MODEL` | Override the voice model (default `eleven_multilingual_v2`) | optional |

The app's context (product, audience, voice, look, allowed claims) is in
`agent/prompts/system.md` and `brand.md`. Every Claude call reads both, so edit those,
not the code, to change what the plans say.

## Folders

| Folder | What's in it | In git? |
|---|---|---|
| `agent/` | The code: `main.py`, `tools/`, `analytics/`, `prompts/` | yes |
| `approvals/pending/` | Plans waiting to be filmed | yes |
| `approvals/approved/` | Posted reels (moved here by us) | yes |
| `approvals/rejected/` | Plans we said no to; new plans avoid them | yes |
| `data/research/` | Daily research brief with source links (AI-generated) | yes |
| `voiceovers/` | AI voiceover MP3 per plan (the text sent is in `logs/runs/`) | no (audio, regenerable) |
| `logs/runs/` | Full transcript of every cycle | yes |
| `logs/spend.jsonl`, `logs/touches.jsonl` | Every £ spent, every human step | yes |
| `logs/reports/` | Daily profit + per-reel sales (counts only) | yes |

**AI voiceovers must be disclosed.** Keep the caption's AI note and the on-screen
"AI-assisted" label, and turn on Instagram's AI label when posting. To redo one, delete
the MP3 and run `python -m agent.tools.voiceover approvals/pending/reel-NNN.md`.

## How the code fits together

```
agent/
  main.py              the cycle: a list of steps, each in its own try block
  config.py            every setting and .env key in one place
  budget.py            check() before / record() after every paid call; £100 cap
  logger.py            run transcripts, touches, outbound copies; scrubs secrets
  prompts/             system.md + brand.md: the app context every Claude call reads
  tools/
    research.py        Tavily searches + Claude summary, once a day
    write_script.py    Claude: one reel script, 5 scored hooks
    propose.py         script -> approvals/pending/reel-NNN.md; reads plan moves
    voiceover.py       ElevenLabs MP3 per plan (optional)
  analytics/
    stripe_sales.py    live sales, refunds, chargebacks (read-only key)
    reports.py         profit + per-reel sales -> logs/reports/; feeds the learning loop
```

## Scaling later

The agent is a list of steps in `main.py` → `cycle()`. To add something, write a
`step_<name>(run)` function that skips (with `_skip`) when its keys aren't set, put any
paid call between `budget.check()` and `budget.record()`, log what it does with
`logger.log_event`, and add it to the list. Nothing else needs to change.

Ideas, roughly in order of value:

| Add | How |
|---|---|
| **Per-reel sales** | The app passes `?ref` from the landing page to Stripe as `client_reference_id`. No agent change: the report and learning loop pick it up |
| **DMs to keyword commenters** | ManyChat (an official Meta partner) or the Instagram API. Only DM people who commented the keyword; copy every DM to `logs/outbound/` with `logger.save_outbound` |
| **Emails to signups** | A `signups.py` reading the app's sign-ups, plus an email step (Resend). UK PECR: unsubscribe line, honour STOP |
| **Auto-editing and auto-posting** | ffmpeg editing from dropped footage, and posting through the Instagram API (needs Meta app permissions). Multiple hook versions per filming |
| **More channels** | A new tool per channel, same step pattern; the plan format is reusable |
| **Paid boost** | Only once sales prove a reel works; through the budget like any other spend |

Code removed in the cleanup (ffmpeg editing, hook versions, emails, the DM/publish
contracts and a `POSTING=api` switch) is in git history: commit `ade9220`. Restore a file
with `git checkout ade9220 -- agent/tools/make_reel.py` (or `email.py`); `main.py` at that
commit shows how those steps were wired into the cycle.

## Hackathon rules (and how we keep them)

| Rule | How |
|---|---|
| Only sales to strangers count: no friends, family, teammates, participants or existing clients | We don't buy, ask people we know to buy, or seed the waitlist. Any test purchase is refunded, and refunds are subtracted |
| Live Stripe, same account as the read-only key on Shipyard; a sale counts only if charged and delivered before the freeze (18 Nov, 6pm UK) | The report reads live Stripe with a restricted read key (test keys are rejected) |
| Refunds and chargebacks are subtracted | `stripe_sales.py` nets them out before profit |
| £100 budget in total | Every paid call goes through `budget.check()` before and `budget.record()` after, logged to `logs/spend.jsonl`; warnings at £50, £75, £90; mirrored with `/spend` |
| Every human action is a touch; keep them few | Plan moves are logged automatically; other steps with `python -m agent.logger touch`; code and prompt changes count; mirrored with `/touch` |
| Official APIs only: no scraping, bots or fake engagement | Search uses the Tavily API; we post by hand; the agent never likes, follows, comments or DMs |
| No cold DMs | The agent sends no DMs. Any DM tool added later only messages people who commented the keyword |
| Disclose AI and label AI content | Every caption has an AI note, the reel carries an "AI-assisted" label, and Instagram's AI label is turned on |
| Only content we have the rights to | Plans only use our own footage, our own photos and app screen recordings; no stock, brands, celebrities or music we don't own |
| Emails follow UK PECR | The agent sends no emails. Any added later carry an unsubscribe line and honour STOP replies |
| Everything auditable | All runs, spend, touches and reports stay in `logs/` and are never deleted; secrets live only in `.env` (gitignored) and are redacted from logs |
