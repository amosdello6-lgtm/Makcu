# Getting your bot online 24/7 — free

Your bot only works while it's running. If you start it on your own PC it
stops the moment you close the window or shut down. This guide gets it
running on a server that stays on permanently, for free.

**Pick one:**

- **[Railway](#railway)** — about 10 minutes, easiest, free credits cover a bot
- **[Oracle Cloud](#oracle-cloud)** — about 40 minutes, harder, free forever

If you're not sure, use Railway.

> **Don't use Render's free tier.** It puts your bot to sleep after 15
> minutes of inactivity, which takes it offline. Plenty of guides recommend
> it anyway. They're wrong for this.

---

## Before you start

You need two things ready:

1. **Your bot token** — from <https://discord.com/developers/applications>,
   your app, **Bot** tab, **Reset Token**, **Copy**
2. **The bot files** — the folder you were given

Keep your token private. Anyone who has it controls your bot completely.
Never post it in a screenshot, a Discord message, or a public repository.

---

## Railway

### Step 1: Put the code on GitHub

Railway deploys from GitHub, so the code needs to live there.

1. Make a free account at <https://github.com>
2. Click the **+** in the top right → **New repository**
3. Name it anything, and **set it to Private**
4. Click **Create repository**
5. On the next page click **uploading an existing file**
6. Drag in every file and folder from your bot folder
7. Click **Commit changes**

> **Do not upload your `.env` file.** It contains your token. If you
> accidentally do, go to the Discord Developer Portal and reset the token
> immediately — deleting the file afterwards is not enough, because GitHub
> keeps history.

### Step 2: Deploy

1. Go to <https://railway.app> and sign in with GitHub
2. **New Project** → **Deploy from GitHub repo**
3. Pick the repository you just made
4. Railway starts building. It will fail the first time — that's expected,
   it doesn't have your token yet.

### Step 3: Add your token

1. Click your service → **Variables** tab
2. **New Variable**
3. Name: `DISCORD_TOKEN`
4. Value: paste your token
5. **Add**

Railway redeploys automatically.

### Step 4: Check it worked

Open the **Deployments** tab and click the running deployment to see the
logs. You want:

```
INFO  bot: loaded cogs.automod
INFO  bot: loaded cogs.cleanup
...
INFO  bot: synced 49 commands globally
INFO  bot: logged in as YourBot#1234
```

Your bot should now show as online in Discord. Done.

> Slash commands registered globally can take up to an hour to appear the
> first time. This is a Discord limitation, not a problem with the bot.

### Keeping an eye on it

- **Usage** tab shows how much of your free credit you've used
- A small bot costs roughly $2–3/month against about $5/month in free credits
- If you run out, the bot stops until the credits reset

---

## Oracle Cloud

Harder to set up, but genuinely free with no expiry and no credits to run
out of. Worth it if you plan to run the bot for a long time.

### Step 1: Make an account

Sign up at <https://www.oracle.com/cloud/free/>. A card is required for
identity verification. You are not charged as long as you stay on
Always Free resources.

### Step 2: Create the server

1. In the Oracle console, go to **Compute → Instances → Create Instance**
2. **Image and shape** → **Change shape** → pick **Ampere** →
   **VM.Standard.A1.Flex**
3. Set 1 CPU and 6 GB memory (well within the free allowance)
4. Under **Add SSH keys**, choose **Generate a key pair for me** and
   **download the private key** — you cannot get it again
5. **Create**

Wait for the status to go green, then copy the **Public IP address**.

### Step 3: Connect

On Windows, open PowerShell:

```powershell
ssh -i C:\path\to\your\key.key ubuntu@YOUR_IP
```

Type `yes` if it asks about authenticity.

If it refuses the key as too open:

```powershell
icacls C:\path\to\your\key.key /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

### Step 4: Install and set up

Paste these one at a time:

```bash
sudo apt update && sudo apt install -y python3-pip git
```

Then upload your bot folder. Easiest way is to put it on GitHub (as in the
Railway steps above) and clone it:

```bash
git clone https://github.com/YOURNAME/YOURREPO.git
cd YOURREPO/discord-bot
pip3 install -r requirements.txt
```

Create the environment file:

```bash
nano .env
```

Type this, pasting your real token:

```
DISCORD_TOKEN=your_token_here
DATABASE_PATH=data/bot.db
```

Save with **Ctrl+O**, **Enter**, then **Ctrl+X**.

Test it:

```bash
python3 bot.py
```

If you see `logged in as ...`, it works. Stop it with **Ctrl+C**.

### Step 5: Keep it running forever

Right now it stops when you disconnect. This fixes that:

```bash
sudo nano /etc/systemd/system/discordbot.service
```

Paste this, changing `YOURREPO` to your folder name:

```ini
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/YOURREPO/discord-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and exit, then:

```bash
sudo systemctl enable --now discordbot
sudo systemctl status discordbot
```

Green `active (running)` means you're done. You can close PowerShell and
the bot stays up.

`Restart=always` means it also comes back by itself after a crash or a
reboot.

### Commands you'll want later

```bash
sudo systemctl restart discordbot   # after changing anything
sudo systemctl stop discordbot      # turn it off
journalctl -u discordbot -f         # watch live logs (Ctrl+C to exit)
```

---

## Updating the bot later

**Railway:** upload the changed files to GitHub. Railway redeploys on its
own.

**Oracle:**

```bash
cd ~/YOURREPO
git pull
sudo systemctl restart discordbot
```

Your `.env` and your database are never touched by an update, so your
token and all your settings survive.

---

## Backing up

Everything the bot remembers — settings, warnings, XP, tickets — is in one
file: `data/bot.db`.

**Oracle:**

```bash
cp ~/YOURREPO/discord-bot/data/bot.db ~/bot-backup.db
```

Worth doing before any update.

---

## If something goes wrong

**Bot shows offline**
Check the logs (Railway: Deployments tab. Oracle:
`journalctl -u discordbot -f`). The error is almost always in the last few
lines.

**`PrivilegedIntentsRequired`**
Go to the Developer Portal → your app → **Bot** → scroll to **Privileged
Gateway Intents** and enable **Server Members Intent** and **Message
Content Intent**. Save, then restart the bot.

**`DISCORD_TOKEN is not set`**
Railway: check the variable is named exactly `DISCORD_TOKEN`.
Oracle: check `.env` exists in the same folder as `bot.py` and has no typo.

**`Improper token has been passed`**
The token is wrong or was reset. Get a fresh one from the Developer Portal
and update it.

**Commands don't appear in Discord**
Wait up to an hour on first deploy. If they still don't show, the bot was
invited without the `applications.commands` scope — re-invite it using a
link that includes both `bot` and `applications.commands`.

**Bot is online but ignores commands**
Check it can actually see and send in the channel, and that its role sits
high enough in **Server Settings → Roles**.
