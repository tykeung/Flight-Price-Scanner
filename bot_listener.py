#!/usr/bin/env python3
"""
bot_listener.py  --  Long-polling Telegram bot for flight price queries.

Commands:
    /prices             -- All-time best price per airline per route
    /history YYZ_SYD    -- 10 cheapest ever seen for that route
    /history MEL_YYZ    -- 10 cheapest ever seen for that route
    /help               -- Command list

Run as a background process (see README.md):
    nohup python3 bot_listener.py >> tracker.log 2>&1 &
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
import urllib.request
from typing import Optional

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [bot] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bot_listener")

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def _tg(method: str, **kwargs) -> dict:
    token = config.TELEGRAM_BOT_TOKEN
    url   = f"https://api.telegram.org/bot{token}/{method}"
    body  = json.dumps(kwargs).encode()
    req   = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("Telegram API error (%s): %s", method, exc)
        return {"ok": False}


def get_updates(offset: int) -> list:
    result = _tg("getUpdates", timeout=30, offset=offset, allowed_updates=["message"])
    return result.get("result", []) if result.get("ok") else []


def send_reply(chat_id: int, text: str) -> None:
    _tg(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_prices() -> str:
    """Return all-time best price per airline per route."""
    try:
        conn = _conn()
        rows = conn.execute(
            """
            SELECT route, airline, best_price_cad, best_price_usd, travel_date
            FROM best_prices
            ORDER BY route, best_price_cad ASC
            """
        ).fetchall()
        conn.close()
    except Exception as exc:
        return f"Database error: {exc}"

    if not rows:
        return "No price data yet.  Run flight_tracker.py first."

    lines = ["<b>All-Time Best Prices per Airline</b>"]
    current_route: Optional[str] = None

    for r in rows:
        if r["route"] != current_route:
            current_route = r["route"]
            label = next(
                (c["label"] for c in config.ROUTES if c["id"] == current_route),
                current_route,
            )
            lines.append(f"\n<b>{label}</b>")
        lines.append(
            f"  {r['airline']}: <b>${r['best_price_cad']:,.0f} CAD</b>"
            f" (${r['best_price_usd']:,.0f} USD) on {r['travel_date']}"
        )

    return "\n".join(lines)


def handle_history(route_id: str) -> str:
    """Return 10 cheapest prices ever seen for the given route."""
    valid = {r["id"] for r in config.ROUTES}
    route_id = route_id.upper()

    if route_id not in valid:
        valid_str = "  or  ".join(sorted(valid))
        return f"Unknown route.  Try: /history {valid_str}"

    try:
        conn = _conn()
        rows = conn.execute(
            """
            SELECT travel_date, airline, price_cad, price_usd, stops, duration
            FROM price_history
            WHERE route = ?
            ORDER BY price_cad ASC
            LIMIT 10
            """,
            (route_id,),
        ).fetchall()
        conn.close()
    except Exception as exc:
        return f"Database error: {exc}"

    label = next(
        (c["label"] for c in config.ROUTES if c["id"] == route_id), route_id
    )

    if not rows:
        return f"No data yet for {label}."

    lines = [f"<b>10 Cheapest -- {label}</b>\n"]
    for i, r in enumerate(rows, 1):
        stops_str = (
            "Nonstop" if r["stops"] == 0
            else f"{r['stops']} stop(s)"
            if r["stops"] is not None
            else "? stops"
        )
        lines.append(
            f"{i}. <b>${r['price_cad']:,.0f} CAD</b> -- {r['airline']}\n"
            f"   {r['travel_date']} | {stops_str} | {r['duration'] or 'N/A'}"
        )

    return "\n".join(lines)


HELP_TEXT = (
    "<b>Flight Price Tracker</b>\n\n"
    "/prices -- All-time best price per airline and route\n"
    "/history YYZ_SYD -- 10 cheapest prices for Toronto -> Sydney\n"
    "/history MEL_YYZ -- 10 cheapest prices for Melbourne -> Toronto\n"
    "/help -- This message"
)


def dispatch(message: dict) -> None:
    raw_text = (message.get("text") or "").strip()
    chat_id  = message["chat"]["id"]

    # Strip @BotName suffix from commands (works in groups)
    text = raw_text.split("@")[0] if raw_text.startswith("/") else raw_text

    if text == "/prices":
        send_reply(chat_id, handle_prices())

    elif text.startswith("/history"):
        parts = text.split(None, 1)
        if len(parts) < 2:
            send_reply(chat_id, "Usage: /history YYZ_SYD  or  /history MEL_YYZ")
        else:
            send_reply(chat_id, handle_history(parts[1].strip()))

    elif text in ("/start", "/help"):
        send_reply(chat_id, HELP_TEXT)


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def main() -> None:
    if config.TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.error("Telegram bot token not set in config.py.  Exiting.")
        sys.exit(1)

    log.info("Bot listener started (long-polling).")
    offset = 0

    while True:
        try:
            updates = get_updates(offset)
        except Exception as exc:
            log.error("get_updates exception: %s", exc)
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message")
            if msg:
                try:
                    dispatch(msg)
                except Exception as exc:
                    log.error("dispatch error: %s", exc)

        # No explicit sleep: long polling (timeout=30 s) handles the idle wait


if __name__ == "__main__":
    main()
