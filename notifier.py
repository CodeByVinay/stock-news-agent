"""Telegram delivery (falls back to console if not configured)."""
import html
import os

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ICON = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪", "mixed": "🟡"}
DISCLAIMER = "Decision support only - not investment advice. Verify before acting."


def _clip(text, n=200):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def format_brief(item, triage, a) -> str:
    """Compact alert: fits on one phone screen."""
    e = lambda s, n=200: html.escape(_clip(s, n))
    t = a.get("trade_setup", {}) or {}
    sym = item.get("symbol") or item["company"]
    src = item["source"].replace("News: ", "").replace(" (via Google News)", "")
    ver = [str(v) for v in (a.get("verify") or [])][:2]
    lines = [
        f"{ICON.get(a.get('sentiment'), '⚪')} <b>{html.escape(sym)}</b> · {e(a.get('headline', item['title']), 120)}",
        f"<i>{html.escape(src)} · {html.escape(str(a.get('impact', '?')))} impact · {triage.get('score', '?')}/10</i>",
        "",
        e(a.get("what_happened", ""), 260),
        f"<b>Why:</b> {e(a.get('why_it_matters', ''), 200)}",
        f"<b>Setup:</b> {e(t.get('bias', ''), 30)} - {e(t.get('approach', ''), 160)}",
        f"<b>Risk:</b> {e(t.get('stop_and_sizing', ''), 140)}",
    ]
    if ver:
        lines.append("<b>Check:</b> " + e("; ".join(ver), 180))
    if item.get("url"):
        lines.append(f"<a href=\"{html.escape(item['url'])}\">Source</a>")
    lines.append("<i>Decision support only, not advice.</i>")
    return "\n".join(lines)


def send(text: str) -> bool:
    if not (TOKEN and CHAT_ID):
        print("\n" + "=" * 60 + "\n" + text + "\n" + "=" * 60)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID, "text": text[:4000], "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
    except Exception as e:
        print(f"[telegram] could not reach Telegram: {type(e).__name__}")
        print(text)
        return False
    if r.ok:
        print("[telegram] message sent")
    else:
        # never print the URL (it contains the bot token) - only Telegram's reason
        print(f"[telegram] FAILED {r.status_code}: {r.text[:300]}")
        print(text)
    return r.ok
