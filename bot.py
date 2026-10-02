import os
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FALIX_API_KEY = os.getenv("FALIX_API_KEY")
FALIX_SERVER_ID = os.getenv("FALIX_SERVER_ID")

# Your dedicated Discord status channel
STATUS_CHANNEL_ID = 1540285782483542079

# How often Anaya checks Falix
UPDATE_INTERVAL = 10

# File used to remember the dashboard message
STATUS_FILE = "status_message.txt"

FALIX_API = "https://client.falixnodes.net/api/v2"


# ============================================================
# VALIDATE CONFIG
# ============================================================

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from .env")

if not FALIX_API_KEY:
    raise RuntimeError("FALIX_API_KEY is missing from .env")

if not FALIX_SERVER_ID:
    raise RuntimeError("FALIX_SERVER_ID is missing from .env")


# ============================================================
# BOT
# ============================================================

class Anaya(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        # No slash commands.
        # Anaya is completely automatic.

        print("🤖 Automatic monitoring mode enabled.")


bot = Anaya()


# ============================================================
# FALIX API
# ============================================================

async def falix_request(method, endpoint):

    url = f"{FALIX_API}{endpoint}"

    headers = {
        "Authorization": f"Bearer {FALIX_API_KEY}",
        "Accept": "application/json"
    }

    try:

        async with aiohttp.ClientSession() as session:

            async with session.request(
                method,
                url,
                headers=headers
            ) as response:

                raw = await response.text()

                try:
                    data = await response.json()
                except Exception:
                    data = None

                return response.status, data, raw

    except Exception as e:

        print("❌ Falix connection error:", e)

        return None, None, str(e)


# ============================================================
# SERVER STATUS
# ============================================================

async def get_server_status():

    status_code, data, raw = await falix_request(
        "GET",
        f"/servers/{FALIX_SERVER_ID}/console/status"
    )

    if status_code != 200:

        print(
            f"❌ Status API error: {status_code} | {raw}"
        )

        return None

    if isinstance(data, dict):
        return data.get("data", data)

    return None


# ============================================================
# QUEUE STATUS
# ============================================================

async def get_queue_status():

    status_code, data, raw = await falix_request(
        "GET",
        f"/servers/{FALIX_SERVER_ID}/console/queue-status"
    )

    if status_code != 200:

        # Queue may simply not exist when the server
        # isn't starting. Don't treat this as a fatal error.

        return None

    if isinstance(data, dict):
        return data.get("data", data)

    return None


# ============================================================
# FORMAT TIME
# ============================================================

def format_seconds(seconds):

    if seconds is None:
        return "Unknown"

    try:
        seconds = max(0, int(seconds))
    except Exception:
        return "Unknown"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"

    if minutes > 0:
        return f"{minutes}m {secs}s"

    return f"{secs}s"


# ============================================================
# DASHBOARD MESSAGE MEMORY
# ============================================================

def load_message_id():

    if not os.path.exists(STATUS_FILE):
        return None

    try:

        with open(
            STATUS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return int(file.read().strip())

    except Exception:

        return None


def save_message_id(message_id):

    with open(
        STATUS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(str(message_id))


# ============================================================
# CREATE EMBED
# ============================================================

def create_status_embed(server, queue):

    status = str(
        server.get("status", "unknown")
    ).lower()

    node_ready = server.get(
        "node_ready",
        False
    )

    resources = server.get("resources")

    message = server.get(
        "message",
        "No status message."
    )


    # ========================================================
    # ONLINE
    # ========================================================

    if status == "running":

        embed = discord.Embed(
            title="⛏️ MINECRAFT SERVER",
            description="🟢 **SERVER ONLINE**",
            colour=discord.Color.green()
        )

        embed.add_field(
            name="📡 Status",
            value="🟢 Online",
            inline=True
        )

        if resources:

            uptime = format_seconds(
                resources.get("uptime")
            )

            cpu = resources.get(
                "cpu",
                0
            )

            memory = resources.get(
                "memory",
                0
            )

            # Falix memory is bytes
            memory_mb = memory / 1024 / 1024

            embed.add_field(
                name="⏱️ Uptime",
                value=uptime,
                inline=True
            )

            embed.add_field(
                name="💻 CPU",
                value=f"{cpu:.1f}%",
                inline=True
            )

            embed.add_field(
                name="🧠 RAM",
                value=f"{memory_mb:.0f} MB",
                inline=True
            )

        embed.add_field(
            name="🖥️ Node",
            value=(
                "🟢 Ready"
                if node_ready
                else "🟡 Waiting"
            ),
            inline=True
        )

        embed.add_field(
            name="💬 Falix",
            value=message,
            inline=False
        )


    # ========================================================
    # QUEUED / STARTING
    # ========================================================

    elif queue and queue.get("queued"):

        queue_status = queue.get(
            "status",
            "waiting"
        )

        position = queue.get(
            "position"
        )

        queue_length = queue.get(
            "queue_length"
        )

        estimated = queue.get(
            "estimated_wait_seconds"
        )

        wait_seconds = queue.get(
            "wait_seconds"
        )

        if queue_status == "waiting":

            title = "🟡 **SERVER IN QUEUE**"

        elif queue_status == "processing":

            title = "🟠 **SERVER BOOTING**"

        else:

            title = "🟡 **SERVER STARTING**"


        embed = discord.Embed(
            title="⛏️ MINECRAFT SERVER",
            description=title,
            colour=discord.Color.orange()
        )

        embed.add_field(
            name="📋 Queue Position",
            value=(
                f"**#{position}** / {queue_length}"
                if position is not None
                else "Unknown"
            ),
            inline=True
        )

        embed.add_field(
            name="🔄 Queue State",
            value=queue_status.upper(),
            inline=True
        )

        embed.add_field(
            name="⏳ Estimated Wait",
            value=format_seconds(
                estimated
            ),
            inline=True
        )

        embed.add_field(
            name="🕐 Time In Queue",
            value=format_seconds(
                wait_seconds
            ),
            inline=True
        )

        embed.add_field(
            name="🖥️ Node",
            value=(
                "🟢 Ready"
                if node_ready
                else "🟡 Waiting"
            ),
            inline=True
        )

        embed.add_field(
            name="💬 Falix",
            value=message,
            inline=False
        )


    # ========================================================
    # OFFLINE
    # ========================================================

    else:

        embed = discord.Embed(
            title="⛏️ MINECRAFT SERVER",
            description="🔴 **SERVER OFFLINE**",
            colour=discord.Color.red()
        )

        embed.add_field(
            name="📡 Status",
            value="🔴 Offline",
            inline=True
        )

        embed.add_field(
            name="🖥️ Node",
            value=(
                "🟢 Ready"
                if node_ready
                else "🔴 Not reachable"
            ),
            inline=True
        )

        embed.add_field(
            name="💬 Falix",
            value=message,
            inline=False
        )


    # ========================================================
    # FOOTER
    # ========================================================

    now = datetime.now().strftime("%H:%M:%S")

    embed.set_footer(
        text=f"Anaya • Live Monitoring • Updated {now}"
    )

    return embed


# ============================================================
# GET OR CREATE DASHBOARD
# ============================================================

async def get_dashboard_message():

    channel = bot.get_channel(
        STATUS_CHANNEL_ID
    )

    if channel is None:

        print(
            f"❌ Cannot find status channel: "
            f"{STATUS_CHANNEL_ID}"
        )

        return None


    message_id = load_message_id()


    # --------------------------------------------------------
    # Try existing dashboard
    # --------------------------------------------------------

    if message_id:

        try:

            message = await channel.fetch_message(
                message_id
            )

            return message

        except discord.NotFound:

            print(
                "⚠️ Old dashboard message no longer exists."
            )

        except discord.Forbidden:

            print(
                "❌ Anaya does not have permission "
                "to read this channel."
            )

            return None

        except Exception as e:

            print(
                "❌ Could not fetch dashboard:",
                e
            )


    # --------------------------------------------------------
    # Create new dashboard
    # --------------------------------------------------------

    embed = discord.Embed(
        title="⛏️ MINECRAFT SERVER",
        description="🔄 **Connecting to Falix...**",
        colour=discord.Color.blurple()
    )

    embed.add_field(
        name="🤖 Anaya",
        value="Automatic live monitoring is active.",
        inline=False
    )

    embed.set_footer(
        text="Anaya • Live Monitoring"
    )

    try:

        message = await channel.send(
            embed=embed
        )

        save_message_id(
            message.id
        )

        print(
            f"✅ Created dashboard message: {message.id}"
        )

        return message

    except discord.Forbidden:

        print(
            "❌ Anaya cannot send messages in "
            "the status channel."
        )

        return None

    except Exception as e:

        print(
            "❌ Could not create dashboard:",
            e
        )

        return None


# ============================================================
# UPDATE DASHBOARD
# ============================================================

async def update_dashboard():

    message = await get_dashboard_message()

    if message is None:
        return


    server = await get_server_status()

    queue = await get_queue_status()


    # --------------------------------------------------------
    # Falix unavailable
    # --------------------------------------------------------

    if server is None:

        embed = discord.Embed(
            title="⛏️ MINECRAFT SERVER",
            description="⚠️ **STATUS UNAVAILABLE**",
            colour=discord.Color.gold()
        )

        embed.add_field(
            name="Connection",
            value="Unable to retrieve the server status from Falix."
        )

        embed.set_footer(
            text="Anaya • Retrying automatically"
        )

    else:

        embed = create_status_embed(
            server,
            queue
        )


    # --------------------------------------------------------
    # Edit same message
    # --------------------------------------------------------

    try:

        await message.edit(
            embed=embed
        )

    except discord.NotFound:

        # Message was deleted.
        # Remove stored ID so a new one is created next cycle.

        print(
            "⚠️ Dashboard was deleted. Creating a new one..."
        )

        try:

            os.remove(STATUS_FILE)

        except FileNotFoundError:
            pass

    except discord.Forbidden:

        print(
            "❌ Anaya no longer has permission "
            "to edit the dashboard."
        )

    except Exception as e:

        print(
            "❌ Discord update error:",
            e
        )


# ============================================================
# BACKGROUND MONITOR
# ============================================================

@tasks.loop(
    seconds=UPDATE_INTERVAL
)
async def status_monitor():

    try:

        await update_dashboard()

    except Exception as e:

        print(
            "❌ Monitor error:",
            e
        )


@status_monitor.before_loop
async def before_status_monitor():

    await bot.wait_until_ready()


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print()
    print("======================================")
    print("          ANAYA IS ONLINE")
    print("======================================")
    print(f"Bot: {bot.user}")
    print(f"Servers: {len(bot.guilds)}")
    print(f"Status Channel: {STATUS_CHANNEL_ID}")
    print("Monitoring: ENABLED")
    print("Commands: NONE")
    print("======================================")
    print()


    if not status_monitor.is_running():

        status_monitor.start()


# ============================================================
# START BOT
# ============================================================

bot.run(DISCORD_TOKEN)