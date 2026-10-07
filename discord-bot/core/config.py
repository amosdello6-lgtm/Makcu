"""Loads configuration from the environment.

Secrets live in a `.env` file that is never committed. Everything that
isn't a secret (colours, limits, defaults) lives here as a plain constant
so a buyer can change the bot's look without touching feature code.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db")

# When set, slash commands sync instantly to this one server instead of
# taking up to an hour to propagate globally. Use it while developing.
_dev_guild = os.getenv("DEV_GUILD_ID", "").strip()
DEV_GUILD_ID = int(_dev_guild) if _dev_guild.isdigit() else None

# ---------------------------------------------------------------------
# Branding — change these to re-skin the bot for a different customer.
# ---------------------------------------------------------------------

COLOR_PRIMARY = 0x5865F2   # Discord blurple
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_DANGER = 0xED4245

EMBED_FOOTER = "Powered by your bot"

# ---------------------------------------------------------------------
# Leveling defaults — per-guild overrides live in the database.
# ---------------------------------------------------------------------

XP_PER_MESSAGE_MIN = 15
XP_PER_MESSAGE_MAX = 25
XP_COOLDOWN_SECONDS = 60


def require_token() -> str:
    """Fail loudly at startup instead of mysteriously at login."""
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set.\n"
            "Copy .env.example to .env and paste your bot token into it."
        )
    return TOKEN
