# Stock News Agent (decision support)

Watches NSE/BSE corporate filings and news for a watchlist of Indian F&O stocks.
Claude triages each item, and for material ones sends a Telegram brief:
what happened, why it matters, priced-in risk, a swing/options trade setup, and a verify checklist.

**Decision support only. It never places orders and is not investment advice.**

## Setup (about 10 minutes)

1. `pip install -r requirements.txt`
2. Telegram: message **@BotFather** -> `/newbot` -> copy the token. Message **@userinfobot** to get your chat id. Send your new bot any message once.
3. `cp .env.example .env`, fill in the keys, then `set -a; source .env; set +a`
4. Test the analysis (no market data needed): `python main.py --demo`
5. Run it: `python main.py` (loops every 2 min, weekdays 07:30-20:00 IST), or `python main.py --once` from cron.

On the first run it records the existing backlog without alerting, so you only get new items.

## Files

- `watchlist.py` - stocks to track (edit this)
- `sources.py` - NSE announcements, BSE announcements, Google News RSS
- `analyzer.py` - triage (Haiku) then full brief (Sonnet); prompts live here
- `notifier.py` - Telegram formatting and sending
- `main.py` - polling loop, dedupe (sqlite), alert cap

## Things to know

- The NSE/BSE endpoints are unofficial and sometimes block datacentre IPs or change format. Run this from your own machine/home network first. If one source breaks, the others keep running and a warning is printed.
- Cost: the cheap triage model sees every new item for your watchlist; the stronger model runs only on items scoring >= `MIN_SCORE`. Raise `MIN_SCORE` to cut noise and cost.
- News is often priced in within minutes. The brief always includes a "priced in?" check; look at the live chart and volume before acting.
- The model only sees the filing/news text, not live prices, the F&O ban list or option chains yet. Those are the next upgrades.

## Next upgrades

1. Live price/volume/OI context (broker API or NSE option chain) so the setup uses real levels
2. F&O ban list and lot-size awareness
3. Short-seller / X (Twitter) watch for whistleblower and fraud allegations
4. PDF attachment reading for filings (order size, counterparties)
5. Daily pre-market and post-market digest
6. Simple dashboard and a log of past alerts vs outcomes, to tune `MIN_SCORE`

## Compliance

For your own trading this is fine. Publishing these as trade calls to others (LinkedIn, Telegram channels) can fall under SEBI research analyst / investment adviser rules.
