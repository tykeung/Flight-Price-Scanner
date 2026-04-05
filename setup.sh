#!/usr/bin/env bash
# setup.sh  --  First-time setup for the Flight Price Tracker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"

echo ""
echo "============================================================"
echo "  Flight Price Tracker -- Setup"
echo "============================================================"
echo ""

# ----------------------------------------------------------------
# 1. Install Python dependencies
# ----------------------------------------------------------------
echo "[1/4] Installing Python dependencies..."
pip3 install fast-flights requests
echo "      Done."
echo ""

# ----------------------------------------------------------------
# 2. Verify paths
# ----------------------------------------------------------------
echo "[2/4] Paths"
echo "      Scripts:   $SCRIPT_DIR"
echo "      Database:  $SCRIPT_DIR/prices.db  (created on first run)"
echo "      Log file:  $SCRIPT_DIR/tracker.log"
echo ""

# ----------------------------------------------------------------
# 3. Telegram setup instructions
# ----------------------------------------------------------------
echo "[3/4] Setting up Telegram"
echo ""
echo "  Step A -- Create a bot"
echo "    1. Open Telegram and search for @BotFather"
echo "    2. Send:  /newbot"
echo "    3. Follow the prompts; BotFather gives you a token like:"
echo "         123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ"
echo "    4. Open config.py and set TELEGRAM_BOT_TOKEN to that value."
echo ""
echo "  Step B -- Get your chat ID"
echo "    1. Send any message to your new bot in Telegram."
echo "    2. Run this command (replace <TOKEN> with your actual token):"
echo ""
echo "       curl -s 'https://api.telegram.org/bot<TOKEN>/getUpdates' | python3 -m json.tool"
echo ""
echo "    3. In the JSON output, find  \"chat\": {\"id\": <NUMBER>}"
echo "    4. Copy that number and set TELEGRAM_CHAT_ID in config.py."
echo ""

# ----------------------------------------------------------------
# 4. Crontab line
# ----------------------------------------------------------------
echo "[4/4] Cron schedule  (00:00, 12:00, 18:00 UTC every day)"
echo ""
echo "  Run  crontab -e  and add this line:"
echo ""
echo "  0 0,12,18 * * * $PYTHON $SCRIPT_DIR/flight_tracker.py >> $SCRIPT_DIR/tracker.log 2>&1"
echo ""

echo "============================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1) Edit config.py  -- add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
echo "  2) python3 flight_tracker.py     -- first run / manual test"
echo "  3) python3 view_prices.py        -- inspect results in terminal"
echo "  4) python3 bot_listener.py &     -- start Telegram bot in background"
echo "  5) crontab -e                    -- add the cron line printed above"
echo "============================================================"
echo ""
