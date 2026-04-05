# =============================================================================
# config.py  --  Edit these values before first run
# =============================================================================

# Telegram credentials  (required for alerts and bot commands)
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID   = "YOUR_CHAT_ID_HERE"

# Routes to monitor
ROUTES = [
    {
        "id":    "YYZ_SYD",
        "from":  "YYZ",
        "to":    "SYD",
        "label": "Toronto (YYZ) -> Sydney (SYD)",
    },
    {
        "id":    "MEL_YYZ",
        "from":  "MEL",
        "to":    "YYZ",
        "label": "Melbourne (MEL) -> Toronto (YYZ)",
    },
]

# Layover airports considered acceptable.
# NOTE: fast-flights does not expose individual layover airport codes in its
# response, so this filter currently cannot be applied automatically.  Flights
# are always included (per spec: "include if layover can't be determined").
# When/if the library exposes layover data this set will be used automatically.
LAYOVER_AIRPORTS = {"HKG", "SFO", "LAX", "YVR", "NRT", "HND"}

# Date window to scan
DATE_START    = "2026-09-01"
DATE_END      = "2026-10-31"
DATES_PER_RUN = 12          # evenly spread across the window each run

# Alert only when the new price is at least this many CAD below the stored best
PRICE_ALERT_THRESHOLD_CAD = 50.0

# Fallback USD -> CAD rate when the live FX fetch from frankfurter.app fails
FX_FALLBACK_RATE = 1.36

# File paths
DB_PATH  = "prices.db"
LOG_FILE = "tracker.log"
