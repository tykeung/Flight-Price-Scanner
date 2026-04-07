# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the scripts

```bash
# Scrape prices, store to DB, send Telegram alerts
python3 flight_tracker.py

# Inspect stored data in the terminal
python3 view_prices.py
python3 view_prices.py --route YYZ_SYD
python3 view_prices.py --airline "Cathay Pacific"
python3 view_prices.py --top 20

# Start the Telegram bot (long-polling, run in background)
python3 bot_listener.py

# First-time setup
bash setup.sh
```

## Architecture

All user-editable settings live in `config.py` — routes, date window, alert threshold, DB path. Every other script imports this module; change behaviour here, not scattered across files.

**`flight_tracker.py`** is the main scheduled script. Flow:
1. Fetch live USD→CAD rate from `frankfurter.app` (falls back to `FX_FALLBACK_RATE`)
2. Generate `DATES_PER_RUN` evenly-spaced dates across the configured window
3. For each route × date, call `fast_flights.get_flights()` and write every result to `price_history`
4. After all scraping, find the lowest price per `(route, airline)` for this run
5. Compare against `best_prices` table; alert via Telegram and update stored best only when the drop meets `PRICE_ALERT_THRESHOLD_CAD`

**`bot_listener.py`** is a separate long-polling process. It shares the same SQLite file as the tracker and responds to `/prices` and `/history <ROUTE_ID>` commands.

**`view_prices.py`** reads only — never writes to the DB.

## Database (prices.db)

Two tables:
- `price_history` — every scraped row ever (route, travel_date, airline, price_usd, price_cad, stops, duration, arrival, layovers, scraped_at)
- `best_prices` — one row per `(route, airline)` with the all-time lowest price; updated only when an alert fires

```bash
sqlite3 prices.db "SELECT * FROM best_prices;"
sqlite3 prices.db "SELECT * FROM price_history LIMIT 20;"
```

## Credentials

Telegram bot token is read from the macOS Keychain at import time:
```
service: TELEGRAM_BOT_TOKEN  account: openclaw
```
Never hardcode the token. `TELEGRAM_CHAT_ID` is set directly in `config.py`.

## Known limitation: layover filtering

`fast-flights` does not expose per-stop airport codes — only airline name, stop count, duration, and price. The `LAYOVER_AIRPORTS` filter in `config.py` and `passes_layover_filter()` in `flight_tracker.py` are implemented but currently have no data to act on, so all flights pass through. The `layovers` column in `price_history` is always an empty string.

## Dependencies

```bash
pip3 install fast-flights
```
No other third-party libraries. All HTTP calls use `urllib` from the standard library.
