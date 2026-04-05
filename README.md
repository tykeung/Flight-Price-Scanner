# Flight Price Tracker

Monitors two one-way routes for the lowest economy fares across Sep 1 - Oct 31 2026.
Scrapes Google Flights via the `fast-flights` library (no API key, no browser needed),
logs everything to SQLite, and sends Telegram alerts only when a new price low is hit
per airline.

**Routes monitored:**
- YYZ -> SYD (Toronto to Sydney)
- MEL -> YYZ (Melbourne to Toronto)

---

## Setup

### 1. Run the setup script

```bash
bash setup.sh
```

This installs dependencies and prints your cron line.

### 2. Create a Telegram bot

1. Open Telegram, search for **@BotFather**, send `/newbot`.
2. Copy the token BotFather gives you (format: `123456789:ABC...`).

### 3. Get your Telegram chat ID

```bash
curl -s 'https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates' | python3 -m json.tool
```

Send your bot a message first, then run the command above.
Find `"chat": {"id": <NUMBER>}` in the output.

### 4. Edit config.py

```python
TELEGRAM_BOT_TOKEN = "123456789:ABCDefGhIJK..."
TELEGRAM_CHAT_ID   = "987654321"
```

All other settings in `config.py` are optional but documented inline.

---

## Manual test run

```bash
python3 flight_tracker.py
```

Scrapes all 12 sample dates for both routes, stores results in `prices.db`,
and sends Telegram alerts for any new price lows found.

The first run establishes baselines -- alerts fire but with no "cheaper than" line.
Subsequent runs alert only when a price drops by at least $50 CAD below the stored best.

---

## Inspect results in the terminal

```bash
# All defaults: bests, top 10, trend chart for both routes
python3 view_prices.py

# Filter to one route
python3 view_prices.py --route YYZ_SYD

# Filter by airline
python3 view_prices.py --airline "Cathay Pacific"

# Show top 20 cheapest
python3 view_prices.py --top 20

# Combine filters
python3 view_prices.py --route MEL_YYZ --airline "Air Canada" --top 5
```

---

## Start the Telegram bot (background process)

The bot responds to `/prices` and `/history` commands in Telegram.

### Run in background with nohup

```bash
nohup python3 bot_listener.py >> tracker.log 2>&1 &
echo "Bot PID: $!"
```

Stop it later with:
```bash
kill <PID>
```

### Run in a tmux session (recommended for servers)

```bash
tmux new-session -d -s flightbot "python3 bot_listener.py"
tmux attach -t flightbot   # to inspect output
```

### Available bot commands

| Command | What it does |
|---------|--------------|
| `/prices` | All-time best price per airline for each route |
| `/history YYZ_SYD` | 10 cheapest prices ever seen for YYZ -> SYD |
| `/history MEL_YYZ` | 10 cheapest prices ever seen for MEL -> YYZ |
| `/help` | Command list |

---

## Add the cron schedule

Run `setup.sh` to print the exact line, then add it with `crontab -e`.

The tracker runs three times a day at **00:00, 12:00, and 18:00 UTC**.

Example cron line (your paths will differ):

```
0 0,12,18 * * * /usr/bin/python3 /Users/you/Flight-Price-Scanner/flight_tracker.py >> /Users/you/Flight-Price-Scanner/tracker.log 2>&1
```

---

## How to read the Telegram alerts

When a new price low is found for an airline, you receive a message like:

```
New Price Low -- Toronto (YYZ) -> Sydney (SYD)

Price:    $1,450 CAD  ($1,066 USD @ 1.3600)
Airline:  Cathay Pacific
Date:     Sep 15, 2026
Stops:    1 stop
Layovers: unknown (not available from data source)
Duration: 17h 30m
Arrives:  11:00 PM (+1)

$130 CAD cheaper than previous best (was $1,580 CAD)

View on Google Flights  [link]
```

---

## Known limitations

### Layover detection

`fast-flights` returns airline name, duration, stop count, and price -- but **not
the individual layover airport codes**.  The layover filter (HKG, SFO, LAX, YVR,
NRT, HND) is implemented and ready to use, but because the data is unavailable,
all flights are currently included rather than filtered.  The Telegram alert shows
"unknown (not available from data source)" for layover cities.

### Price currency

Google Flights returns prices in **USD**.  The tracker fetches a live exchange rate
from [frankfurter.app](https://api.frankfurter.app) and converts to CAD.  If the
fetch fails, a hardcoded fallback rate of 1.36 is used.  Converted prices are
approximate and should be verified on Google Flights before booking.

### fast-flights breakage

`fast-flights` reverse-engineers Google Flights' internal protobuf format.  If
Google changes its page structure or request format, scrapes may start returning
zero results or raising exceptions.  Check `tracker.log` if no alerts arrive over
several days.  Update the library with `pip3 install --upgrade fast-flights`.

### Prices not guaranteed

Prices fluctuate constantly.  A low price seen by the scraper may no longer be
available by the time you check.  Always confirm the price on Google Flights.

---

## File overview

| File | Purpose |
|------|---------|
| `config.py` | All user-editable settings |
| `flight_tracker.py` | Main script: scrape, store, compare, alert |
| `view_prices.py` | CLI viewer for stored data |
| `bot_listener.py` | Telegram bot (long polling) |
| `setup.sh` | Dependency installer + instructions |
| `prices.db` | SQLite database (created on first run) |
| `tracker.log` | Combined log file |
