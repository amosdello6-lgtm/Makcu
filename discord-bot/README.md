# Discord Bot

A modular, fully configurable Discord bot. Moderation, welcome system,
XP/leveling, and per-server configuration — all driven by slash commands,
with every setting stored per server so one running bot can serve many
communities with different configs.

## Features

**Moderation**
- `/warn` — warn a member, with a stored warning history
- `/warnings` — view a member's warning history
- `/clearwarns` — wipe a member's warnings
- `/timeout` · `/untimeout` — Discord-native timeouts, 1 minute to 28 days
- `/kick` · `/ban` · `/unban` — with DM notification before action
- `/purge` — bulk delete up to 100 messages, optionally filtered to one member
- Every action logs to a configurable channel with a full audit embed
- Role-hierarchy safety on every command (can't action someone above you, or above the bot)

**Welcome system**
- Custom welcome embeds with `{user}` `{username}` `{server}` `{count}` placeholders
- Goodbye messages
- Auto-role on join, with a hierarchy check so it can't silently fail

**Levels & XP**
- XP per message with an anti-spam cooldown
- `/rank` — level, server rank, and a progress bar to the next level
- `/leaderboard` — top 10 with medals
- Level-up announcements in a channel of your choice
- Toggleable per server

**Support tickets**
- `/ticket-panel` — post a panel with an "Open a ticket" button
- Members get a private channel only they and staff can see
- `/ticket-add` — pull another member into a ticket
- Close button, with a summary posted to a ticket log channel
- Limit of 3 open tickets per member so nobody floods you
- Buttons are persistent — they survive bot restarts and redeploys

**Self-assignable roles**
- `/rolemenu create` — post a role menu
- `/rolemenu add` — attach a role button to it (up to 25)
- Click to get a role, click again to remove it
- Rejects roles above the bot, `@everyone`, and integration-managed roles
- Validates that a clicked role was actually published — a forged button
  can't grant arbitrary roles

**Auto-moderation**
- `/automod invites` — delete Discord invite links
- `/automod links` — delete all URLs
- `/automod mentions` — delete messages with 5+ mentions
- `/automod block-word` · `unblock-word` · `words` — custom word blocklist
- `/automod status` — see what's on
- Word matching uses word boundaries, so "assistant" doesn't trip a block on "ass"
- Staff with Manage Messages always bypass every filter
- Everything off by default

**Event logging**
- `/logging toggle` — per-event-type on/off
- `/logging all` · `/logging status`
- Logs deleted messages, edited messages (before/after), joins, leaves, role changes
- Flags accounts less than 7 days old on join — the classic raid signal

**General**
- `/help` — builds itself from registered commands, so it never goes stale
- `/serverinfo` · `/userinfo` · `/avatar` · `/ping`

**Configuration**
- `/config view` — every current setting at a glance
- `/config welcome-channel` · `goodbye-channel` · `log-channel` · `levelup-channel`
- `/config autorole` · `welcome-message` · `leveling`
- `/config ticket-category` · `ticket-staff` · `ticket-log`
- Admin-only, and hidden from members who can't use them

---

## Setup

### 1. Create the bot application

1. Go to https://discord.com/developers/applications → **New Application**
2. **Bot** tab → **Reset Token** → copy the token (you only see it once)
3. On the same page, scroll to **Privileged Gateway Intents** and enable:
   - **SERVER MEMBERS INTENT** (needed for join/leave events)
   - **MESSAGE CONTENT INTENT** (needed to award XP for messages)

   The bot will refuse to start without these.

### 2. Invite it to your server

**OAuth2 → URL Generator**, tick:
- Scopes: `bot`, `applications.commands`
- Bot permissions: `Manage Roles`, `Kick Members`, `Ban Members`,
  `Moderate Members`, `Manage Messages`, `Read Messages/View Channels`,
  `Send Messages`, `Embed Links`

Open the generated URL and pick your server.

> **Important:** in Server Settings → Roles, drag the bot's role **above**
> any role it needs to assign or any member it needs to moderate.
> Discord won't let a bot act on anyone at or above its own top role.

### 3. Run it locally

```bash
pip install -r requirements.txt
copy .env.example .env        # Windows   (cp on Mac/Linux)
```

Open `.env` and paste your token. Set `DEV_GUILD_ID` to your test
server's ID too — slash commands then appear instantly instead of taking
up to an hour.

```bash
python bot.py
```

You should see each cog load, then `logged in as ...`.

---

## Hosting it 24/7

A Discord bot has to stay running. Here are the real options as of 2026 —
note that **Render's free tier sleeps after 15 minutes**, which takes the
bot offline, so it is not usable for this.

### Option A — Railway (easiest)

Railway gives ~$5/month in free credits, and a small bot costs roughly
$2–3/month to run, so it fits. No sleeping, deploys straight from GitHub.

1. Push this folder to a GitHub repo
2. railway.app → **New Project** → **Deploy from GitHub repo**
3. If the bot is in a subfolder, set **Root Directory** to `discord-bot`
4. **Variables** → add `DISCORD_TOKEN` with your token
5. Railway reads the `Procfile` and runs it as a worker

Note: Railway asks for a card to verify (it won't charge within the free
credits), so you'll need a parent's help if you're under 18.

### Option B — Oracle Cloud Always Free (genuinely free forever)

Oracle's free tier gives 4 ARM cores and 24 GB RAM permanently — enough
to run dozens of bots. More setup, but it never expires and never costs.

1. Sign up at oracle.com/cloud/free (card needed for identity check, not charged)
2. Create an **Ampere A1** compute instance running Ubuntu
3. SSH in, then:

```bash
sudo apt update && sudo apt install -y python3-pip git
git clone <your repo url> && cd <repo>/discord-bot
pip3 install -r requirements.txt
nano .env        # paste your token
```

4. Keep it running after you disconnect with systemd:

```bash
sudo nano /etc/systemd/system/discordbot.service
```

```ini
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/<repo>/discord-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now discordbot
sudo systemctl status discordbot      # check it's running
journalctl -u discordbot -f           # live logs
```

`Restart=always` means it comes back automatically after a crash or reboot.

### Option C — Fly.io

3 free shared VMs with 256 MB RAM. Plenty for a bot, but needs a
Dockerfile, so it's the fiddliest of the three.

---

## Adding a feature

This is the part that matters if you're selling the bot and a customer
asks for something extra.

**1. Drop a new file into `cogs/`:**

```python
# cogs/mything.py
from discord import app_commands
from discord.ext import commands

class MyThing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mything", description="Does a thing")
    async def mything(self, interaction):
        await interaction.response.send_message("it works")

async def setup(bot):
    await bot.add_cog(MyThing(bot))
```

Restart the bot. It loads automatically — `bot.py` scans the folder, so
you never edit it to add a feature.

**2. If the feature needs a configurable setting:**

- Add the key to `KNOWN_SETTINGS` in `cogs/settings.py`
- Add a `/config` command for it there
- Read it anywhere with `await self.bot.db.get_setting(guild_id, "my_key")`

No database migration needed — settings are a generic key/value table
keyed by guild, which is exactly what makes "can it also do X?" a
ten-minute job instead of a rewrite.

---

## Project layout

```
discord-bot/
├── bot.py              entry point — loads cogs, syncs commands, logs in
├── core/
│   ├── config.py       env vars, colours, tunables
│   └── database.py     SQLite: per-guild settings, warns, XP
├── cogs/               one file per feature — add files here
│   ├── general.py      help, ping, serverinfo, userinfo, avatar
│   ├── moderation.py   warn, kick, ban, timeout, purge + audit logging
│   ├── automod.py      invite/link/mention filters, word blocklist
│   ├── welcome.py      join/leave messages, auto-role
│   ├── leveling.py     XP, /rank, /leaderboard
│   ├── tickets.py      ticket panel, private channels, close button
│   ├── rolemenu.py     self-assignable role buttons
│   ├── serverlog.py    delete/edit/join/leave/role-change logging
│   └── settings.py     /config commands
├── Procfile            tells Railway/Heroku how to start it
└── requirements.txt
```

## Troubleshooting

**Slash commands don't appear** — set `DEV_GUILD_ID` in `.env` for instant
syncing. Global commands can take up to an hour on first registration.

**`PrivilegedIntentsRequired` on startup** — you didn't tick SERVER
MEMBERS and MESSAGE CONTENT in the Developer Portal. Go back to step 1.

**Bot can't assign a role / can't ban someone** — the bot's role is below
the target's. Drag it higher in Server Settings → Roles.

**Nothing happens on join** — you haven't run `/config welcome-channel`
yet. Features stay silent until configured, on purpose.
