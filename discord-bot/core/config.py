from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db")

# Syncs slash commands to one guild instantly instead of waiting on the
# global propagation delay. Development only.
_dev_guild = os.getenv("DEV_GUILD_ID", "").strip()
DEV_GUILD_ID = int(_dev_guild) if _dev_guild.isdigit() else None

# Branding
COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_DANGER = 0xED4245

EMBED_FOOTER = "Powered by your bot"

# Leveling
XP_PER_MESSAGE_MIN = 15
XP_PER_MESSAGE_MAX = 25
XP_COOLDOWN_SECONDS = 60


def require_token() -> str:
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set.\n"
            "Copy .env.example to .env and paste your bot token into it."
        )
    return TOKEN
