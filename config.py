import os
from typing import List

# Admin password for admin panel
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# Server config
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 10000))

# Thumbnails directory
THUMBNAILS_DIR = "static/thumbnails"