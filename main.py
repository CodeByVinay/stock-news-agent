"""Stock news agent - decision support for Indian F&O stocks.

Usage:
  python main.py            # run forever, poll every POLL_SECONDS during market hours
  python main.py --once     # one polling cycle and exit (good for cron / GitHub Actions)
  python main.py --demo     # run the analysis on a sample filing (needs ANTHROPIC_API_KEY)
"""
import argparse
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import analyzer
import notifier
import sources
from watchlist import WATCHLIST, match

IST = timezone(timedelta(hours=5, minutes=30))  # India has no DST; avoids needing tzdata on Windows
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
NEWS_EVERY_N_CYCLES = int(os.getenv("NEWS_EVERY_N_CYCLES", "5"))  # per-stock Google News search (40 requests)
FEEDS_EVERY_N_CYCLES = int(os.getenv("FEEDS_EVERY_N_CYCLES", "2"))  # general news RSS feeds (~10 requests)
MAX_ALERTS_PER_CYCLE = int(os.getenv("MAX_ALERTS_PER_CYCLE", "8"))
DB = os.getenv("DB_PATH", "seen.db")


def db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, ts TEXT)")
    return con


def is_new(con, item_id) -> bool:
    return con.execute("SELECT 1 FROM seen WHERE id=?", (item_id,)).fetchone() is None


def mark(con, item_id):
    con.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)", (item_id, datetime.now(IST).isoformat()))
    con.commit()


def market_hours(now=None) -> bool:
    """Poll from 07:30 to 20:00 IST on weekdays (filings also land pre/post market)."""
    now = now or datetime.now(IST)
    return now.weekday() < 5 and (7, 30) <= (now.hour, now.minute) <= (20, 0)


def collect(cycle: int):
    items = []
    for name, fn in (("NSE", sources.fetch_nse), ("BSE", sources.fetch_bse)):
        try:
            items += fn()
        except Exception as e:  # one broken source must not stop the others
            print(f"[warn] {name} fetch failed: {e}")
    if cycle % NEWS_EVERY_N_CYCLES == 0:
        try:
            items += sources.fetch_news(WATCHLIST)
        except Exception as e:
            print(f"[warn] news fetch failed: {e}")
    if cycle % FEEDS_EVERY_N_CYCLES == 0:
        try:
            items += sources.fetch_feeds()
        except Exception as e:
            print(f"[warn] feeds fetch failed: {e}")
    return items


def process(items, con, first_run_seed=False):
    sent = 0
    for item in items:
        if not is_new(con, item["id"]):
            continue
        sym = match(item)
        if not sym:
            mark(con, item["id"])
            continue
        item["symbol"] = item.get("symbol") or sym
        if first_run_seed:  # don't alert on the backlog at first start
            mark(con, item["id"])
            continue
        if sent >= MAX_ALERTS_PER_CYCLE:
            break  # leave unmarked; picked up next cycle
        try:
            t, a = analyzer.assess(item)
            if a:
                notifier.send(notifier.format_brief(item, t, a))
                sent += 1
            mark(con, item["id"])
        except Exception as e:
            print(f"[warn] analysis failed for {item['id']}: {e}")
    return sent


def run_cycle(con, cycle, seed=False):
    items = collect(cycle)
    n = process(items, con, first_run_seed=seed)
    print(f"[{datetime.now(IST):%H:%M:%S}] cycle {cycle}: {len(items)} items, {n} alerts")


def demo():
    item = {
        "id": "demo", "symbol": "EXAMPLECO", "company": "Example Infra Ltd",
        "source": "NSE filing (sample)", "title": "Award of Order",
        "text": "Example Infra Ltd has received a Letter of Award worth Rs 2,400 crore from "
                "a state transport authority for a metro depot project, to be executed over "
                "30 months. The company's FY26 revenue was Rs 6,100 crore.",
        "time": datetime.now(IST).isoformat(), "url": "",
    }
    t, a = analyzer.assess(item)
    print("triage:", t)
    if a:
        notifier.send(notifier.format_brief(item, t, a))
    else:
        print("Item scored below MIN_SCORE, so no brief was sent. Try MIN_SCORE=1 for the demo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scheduled", action="store_true",
                    help="one cycle, only during market hours (for GitHub Actions / cron)")
    args = ap.parse_args()

    if args.demo:
        demo()
        raise SystemExit

    con = db()
    first = con.execute("SELECT COUNT(*) FROM seen").fetchone()[0] == 0
    if args.scheduled:
        if not market_hours() and os.getenv("FORCE_RUN") != "1":
            print("Outside market hours (weekdays 07:30-20:00 IST) - nothing to do.")
            raise SystemExit
        # derive a cycle number from the clock so "every Nth cycle" jobs still rotate across runs
        run_cycle(con, int(time.time() // 600), seed=first)
        raise SystemExit
    if args.once:
        run_cycle(con, 0, seed=first)
        raise SystemExit

    cycle = 0
    while True:
        if market_hours():
            run_cycle(con, cycle, seed=(first and cycle == 0))
            cycle += 1
        time.sleep(POLL_SECONDS)
