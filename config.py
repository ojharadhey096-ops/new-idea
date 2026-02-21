import os
from typing import List

# Telegram API credentials (set via environment variables)
API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # Optional, for bot if needed

# Channels/Groups to monitor (comma-separated in env)
CHANNELS = os.environ.get("CHANNELS", "@Rk_Movie096").split(",") if os.environ.get("CHANNELS") else []

# Admin password for admin panel
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# Server config
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 10000))

# Sync interval in seconds (how often to check for new videos)
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", 3600))  # Default 1 hour

# JSON cache file
VIDEO_CACHE_FILE = "video_cache.json"

# Thumbnails directory
THUMBNAILS_DIR = "static/thumbnails"

# Session file for Telegram client
SESSION_FILE = "telegram_session"