#!/usr/bin/env python3
"""
flight_tracker.py  --  Scrape flight prices, log to SQLite, alert via Telegram.

Run manually:
    python3 flight_tracker.py

Scheduled via cron (see setup.sh output for the exact line).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from fast_flights import FlightData, Passengers, get_flights

import config

# ---------------------------------------------------------------------------
# Logging  (file + stdout)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            route       TEXT    NOT NULL,
            travel_date TEXT    NOT NULL,
            airline     TEXT    NOT NULL,
            price_usd   REAL    NOT NULL,
            price_cad   REAL    NOT NULL,
            stops       INTEGER,
            duration    TEXT,
            arrival     TEXT,
            layovers    TEXT,
            scraped_at  TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS best_prices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            route           TEXT    NOT NULL,
            airline         TEXT    NOT NULL,
            best_price_cad  REAL    NOT NULL,
            best_price_usd  REAL    NOT NULL,
            travel_date     TEXT    NOT NULL,
            last_alert_at   TEXT,
            updated_at      TEXT    NOT NULL,
            UNIQUE(route, airline)
        )
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_sample_dates() -> list:
    """Return DATES_PER_RUN dates spread evenly between DATE_START and DATE_END."""
    start = datetime.strptime(config.DATE_START, "%Y-%m-%d")
    end   = datetime.strptime(config.DATE_END,   "%Y-%m-%d")
    total = (end - start).days
    n     = config.DATES_PER_RUN

    if n == 1:
        return [start.strftime("%Y-%m-%d")]

    return [
        (start + timedelta(days=round(i * total / (n - 1)))).strftime("%Y-%m-%d")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# FX rate
# ---------------------------------------------------------------------------

def fetch_fx_rate() -> float:
    """Fetch live USD -> CAD rate from frankfurter.app (no API key needed)."""
    url = "https://api.frankfurter.app/latest?from=USD&to=CAD"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FlightTracker/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            rate = float(data["rates"]["CAD"])
            log.info("FX rate USD->CAD: %.4f", rate)
            return rate
    except Exception as exc:
        log.warning(
            "FX fetch failed (%s); using fallback rate %.2f",
            exc,
            config.FX_FALLBACK_RATE,
        )
        return config.FX_FALLBACK_RATE


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

def parse_price_usd(price_str: str) -> Optional[float]:
    """Parse a price string like '$1234' or '1,234' into a float.

    Returns None when the price is zero or unparseable (e.g. flight had no
    listed price on Google Flights).
    """
    cleaned = re.sub(r"[^\d.]", "", price_str)
    if not cleaned:
        return None
    value = float(cleaned)
    return value if value > 0 else None


# ---------------------------------------------------------------------------
# Layover filter
# ---------------------------------------------------------------------------

def passes_layover_filter(layovers_str: str) -> bool:
    """Return True if the flight should be kept.

    Keeps the flight when:
    - layover data is unavailable (empty string) -- always include per spec
    - at least one layover airport is in LAYOVER_AIRPORTS

    fast-flights does not expose layover airport codes, so layovers_str will
    always be empty and this function will always return True.  The logic is
    present so it activates automatically if the data becomes available.
    """
    if not layovers_str:
        return True  # can't determine -> include per spec
    airports = {a.strip().upper() for a in re.split(r"[,;/\s]+", layovers_str) if a.strip()}
    return bool(airports & config.LAYOVER_AIRPORTS)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _tg_post(payload: dict) -> None:
    token = config.TELEGRAM_BOT_TOKEN
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    body  = json.dumps(payload).encode()
    req   = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                log.error("Telegram API error: %s", result)
    except Exception as exc:
        log.error("Failed to send Telegram message: %s", exc)


def send_telegram(text: str) -> None:
    if config.TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.warning("Telegram not configured -- alert not sent")
        log.info("Alert text:\n%s", text)
        return
    _tg_post(
        {
            "chat_id":                  config.TELEGRAM_CHAT_ID,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": False,
        }
    )


def build_alert(
    route: dict,
    price_cad: float,
    price_usd: float,
    travel_date: str,
    airline: str,
    stops: int,
    duration: str,
    arrival: str,
    layovers: str,
    prev_best_cad: Optional[float],
    fx_rate: float,
) -> str:
    date_fmt  = datetime.strptime(travel_date, "%Y-%m-%d").strftime("%b %-d, %Y")
    stops_str = "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"
    layover_str = layovers if layovers else "unknown (not available from data source)"

    gf_url = (
        "https://www.google.com/travel/flights?q=Flights+from+"
        f"{route['from']}+to+{route['to']}+on+{travel_date}"
    )

    savings_line = ""
    if prev_best_cad is not None:
        diff = prev_best_cad - price_cad
        savings_line = (
            f"\n<b>${diff:,.0f} CAD cheaper</b> than previous best "
            f"(was ${prev_best_cad:,.0f} CAD)"
        )

    return (
        f"<b>New Price Low -- {route['label']}</b>\n\n"
        f"Price:    <b>${price_cad:,.0f} CAD</b>  (${price_usd:,.0f} USD @ {fx_rate:.4f})\n"
        f"Airline:  {airline}\n"
        f"Date:     {date_fmt}\n"
        f"Stops:    {stops_str}\n"
        f"Layovers: {layover_str}\n"
        f"Duration: {duration}\n"
        f"Arrives:  {arrival}"
        f"{savings_line}\n\n"
        f'<a href="{gf_url}">View on Google Flights</a>'
    )


# ---------------------------------------------------------------------------
# Core: scrape -> store -> compare -> alert
# ---------------------------------------------------------------------------

def scrape_and_store(conn: sqlite3.Connection, fx_rate: float) -> None:
    dates    = get_sample_dates()
    now_iso  = datetime.utcnow().isoformat(timespec="seconds")
    run_rows: list = []

    for route in config.ROUTES:
        log.info("Scanning route %s  (%d dates)", route["id"], len(dates))

        for travel_date in dates:
            try:
                result = get_flights(
                    flight_data=[
                        FlightData(
                            date=travel_date,
                            from_airport=route["from"],
                            to_airport=route["to"],
                        )
                    ],
                    trip="one-way",
                    passengers=Passengers(adults=1),
                    seat="economy",
                )
            except Exception as exc:
                log.error("Scrape failed [%s %s]: %s", route["id"], travel_date, exc)
                time.sleep(2)
                continue

            for flight in result.flights:
                price_usd = parse_price_usd(flight.price)
                if price_usd is None:
                    continue

                layovers = ""  # fast-flights does not expose per-stop airport codes
                if not passes_layover_filter(layovers):
                    continue

                price_cad = round(price_usd * fx_rate, 2)
                arrival   = flight.arrival
                if flight.arrival_time_ahead:
                    arrival = f"{arrival} ({flight.arrival_time_ahead})"

                row = {
                    "route":       route["id"],
                    "travel_date": travel_date,
                    "airline":     flight.name,
                    "price_usd":   price_usd,
                    "price_cad":   price_cad,
                    "stops":       flight.stops if isinstance(flight.stops, int) else None,
                    "duration":    flight.duration,
                    "arrival":     arrival,
                    "layovers":    layovers,
                    "scraped_at":  now_iso,
                }
                conn.execute(
                    """
                    INSERT INTO price_history
                        (route, travel_date, airline, price_usd, price_cad,
                         stops, duration, arrival, layovers, scraped_at)
                    VALUES
                        (:route, :travel_date, :airline, :price_usd, :price_cad,
                         :stops, :duration, :arrival, :layovers, :scraped_at)
                    """,
                    row,
                )
                run_rows.append(row)
                log.info(
                    "  %s %s | %-28s | $%,.0f CAD | %s stop(s)",
                    route["id"],
                    travel_date,
                    flight.name[:28],
                    price_cad,
                    flight.stops,
                )

            conn.commit()
            sleep_secs = 2 + (abs(hash(route["id"] + travel_date)) % 2)  # 2 or 3 s
            time.sleep(sleep_secs)

    # ------------------------------------------------------------------
    # Find the best price per route+airline across all dates in this run
    # ------------------------------------------------------------------
    run_bests: dict = {}
    for row in run_rows:
        key = (row["route"], row["airline"])
        if key not in run_bests or row["price_cad"] < run_bests[key]["price_cad"]:
            run_bests[key] = row

    # ------------------------------------------------------------------
    # Compare against stored bests and alert when a new low is found
    # ------------------------------------------------------------------
    for (route_id, airline), best in run_bests.items():
        route_cfg = next(r for r in config.ROUTES if r["id"] == route_id)

        cur = conn.execute(
            "SELECT best_price_cad FROM best_prices WHERE route = ? AND airline = ?",
            (route_id, airline),
        ).fetchone()

        stored_best_cad: Optional[float] = cur[0] if cur else None
        new_price_cad = best["price_cad"]

        # Alert on first sighting (no stored best) or when >= threshold cheaper
        should_alert = stored_best_cad is None or (
            stored_best_cad - new_price_cad >= config.PRICE_ALERT_THRESHOLD_CAD
        )

        if not should_alert:
            log.info(
                "No alert for %s / %s: $%,.0f CAD (stored best: $%,.0f CAD, "
                "threshold: $%.0f CAD)",
                route_id,
                airline,
                new_price_cad,
                stored_best_cad,
                config.PRICE_ALERT_THRESHOLD_CAD,
            )
            continue

        log.info(
            "New low for %s / %s: $%,.0f CAD (prev: %s)",
            route_id,
            airline,
            new_price_cad,
            f"${stored_best_cad:,.0f}" if stored_best_cad else "none",
        )

        msg = build_alert(
            route=route_cfg,
            price_cad=new_price_cad,
            price_usd=best["price_usd"],
            travel_date=best["travel_date"],
            airline=airline,
            stops=best["stops"] if best["stops"] is not None else 0,
            duration=best["duration"] or "N/A",
            arrival=best["arrival"] or "N/A",
            layovers=best["layovers"],
            prev_best_cad=stored_best_cad,
            fx_rate=fx_rate,
        )
        send_telegram(msg)

        conn.execute(
            """
            INSERT INTO best_prices
                (route, airline, best_price_cad, best_price_usd,
                 travel_date, last_alert_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(route, airline) DO UPDATE SET
                best_price_cad = excluded.best_price_cad,
                best_price_usd = excluded.best_price_usd,
                travel_date    = excluded.travel_date,
                last_alert_at  = excluded.last_alert_at,
                updated_at     = excluded.updated_at
            """,
            (
                route_id,
                airline,
                new_price_cad,
                best["price_usd"],
                best["travel_date"],
                now_iso,
                now_iso,
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Flight tracker run started")
    conn = init_db(config.DB_PATH)
    fx_rate = fetch_fx_rate()
    try:
        scrape_and_store(conn, fx_rate)
    finally:
        conn.close()
    log.info("Flight tracker run complete")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
