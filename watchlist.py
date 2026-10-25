"""Watchlist: (NSE symbol, name used for news search).

Starter set of liquid, volatile F&O stocks. Edit freely - add or remove lines.
Filings are matched on symbol (NSE) or company name (BSE); news is searched by name.
"""

WATCHLIST = [
    ("RELIANCE", "Reliance Industries"),
    ("TCS", "Tata Consultancy Services"),
    ("INFY", "Infosys"),
    ("HDFCBANK", "HDFC Bank"),
    ("ICICIBANK", "ICICI Bank"),
    ("SBIN", "State Bank of India"),
    ("AXISBANK", "Axis Bank"),
    ("KOTAKBANK", "Kotak Mahindra Bank"),
    ("BAJFINANCE", "Bajaj Finance"),
    ("TATAMOTORS", "Tata Motors"),
    ("TATASTEEL", "Tata Steel"),
    ("ADANIENT", "Adani Enterprises"),
    ("ADANIPORTS", "Adani Ports"),
    ("ADANIPOWER", "Adani Power"),
    ("VEDL", "Vedanta"),
    ("HINDALCO", "Hindalco"),
    ("JSWSTEEL", "JSW Steel"),
    ("ONGC", "ONGC"),
    ("COALINDIA", "Coal India"),
    ("NTPC", "NTPC"),
    ("POWERGRID", "Power Grid"),
    ("BHEL", "BHEL"),
    ("HAL", "Hindustan Aeronautics"),
    ("BEL", "Bharat Electronics"),
    ("LT", "Larsen & Toubro"),
    ("IRFC", "IRFC"),
    ("RVNL", "Rail Vikas Nigam"),
    ("SUZLON", "Suzlon Energy"),
    ("YESBANK", "Yes Bank"),
    ("IDEA", "Vodafone Idea"),
    ("BHARTIARTL", "Bharti Airtel"),
    ("ZOMATO", "Eternal Zomato"),
    ("PAYTM", "One97 Communications Paytm"),
    ("DLF", "DLF"),
    ("SUNPHARMA", "Sun Pharma"),
    ("CIPLA", "Cipla"),
    ("DRREDDY", "Dr Reddys Laboratories"),
    ("MARUTI", "Maruti Suzuki"),
    ("M&M", "Mahindra & Mahindra"),
    ("TITAN", "Titan Company"),
]

SYMBOLS = {s for s, _ in WATCHLIST}
# lower-cased fragments used to match BSE filings (which carry names, not NSE symbols)
NAME_KEYS = {n.lower(): s for s, n in WATCHLIST}


def match(item) -> str | None:
    """Return the NSE symbol if this item belongs to a watchlist stock."""
    sym = item.get("symbol", "").upper()
    if sym in SYMBOLS:
        return sym
    co = item.get("company", "").lower().replace(" limited", "").replace(" ltd.", "").replace(" ltd", "").strip()
    if len(co) < 4:
        return None
    for key, s in NAME_KEYS.items():
        # exact-ish name match either way round (e.g. "Infosys Ltd" vs "Infosys")
        if key == co or key in co or co in key:
            return s
    return None


# ---- matching headlines from general news feeds to watchlist stocks ----
import re as _re

ALIAS_EXTRA = {
    "RELIANCE": ["Reliance", "RIL"], "SBIN": ["SBI", "State Bank"], "KOTAKBANK": ["Kotak Bank"],
    "POWERGRID": ["PGCIL"], "LT": ["L&T", "Larsen"], "BHARTIARTL": ["Airtel"],
    "ZOMATO": ["Zomato", "Eternal Ltd"], "PAYTM": ["Paytm"], "DRREDDY": ["Dr Reddy"],
    "MARUTI": ["Maruti"], "TCS": ["TCS"], "INFY": ["Infosys"], "ADANIENT": ["Adani Enterprises"],
    "IDEA": ["Vodafone Idea"], "TITAN": ["Titan"], "M&M": ["M&M"],
}


def _alias_patterns():
    pats = []
    for sym, name in WATCHLIST:
        for a in {name, *ALIAS_EXTRA.get(sym, [])}:
            # case-sensitive on purpose: headlines capitalise company names, and this avoids
            # false hits like "reliance on imports" or a lower-case "titan"
            pats.append((sym, _re.compile(r"(?<![A-Za-z0-9])" + _re.escape(a) + r"(?![A-Za-z0-9])")))
    return pats


_PATS = _alias_patterns()


def match_text(text: str, limit: int = 2):
    """NSE symbols of watchlist stocks mentioned in free text (headline/summary)."""
    found = []
    for sym, p in _PATS:
        if sym not in found and p.search(text):
            found.append(sym)
            if len(found) >= limit:
                break
    return found
