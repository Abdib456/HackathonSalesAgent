# HackathonSalesAgent

An AI marketing agent for our photography + fashion try-on app, built for the
Shipyard "Make Me Money" hackathon. It does the research, scripting and reporting
behind our Instagram reels; we film, edit and post them by hand. Strangers buy in
our web app through a live Stripe payment link.

## What the agent does

1. **Researches** what's working in fashion / try-on reels this week (Tavily search + a Claude summary, with sources).
2. **Writes reel plans** with Claude: idea, 5 hooks scored 1-10, shot list, voiceover, caption with an AI note, "link in bio" call to action.
3. **Learns**: new plans lean towards reels that made money and away from plans we rejected.
4. **Reports**: profit (live Stripe sales − refunds/chargebacks − spend), touches, and sales per reel.

Every £ spent is checked against the £100 cap and logged. Every human step is logged as a touch.

## The flow, start to finish

| # | Step | Who | Touch? |
|---|------|-----|--------|
| 1 | Daily research brief → `data/research/YYYY-MM-DD.md` | Agent | — |
| 2 | Reel plan → `approvals/pending/reel-NNN.md` (keeps 2 ready, max 2 new a day) | Agent | — |
| 3 | Read the plan. Weak? Move it to `approvals/rejected/` (optional `Reason: ...` line) | Human | yes (logged automatically) |
| 4 | Film and edit it in Edits / CapCut, with an "AI-assisted" label on screen | Human | yes (log it, see below) |
| 5 | Post on Instagram with the plan's caption; set the bio link the plan gives you | Human | yes |
| 6 | Move the plan to `approvals/approved/`: marks it posted and frees a slot for the next plan | Human | logged automatically as the posting touch |
| 7 | A stranger taps the bio link, signs up, uses the free edit, pays in the app | Customer + app | — |
| 8 | Report → `logs/reports/YYYY-MM-DD.md`, refreshed every cycle | Agent | — |

About 3 touches per posted reel. Log the ones the agent can't see (filming, editing) with:

```bash
python -m agent.logger touch reel-001 "filmed and edited in CapCut"
```

and mirror every touch with `/touch` (and every spend with `/spend`) in Discord.

**Which reel sold?** The plan's bio link is `LANDING_PAGE_URL?ref=reel-NNN`. If the app
passes that `ref` to Stripe as `client_reference_id`, the report credits each sale to
its reel and the agent learns from it. If not, sales still count, but show as "unknown".

## The cycle

`python -m agent.main` runs **one cycle** and exits; `--loop` repeats it **every 15
minutes** until Ctrl+C. Stopping is safe: all state is in files.

Each cycle: log plan moves as touches → research (once a day) → new plans (if fewer
than 2 waiting) → report. Anything not set up yet is skipped and logged, never fatal.

Cost: most cycles cost £0. Plans call Claude (~4p each, max 2/day), plus one research
summary a day (~5p). The 8 daily Tavily searches use partner credits.

## Where it runs

On a Mac: `caffeinate -i python -m agent.main --loop` (keeps it awake). The agent's
state is files you move by hand (plans) and logs we commit, so it runs where we work.
Replit isn't needed for manual posting.

## Setup

```bash
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
| `POSTING` | `manual` (default) or `api` | — |

The app's context goes in `agent/prompts/system.md` and `brand.md` (the product,
audience, tone). Until it's filled in, plans are generic.

## Folders

| Folder | What's in it | In git? |
|---|---|---|
| `agent/` | The code: `main.py`, `tools/`, `analytics/`, `prompts/` | yes |
| `approvals/pending/` | Plans waiting to be filmed | yes |
| `approvals/approved/` | Posted reels (moved here by us) | yes |
| `approvals/rejected/` | Plans we said no to; new plans avoid them | yes |
| `data/research/` | Daily research brief with source links (AI-generated) | yes |
| `logs/runs/` | Full transcript of every cycle | yes |
| `logs/spend.jsonl`, `logs/touches.jsonl` | Every £ spent, every human step | yes |
| `logs/reports/` | Daily profit + per-reel sales (counts only) | yes |

## Optional: agent edits, publishes and DMs (`POSTING=api`)

Built but dormant. With `POSTING=api`, plans say "comment KEYWORD", the team drops
footage into `footage/reel-NNN/`, the agent edits it with ffmpeg (9:16, captions,
"AI-assisted" tag, up to 3 hook versions), publishes one a day after approval, DMs
everyone who comments the keyword, and emails signups. It needs `agent/tools/instagram.py`
(not written), `agent/analytics/signups.py` (not written), a Meta app with the
`instagram_business_*` permissions, a public URL for `creatives/` (Replit), and the
`INSTAGRAM_*`, `RESEND_API_KEY`, `EMAIL_FROM`, `STRIPE_PAYMENT_LINK` and `APP_LIVE` keys.
Code: `tools/make_reel.py`, `tools/email.py`; folders `footage/`, `creatives/`, `logs/outbound/`.

## Hackathon rules

*Added with the context commit.*
