# Discord Bot

A modular Discord bot with moderation, tickets, auto-moderation, leveling,
self-assignable roles, welcome messages and event logging.

Everything is configured per server through slash commands, so one running
instance serves many servers with completely independent settings. No code
changes needed to deploy it somewhere new.

**45 slash commands across 9 feature modules.**

---

## Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Setup](#setup) — creating the bot, inviting it, first run
4. [Configuring it](#configuring-it) — every setting explained
5. [Hosting it 24/7](#hosting-it-247) — Railway, Oracle Cloud, Fly.io
6. [Updating](#updating)
7. [Adding your own features](#adding-your-own-features)
8. [Command reference](#command-reference)
9. [Troubleshooting](#troubleshooting)

---

## Features

### Moderation
Warnings with persistent history, kick, ban, unban, Discord-native timeouts,
and bulk message deletion. Every action is logged to a channel you choose
with a full audit embed, and the target is DMed the reason before the action
lands.

Role hierarchy is enforced on every command: nobody can action a member at
or above their own highest role, nobody can action the server owner, and the
bot refuses to act on anyone above itself.

### Support tickets
Post a panel; members click a button and get a private channel visible only
to them and your staff role. Staff can pull other members in. Closing posts
a summary to a log channel and deletes the channel. Limited to 3 open
tickets per member.

Panel buttons are persistent, so they keep working across restarts and
redeploys.

### Auto-moderation
Optional filters for Discord invites, URLs, mass mentions, and a custom word
blocklist. Word matching respects word boundaries, so blocking `ass` does not
match `assistant`. Anyone with Manage Messages bypasses every filter.

All filters are off until you turn them on.

### Channel clearing
`/clear` wipes a channel's entire history, not just the last 100 messages.
It works by replacing the channel with an identical empty copy, which keeps
the name, permissions, topic, slowmode and position. A confirmation button
is required, and any stored settings pointing at that channel are updated
automatically.

`/autoclear` does the same on a schedule — hourly, daily, weekly, or any
interval up to 30 days — per channel.

### Levels and XP
Members earn randomised XP per message with a 60-second cooldown to stop
spam farming. `/rank` shows level, server position and a progress bar;
`/leaderboard` shows the top 10. Level-up announcements can go to the
current channel or a dedicated one.

### Self-assignable roles
Build button menus members click to give themselves roles. Up to 25 buttons
per menu. Rejects `@everyone`, integration-managed roles, and anything above
the bot in the hierarchy.

### Welcome system
Customisable welcome and goodbye messages with `{user}`, `{username}`,
`{server}` and `{count}` placeholders, plus an auto-role granted on join.

### Event logging
Deleted messages (with content), edited messages (before and after), joins,
leaves and role changes. Each type toggles independently. Accounts younger
than 7 days are flagged on join.

### General
A `/help` that builds itself from the registered commands so it can never go
stale, plus `/serverinfo`, `/userinfo`, `/avatar` and `/ping`.

---

## Requirements

- Python 3.9 or newer (3.11+ recommended)
- A Discord account

That's it. Dependencies are `discord.py`, `aiosqlite` and `python-dotenv`.

---

## Setup

### 1. Create the application

1. Go to <https://discord.com/developers/applications>
2. **New Application**, give it a name, **Create**
3. Open the **Bot** tab in the left sidebar
4. **Reset Token**, then **Copy**. You only see this once — paste it
   somewhere safe for a minute.

### 2. Enable the privileged intents

Still on the **Bot** page, scroll down to **Privileged Gateway Intents** and
switch on:

- **Server Members Intent** — needed for join/leave events, welcome
  messages, auto-role and member logging
- **Message Content Intent** — needed for XP and automod

Leave **Presence Intent** off. Click **Save Changes** if a prompt appears.

The bot will not start without these two. The error is
`PrivilegedIntentsRequired`.

### 3. Invite it to your server

Go to **OAuth2 → URL Generator** and tick:

**Scopes**
- `bot`
- `applications.commands` ← easy to miss, and slash commands won't register without it

**Bot Permissions**
- Manage Roles
- Manage Channels
- Kick Members
- Ban Members
- Moderate Members
- Manage Messages
- View Channels
- Send Messages
- Embed Links
- Read Message History

Copy the URL at the bottom and open it, then pick your server.

> **Then do this:** open **Server Settings → Roles** and drag the bot's role
> **above** every role it needs to manage. Discord will not let a bot assign
> a role, or moderate a member, at or above its own highest role. This is the
> single most common reason a correctly-configured bot "doesn't work".

### 4. Install and configure

```bash
pip install -r requirements.txt
```

Copy the example environment file:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` in a text editor and fill it in:

```ini
DISCORD_TOKEN=your_token_from_step_1
DEV_GUILD_ID=your_server_id
DATABASE_PATH=data/bot.db
```

**Getting your server ID:** in Discord, go to **Settings → Advanced** and
turn on **Developer Mode**. Then right-click your server's icon and choose
**Copy Server ID**.

`DEV_GUILD_ID` is optional but recommended while setting up. With it, slash
commands appear instantly in that one server. Without it, they're registered
globally and can take up to an hour to show up. Leave it blank for
production.

> **On Windows, do not rename `.env.example` in File Explorer.** Explorer
> silently re-appends the extension and you end up with `.env.env`, which
> the bot can't find. Use the `copy` command above, or rename from a
> terminal with `Rename-Item`.

### 5. Run it

```bash
python bot.py
```

A successful start looks like:

```
12:47:15  INFO  bot: database ready at data/bot.db
12:47:15  INFO  bot: loaded cogs.automod
12:47:15  INFO  bot: loaded cogs.general
12:47:15  INFO  bot: loaded cogs.leveling
12:47:15  INFO  bot: loaded cogs.moderation
12:47:15  INFO  bot: loaded cogs.rolemenu
12:47:15  INFO  bot: loaded cogs.serverlog
12:47:15  INFO  bot: loaded cogs.settings
12:47:15  INFO  bot: loaded cogs.tickets
12:47:15  INFO  bot: loaded cogs.welcome
12:47:15  INFO  bot: persistent views registered
12:47:15  INFO  bot: synced 45 commands to dev guild ...
12:47:16  INFO  bot: logged in as YourBot#1234
12:47:16  INFO  bot: serving 1 guild(s)
```

Two warnings about `PyNaCl` and `davey` are normal — they relate to voice
support, which this bot doesn't use.

Now type `/help` in your server.

---

## Configuring it

Nothing is enabled until you configure it. This is deliberate — a bot that
starts posting the moment it joins gets removed.

Run `/config view` at any time to see every current setting.

### Welcome messages

```
/config welcome-channel #welcome
/config welcome-message Welcome {user} to {server}! You're member #{count}
/config goodbye-channel #welcome
/config autorole @Member
```

Placeholders available in the welcome message:

| Placeholder  | Becomes                          |
|--------------|----------------------------------|
| `{user}`     | A mention, e.g. @Amos            |
| `{username}` | Display name without the mention |
| `{server}`   | Server name                      |
| `{count}`    | Current member count             |

Run `/config welcome-message` with no text to reset to the default.

### Moderation logging

```
/config log-channel #mod-logs
```

Every warn, kick, ban and timeout now posts an audit embed there. Automod
deletions go here too.

### Tickets

```
/config ticket-staff @Support
/config ticket-category Tickets
/config ticket-log #ticket-logs
/ticket-panel
```

`/ticket-panel` accepts optional `title`, `message` and `channel` arguments
if you want to customise the panel.

### Levels

```
/config leveling true
/config levelup-channel #general
```

Leave `levelup-channel` unset to announce in whichever channel the member
levelled up in.

### Auto-moderation

```
/automod invites true
/automod links true
/automod mentions true
/automod block-word somebadword
/automod status
```

### Event logging

```
/config log-channel #server-logs
/logging all true
```

Or enable types individually:

```
/logging toggle event:Deleted messages enabled:true
/logging toggle event:Role changes enabled:false
/logging status
```

### Self-assignable roles

```
/rolemenu create title:Pick your roles
```

It replies with a message ID. Use it to attach roles:

```
/rolemenu add message_id:123456789 role:@Gamer
/rolemenu add message_id:123456789 role:@Artist
```

---

## Hosting it 24/7

The bot has to stay running to work. Closing your terminal stops it.

> **New to this?** [HOSTING.md](HOSTING.md) is a step-by-step walkthrough
> that assumes no prior experience. The summary below is for people who
> already know their way around a server.

> **Render's free tier is not suitable.** Free web services sleep after 15
> minutes of inactivity, which disconnects the bot. Ignore guides that
> recommend it.

### Option A: Railway — easiest

Railway gives roughly $5/month in free credits and a small bot uses about
$2–3/month. No sleeping, and it deploys straight from GitHub.

1. Push this folder to a GitHub repository
2. At <https://railway.app>, choose **New Project → Deploy from GitHub repo**
3. If the bot lives in a subfolder, set **Root Directory** to that folder
4. Under **Variables**, add `DISCORD_TOKEN` with your token
5. Leave `DEV_GUILD_ID` unset in production

Railway reads the included `Procfile` and runs the bot as a worker.

### Option B: Oracle Cloud Always Free — free permanently

Oracle's free tier includes 4 ARM cores and 24 GB RAM with no expiry, which
runs this bot many times over. More setup, but it never costs anything.

1. Sign up at <https://www.oracle.com/cloud/free/>
2. Create an **Ampere A1** compute instance running Ubuntu
3. SSH in and set up:

```bash
sudo apt update && sudo apt install -y python3-pip git
git clone <your-repo-url>
cd <repo>/discord-bot
pip3 install -r requirements.txt
nano .env     # paste your token
```

4. Create a systemd service so it survives reboots and crashes:

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
sudo systemctl status discordbot    # check it started
journalctl -u discordbot -f         # follow the logs
```

Useful afterwards:

```bash
sudo systemctl restart discordbot   # after pulling an update
sudo systemctl stop discordbot
```

### Option C: Fly.io

Three free shared VMs with 256 MB RAM each, which is plenty. Requires
writing a Dockerfile, so it's the most involved of the three.

---

## Updating

### If you cloned from git

```bash
git pull
pip install -r requirements.txt
```

Then restart the bot. On a systemd host:

```bash
sudo systemctl restart discordbot
```

Your `.env` and the `data/` folder are both gitignored, so **your token and
your database survive updates**. Nothing is reset.

### Database changes

New tables and columns are created automatically on startup — the schema
uses `CREATE TABLE IF NOT EXISTS`, so updating never destroys existing data.

### Backing up

The entire bot state is one file:

```bash
cp data/bot.db data/bot.db.backup
```

Do this before any update you're unsure about.

---

## Adding your own features

Features live in `cogs/`. The bot scans that folder at startup, so adding
one means adding a file — you never edit `bot.py`.

### A new command

Create `cogs/example.py`:

```python
import discord
from discord import app_commands
from discord.ext import commands


class Example(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="hello", description="Say hello")
    async def hello(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Hello.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Example(bot))
```

Restart the bot. `/hello` now exists, and `/help` picks it up automatically.

### A new configurable setting

Three steps:

1. Add the key and a label to `KNOWN_SETTINGS` in `cogs/settings.py` so it
   shows in `/config view`
2. Add a `/config` command for it in the same file
3. Read it wherever you need it:

```python
value = await self.bot.db.get_setting(guild_id, "my_key")
channel_id = await self.bot.db.get_int_setting(guild_id, "my_channel")
```

No database migration is required. Settings are stored as rows in a generic
key/value table keyed by guild, so new options cost nothing.

### A new table

Add the `CREATE TABLE IF NOT EXISTS` statement to `SCHEMA` in
`core/database.py` and add methods alongside the existing ones. It is
created on next startup.

### Re-skinning for a different customer

Open `core/config.py`. Embed colours and the footer text are constants
there, separate from any feature code.

---

## Command reference

### General
| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/ping` | Check responsiveness |
| `/serverinfo` | Server statistics |
| `/userinfo [member]` | Member information |
| `/avatar [member]` | Full-size avatar |

### Moderation
| Command | Permission | Description |
|---|---|---|
| `/warn <member> [reason]` | Moderate Members | Warn and record |
| `/warnings <member>` | Moderate Members | View warning history |
| `/clearwarns <member>` | Manage Server | Delete all warnings |
| `/timeout <member> <minutes> [reason]` | Moderate Members | Timeout, 1–40320 min |
| `/untimeout <member>` | Moderate Members | Lift a timeout |
| `/kick <member> [reason]` | Kick Members | Kick |
| `/ban <member> [reason] [delete_days]` | Ban Members | Ban |
| `/unban <user_id>` | Ban Members | Unban by ID |
| `/purge <amount> [member]` | Manage Messages | Bulk delete, max 100 |

### Channel clearing
| Command | Permission | Description |
|---|---|---|
| `/clear [channel]` | Manage Channels | Delete the channel's entire history |
| `/autoclear set <channel> <hours>` | Manage Channels | Clear on a schedule |
| `/autoclear remove <channel>` | Manage Channels | Stop the schedule |
| `/autoclear list` | Manage Channels | Show scheduled clears and next run |

### Levels
| Command | Description |
|---|---|
| `/rank [member]` | Level, rank and progress |
| `/leaderboard` | Top 10 by XP |

### Tickets
| Command | Permission | Description |
|---|---|---|
| `/ticket-panel [channel] [title] [message]` | Manage Server | Post the panel |
| `/ticket-add <member>` | Manage Channels | Add someone to a ticket |

### Roles
| Command | Permission | Description |
|---|---|---|
| `/rolemenu create [title] [message] [channel]` | Manage Roles | Post a menu |
| `/rolemenu add <message_id> <role> [label]` | Manage Roles | Add a button |

### Auto-moderation
All require Manage Server.

| Command | Description |
|---|---|
| `/automod invites <bool>` | Block Discord invites |
| `/automod links <bool>` | Block all URLs |
| `/automod mentions <bool>` | Block 5+ mentions |
| `/automod block-word <word>` | Add to blocklist |
| `/automod unblock-word <word>` | Remove from blocklist |
| `/automod words` | Show the blocklist |
| `/automod status` | Show active filters |

### Logging
All require Manage Server.

| Command | Description |
|---|---|
| `/logging toggle <event> <bool>` | Toggle one event type |
| `/logging all <bool>` | Toggle everything |
| `/logging status` | Show what's enabled |

### Configuration
All require Manage Server.

| Command | Description |
|---|---|
| `/config view` | Show all settings |
| `/config welcome-channel [channel]` | Welcome messages |
| `/config welcome-message [text]` | Custom welcome text |
| `/config goodbye-channel [channel]` | Goodbye messages |
| `/config autorole [role]` | Role granted on join |
| `/config log-channel [channel]` | Moderation and automod log |
| `/config levelup-channel [channel]` | Level-up announcements |
| `/config leveling <bool>` | Enable the XP system |
| `/config ticket-category [category]` | Where tickets are created |
| `/config ticket-staff [role]` | Role that sees all tickets |
| `/config ticket-log [channel]` | Closed-ticket summaries |

Omitting the optional argument clears that setting.

---

## Project layout

```
discord-bot/
├── bot.py              entry point: loads cogs, registers views, syncs, logs in
├── core/
│   ├── config.py       env vars, colours, tunables
│   └── database.py     SQLite: settings, warns, XP, tickets, role menus
├── cogs/               one file per feature
│   ├── general.py      help, ping, serverinfo, userinfo, avatar
│   ├── moderation.py   warn, kick, ban, timeout, purge, audit logging
│   ├── automod.py      invite/link/mention filters, word blocklist
│   ├── cleanup.py      /clear and scheduled auto-clearing
│   ├── welcome.py      join and leave messages, auto-role
│   ├── leveling.py     XP, rank, leaderboard
│   ├── tickets.py      ticket panel, private channels, close flow
│   ├── rolemenu.py     self-assignable role buttons
│   ├── serverlog.py    delete/edit/join/leave/role-change logging
│   └── settings.py     /config commands
├── data/               SQLite database (created at runtime, gitignored)
├── .env                your token (gitignored, never commit)
├── Procfile            start command for Railway and similar
└── requirements.txt
```

---

## Troubleshooting

**`DISCORD_TOKEN is not set`**
The bot can't find a token. Check that the file is named exactly `.env` and
not `.env.txt` or `.env.env`. On Windows, `Get-ChildItem -Force` shows real
filenames. Also confirm you're running `python bot.py` from inside the
`discord-bot` folder.

**`PrivilegedIntentsRequired`**
Server Members Intent and Message Content Intent aren't enabled. See
[step 2](#2-enable-the-privileged-intents).

**`403 Forbidden (error code: 50001): Missing Access` on startup**
The bot isn't in the server named by `DEV_GUILD_ID`, or was invited without
the `applications.commands` scope. Re-invite it using a URL that includes
both scopes. The bot logs a ready-made invite link when this happens and
falls back to a global sync rather than crashing.

**Slash commands don't appear**
Set `DEV_GUILD_ID` for instant syncing. Globally-registered commands can take
up to an hour the first time. Also check the bot was invited with the
`applications.commands` scope.

**"I can't assign that role" / "they're above me in the role list"**
The bot's role sits below the role or member it's trying to act on. Move it
up in **Server Settings → Roles**.

**Welcome messages / logging / automod do nothing**
They're unconfigured. Run `/config view` to see what's set. Every feature
stays silent until you point it at a channel.

**Nothing happens when I click a ticket or role button**
If the bot was restarted, confirm `persistent views registered` appears in
the startup log. If a role button says the role isn't available, the menu
entry was removed from the database — re-add it with `/rolemenu add`.

**XP isn't being awarded**
Check `/config view` shows leveling as on, that Message Content Intent is
enabled, and remember the 60-second per-member cooldown.

**Bot goes offline when I close the terminal**
Expected. See [Hosting it 24/7](#hosting-it-247).

**`/clear` says it failed**
It needs **Manage Channels**, since it works by cloning and deleting rather
than bulk-deleting messages. Check the bot's role has that permission and
sits above the channel's permission overwrites.

**A channel disappeared after `/clear`**
That's how it works — the original is deleted and replaced with an empty
copy in the same position. The copy is a different channel internally, so
any integration or webhook pointing at the old one needs re-adding. The
bot's own settings are remapped automatically.
