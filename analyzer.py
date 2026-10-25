"""LLM analysis. Free by default (Google Gemini free tier); Claude optional.

LLM_PROVIDER=gemini (default, free) : ONE request per item (score + brief together),
                                      plus a keyword pre-filter to save free-tier quota.
LLM_PROVIDER=claude (paid API)      : cheap triage model, then stronger model for the brief.
"""
import json
import os
import re
import time

import requests

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
MIN_SCORE = int(os.getenv("MIN_SCORE", "6"))

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "claude-haiku-5-5")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "claude-sonnet-5-5")

# Routine filings that almost never move a stock - skipped without spending an LLM request.
ROUTINE = re.compile(
    r"trading window|newspaper|copy of advertisement|certificate under regulation|"
    r"compliance certificate|scrutinizer|investor grievance|share transfer|"
    r"loss of share certificate|duplicate share|intimation of (analyst|investor) (meet|call)|"
    r"schedule of (analyst|investor)|record date for|book closure|postal ballot notice|"
    r"annual general meeting notice|reg\. ?74|depositories and participants|"
    r"closure of trading window|statement of deviation|disclosure of voting results",
    re.I,
)


MATERIAL = re.compile(
    r"order|contract|bags|wins|secures|awarded|letter of (award|intent)|fraud|probe|raid|"
    r"\bsebi\b|\bed\b|\bcbi\b|penalty|fine[sd]?\b|resign|auditor|whistle|short.?sell|"
    r"downgrad|upgrad|stake|block deal|bulk deal|buyback|dividend|bonus|split|result|profit|"
    r"loss|revenue|guidance|merger|acqui|takeover|demerger|ipo|offer for sale|\bfpo\b|approval|"
    r"approves|ban|default|pledge|rating|outage|shutdown|recall|lawsuit|court|tribunal|"
    r"insolven|nclt|tax|dues|investigation|charge|allegation|scam|forensic|promoter|"
    r"capex|expansion|plant|launch|tender|licen[cs]e|spectrum|tariff|price hike|"
    r"surge|plunge|crash|jump|rall(y|ies)|tumble|slump|upper circuit|lower circuit",
    re.I,
)


def prefilter(item) -> bool:
    """True if the item is worth sending to the LLM (saves free-tier quota)."""
    blob = f"{item['title']} {item['text'][:300]}"
    if item["source"].startswith("News"):
        return bool(MATERIAL.search(blob))
    return not ROUTINE.search(blob)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


SCORING_GUIDE = """Score 0-10 how likely the item is to move the stock materially over 1-3 days.
High (7-10): large order wins relative to market cap/revenue, fraud/whistleblower/short-seller
allegations, SEBI/ED/CBI action, auditor resignation, results surprises, M&A, big block deals,
promoter pledge/sale, rating changes, regulatory approvals/bans, guidance changes.
Low (0-3): routine compliance, AGM notices, duplicate/old items, generic market commentary."""

BRIEF_SCHEMA = """{
 "headline": "one line, what happened",
 "what_happened": "2-3 sentences, facts only",
 "why_it_matters": "impact on revenue/earnings/risk/sentiment; size relative to company",
 "sentiment": "bullish" | "bearish" | "neutral" | "mixed",
 "impact": "high" | "medium" | "low",
 "already_priced_in_risk": "how likely it is already reflected, and what to check",
 "trade_setup": {
   "bias": "long" | "short" | "avoid/wait",
   "approach": "e.g. wait for first 15-min candle, buy on retest, fade the spike, stay out",
   "instrument_ideas": "cash vs futures vs options; option structure idea (e.g. debit spread) and why",
   "levels_to_check": "what to look at on the chart: prior day high/low, support/resistance, volume",
   "stop_and_sizing": "stop-loss logic and risk per trade as % of capital (suggest <=1%)",
   "invalidation": "what would prove this thesis wrong"
 },
 "watch_next": "next trigger: follow-up filing, management call, regulator response, etc.",
 "verify": ["checklist of things to confirm before acting"]
}"""

ANALYST_RULES = """You are a market analyst assisting an Indian F&O trader who trades swing positions
and options. This is decision support, not advice; the trader decides. Be specific, concise and
honest about uncertainty. Do not invent facts or numbers that are not in the item. If key facts
are missing (order size, margin impact, price reaction), say what to verify. Consider NSE/BSE
circuit limits, liquidity, F&O ban list, lot sizes, and that fast news is often priced in within minutes.
BE BRIEF: the trader reads this on a phone. Every text field must be under 25 words, plain language,
no filler. what_happened is at most 2 short sentences. Give at most 2 items in verify."""

TRIAGE_SYSTEM = f"""You screen Indian stock-market news for an F&O swing/options trader.
{SCORING_GUIDE}
Reply ONLY with JSON: {{"score": int, "category": str, "reason": str}}"""

ANALYSIS_SYSTEM = f"""{ANALYST_RULES}
Reply ONLY with JSON:
{BRIEF_SCHEMA}"""

COMBINED_SYSTEM = f"""{ANALYST_RULES}
{SCORING_GUIDE}
Reply ONLY with JSON: {{"score": int, "category": str, "brief": <brief or null>}}
If score < {MIN_SCORE}, set "brief" to null (keep it short). Otherwise "brief" must follow this schema:
{BRIEF_SCHEMA}"""


def _item_text(item, extra="") -> str:
    return (
        f"Stock: {item['company']} ({item.get('symbol','')})\nSource: {item['source']}\n"
        f"Time: {item['time']}\nTitle: {item['title']}\nText: {item['text']}{extra}"
    )


# ---------- Gemini (free) ----------
_last_call = 0.0


def _gemini(system: str, user: str, max_tokens: int = 4096) -> str:
    global _last_call
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
        },
    }
    for attempt in range(4):
        # stay under free-tier per-minute limits (~10 requests/min on flash models)
        wait = 6.5 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        # key goes in a header (not the URL) so it never shows up in error messages
        try:
            r = requests.post(url, headers={"x-goog-api-key": GEMINI_KEY}, json=body, timeout=120)
        except requests.exceptions.RequestException as e:
            print(f"[gemini] network problem ({type(e).__name__}) - slow model or connection. Retrying...")
            time.sleep(5)
            continue
        if r.status_code in (429, 503):
            print(f"[gemini] {GEMINI_MODEL} returned {r.status_code}: {r.text[:300].strip()}")
            if attempt < 3:
                print(f"[gemini] waiting {15 * (attempt + 1)}s then retrying...")
            time.sleep(15 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"Gemini error {r.status_code} for model '{GEMINI_MODEL}': {r.text[:400].strip()}")
        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Gemini returned no answer: {str(data)[:400]}")
        return "".join(p.get("text", "") for p in parts)
    raise RuntimeError(
        f"Gemini kept timing out or refusing ('{GEMINI_MODEL}'): likely the free quota for this model is used up or "
        "not available to your account. Try another model (set GEMINI_MODEL) or wait a few minutes."
    )


# ---------- Claude (paid, optional) ----------
_client = None


def _claude(model: str, system: str, user: str, max_tokens: int) -> str:
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    r = _client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return r.content[0].text


# ---------- public API used by main.py ----------
def assess(item):
    """Return (triage_dict, brief_dict_or_None). Brief is None if the item is not material."""
    if not prefilter(item):
        return {"score": 0, "category": "routine", "reason": "filtered"}, None

    if PROVIDER == "claude":
        t = _json(_claude(TRIAGE_MODEL, TRIAGE_SYSTEM, _item_text(item)[:2500], 200))
        if int(t.get("score", 0)) < MIN_SCORE:
            return t, None
        a = _json(_claude(ANALYSIS_MODEL, ANALYSIS_SYSTEM,
                          _item_text(item, f"\nTriage: {json.dumps(t)}"), 1500))
        return t, a

    out = _json(_gemini(COMBINED_SYSTEM, _item_text(item)))
    t = {"score": out.get("score", 0), "category": out.get("category", "")}
    brief = out.get("brief") if int(t["score"] or 0) >= MIN_SCORE else None
    return t, brief
