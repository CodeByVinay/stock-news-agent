"""News sources: NSE + BSE corporate announcements and Google News RSS.

NSE/BSE endpoints are unofficial and need browser-like headers/cookies.
They can change without notice - if one breaks, the others keep working.
"""
import calendar
import hashlib
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote

import feedparser
import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def fetch_nse(timeout=15):
    """NSE corporate announcements (equities)."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    s.get("https://www.nseindia.com", timeout=timeout)  # sets cookies
    r = s.get(
        "https://www.nseindia.com/api/corporate-announcements",
        params={"index": "equities"},
        headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"},
        timeout=timeout,
    )
    r.raise_for_status()
    items = []
    for a in r.json():
        sym = a.get("symbol", "")
        text = f"{a.get('desc', '')}. {a.get('attchmntText', '')}".strip()
        items.append({
            "id": _id("nse", sym, a.get("an_dt"), a.get("desc")),
            "symbol": sym,
            "company": a.get("sm_name", sym),
            "source": "NSE filing",
            "title": a.get("desc", ""),
            "text": text[:2500],
            "time": a.get("an_dt", ""),
            "url": a.get("attchmntFile", ""),
        })
    return items


def fetch_bse(timeout=15):
    """BSE corporate announcements for today and yesterday.

    BSE often rejects scripts (403). We warm up a browser-like session first.
    Most F&O stocks also file on NSE, so set DISABLE_BSE=1 to skip this source.
    """
    if os.getenv("DISABLE_BSE") == "1":
        return []
    today = datetime.now()
    frm = (today - timedelta(days=1)).strftime("%Y%m%d")
    to = today.strftime("%Y%m%d")
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.bseindia.com/corporates/ann.html",
        "Origin": "https://www.bseindia.com",
    })
    s.get("https://www.bseindia.com/corporates/ann.html", timeout=timeout)  # picks up cookies
    r = s.get(
        "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
        params={
            "pageno": 1, "strCat": "-1", "strPrevDate": frm, "strScrip": "",
            "strSearch": "P", "strToDate": to, "strType": "C", "subcategory": "-1",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    items = []
    for a in r.json().get("Table", []):
        name = a.get("SLONGNAME", "")
        text = a.get("NEWSSUB") or a.get("HEADLINE") or ""
        items.append({
            "id": _id("bse", a.get("NEWSID")),
            "symbol": "",  # BSE gives scrip code; matched by company name
            "company": name,
            "source": "BSE filing",
            "title": a.get("CATEGORYNAME", ""),
            "text": text[:2500],
            "time": a.get("NEWS_DT", ""),
            "url": f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{a.get('ATTACHMENTNAME','')}",
        })
    return items


# Query terms that surface the kinds of news that move stocks.
NEWS_TERMS = (
    '("order win" OR bags OR "secures contract" OR fraud OR whistleblower OR '
    '"SEBI order" OR "show cause" OR raid OR "forensic audit" OR "auditor resigns" OR '
    'pledge OR "block deal" OR buyback OR "rating downgrade" OR "rating upgrade" OR '
    '"promoter" OR "short seller")'
)


def fetch_news(symbols_names, timeout=15):
    """Google News RSS per stock. symbols_names: list of (symbol, company name)."""
    items = []
    for sym, name in symbols_names:
        q = quote(f'"{name}" {NEWS_TERMS} when:1d')
        url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": UA})
        except Exception:
            continue
        for e in feed.entries[:5]:
            items.append({
                "id": _id("news", e.get("link")),
                "symbol": sym,
                "company": name,
                "source": "News: " + e.get("source", {}).get("title", "web"),
                "title": e.get("title", ""),
                "text": re.sub("<[^>]+>", "", e.get("summary", ""))[:1500],
                "time": e.get("published", ""),
                "url": e.get("link", ""),
            })
    return items


# ---------- general business-news RSS feeds ----------
# Reuters has no free public RSS (and scraping is not allowed), so Reuters headlines come via
# Google News "site:" searches. Feed URLs can change; a dead feed just prints a warning.
def _gnews(q):
    return "https://news.google.com/rss/search?q=" + quote(q + " when:1d") + "&hl=en-IN&gl=IN&ceid=IN:en"


FEEDS = {
    "Reuters (via Google News)": _gnews("site:reuters.com India shares OR stock OR company OR shareholders"),
    "Reuters risk (via Google News)": _gnews("site:reuters.com India fraud OR probe OR raid OR whistleblower OR \"short seller\" OR penalty"),
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Economic Times Stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    # Moneycontrol and SEBI block direct RSS access, so these go through Google News
    "Moneycontrol (via Google News)": _gnews("site:moneycontrol.com India stock OR shares OR company order OR probe OR results OR rating"),
    "Business Standard Markets": "https://www.business-standard.com/rss/markets-106.rss",
    "Mint Markets": "https://www.livemint.com/rss/markets",
    "BusinessLine Markets": "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    "SEBI action (via Google News)": _gnews('SEBI order OR "show cause" OR ban OR penalty OR investigation listed company India'),
}


def fetch_feeds(max_age_hours=36):
    """Headlines from FEEDS that mention a watchlist stock. Headline + short summary only."""
    from watchlist import WATCHLIST, match_text
    names = dict(WATCHLIST)
    cutoff = time.time() - max_age_hours * 3600
    items = []
    for label, url in FEEDS.items():
        try:
            feed = feedparser.parse(url, agent=UA)
        except Exception as e:
            print(f"[warn] feed '{label}' failed: {type(e).__name__}")
            continue
        if not feed.entries:
            print(f"[warn] feed '{label}' returned no items (URL may have changed or blocked)")
            continue
        for e in feed.entries[:60]:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and calendar.timegm(ts) < cutoff:
                continue
            title = e.get("title", "")
            summary = re.sub("<[^>]+>", "", e.get("summary", ""))[:1200]
            for sym in match_text(f"{title}. {summary}"):
                items.append({
                    "id": _id("feed", e.get("link", title), sym),
                    "symbol": sym,
                    "company": names.get(sym, sym),
                    "source": f"News: {label}",
                    "title": title,
                    "text": summary,
                    "time": e.get("published", ""),
                    "url": e.get("link", ""),
                })
    return items
