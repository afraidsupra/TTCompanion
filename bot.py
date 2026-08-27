import logging
import os
from datetime import UTC, datetime, timezone
from typing import Any

import discord
from discord.ext import commands
from dotenv import load_dotenv
from sqlcipher3 import dbapi2 as sqlcipher

# Load environment variables
_ = load_dotenv()
bot_key = os.getenv("DISCORD_TOKEN")
pragma = os.getenv("PRAGMA")
now: datetime = datetime.now(timezone.utc)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    filename=f'./logs/{now.strftime("%Y-%m-%d-%H-%M-%S")}.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
log_file = logging.FileHandler(f"bot{datetime}.log")
log_file.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addFilter(log_file)

# Configure Discord client
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

# Configure encrypted database
db = sqlcipher.connect('ticket.db')
cursor = db.cursor()
_ = cursor.execute(f"PRAGMA key='{pragma}';")

db.commit()

# DB functions
async def write_DB(query: str, *params: tuple[int | str | float | None, ...]) -> tuple[bool, str]:
    try:
        db = sqlcipher.connect('ticket.db')
        cursor = db.cursor()
        _ = cursor.execute(f"PRAGMA key='{pragma}';")
        _ = cursor.execute(query, *params)

        db.commit()
        db.close()
        return True, "Record written successfully"
    except sqlcipher.Error as e:
        return False, f"Unable to write entry: {e}"

async def read_DB(query: str, *params: tuple[int | str | float | None, ...]) -> tuple[bool, list[tuple[Any, ...]], str]:
    try:
        db = sqlcipher.connect('ticket.db')
        cursor = db.cursor()
        _ = cursor.execute(f"PRAGMA key='{pragma}';")
        _ = cursor.execute(query, *params)

        result = cursor.fetchall()
        db.close()
        err_msg = 'None'
        return True, result, err_msg
    except sqlcipher.Error as e:
        result = ("No", "Result")
        err_msg = f"Failed to read from database. {e}"
        return (False, result, err_msg)
# Start up scripts
@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user}')
    visible_guilds: list[list[str | int]] = []
    for guild in client.guilds:
        visible_guilds.append([guild.name, guild.id])
    logger.info(f'Visible Guilds: {visible_guilds}')
    await validate_tables()

async def validate_tables():
    db = sqlcipher.connect('ticket.db')
    cursor = db.cursor()
    _ = cursor.execute(f"PRAGMA key='{pragma}';")
    query = """
    CREATE TABLE IF NOT EXISTS text_channels (
        id                        INTEGER PRIMARY KEY,          -- channel.id (snowflake)
        name                      TEXT    NOT NULL,             -- channel.name
        guild_id                  INTEGER NOT NULL,             -- channel.guild.id
        category_id               INTEGER,                       -- channel.category_id (nullable)
        position                  INTEGER NOT NULL DEFAULT 0,   -- channel.position
        last_message_id           INTEGER,                       -- channel.last_message_id (may be stale)
        slowmode_delay            INTEGER NOT NULL DEFAULT 0,   -- seconds, 0 = disabled
        nsfw                      INTEGER NOT NULL DEFAULT 0,   -- bool as 0/1
        default_thread_slowmode_delay   INTEGER NOT NULL DEFAULT 0,     -- seconds
        type                      INTEGER NOT NULL,             -- ChannelType.value (15 = text)
        created_at                INTEGER DEFAULT (unixepoch()),    -- ISO-8601 UTC (from id / created_at)
        deleted_at                INTEGER,
        permissions_synced        INTEGER NOT NULL DEFAULT 0,   -- bool
        first_captured_at         INTEGER    NOT NULL DEFAULT (unixepoch()),
        last_captured_at          INTEGER    NOT NULL DEFAULT (unixepoch())
    );
    """
    _ = cursor.execute(query)
    query = """
    CREATE TABLE IF NOT EXISTS ticket_categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        guild_id INTEGER NOT NULL
    );
    """
    _ = cursor.execute(query)

    db.commit()
    db.close()

# This section captures activity on the Discord
@client.event
async def on_guild_channel_create(channel: discord.channel.TextChannel):
    print(type(channel))
    if type(channel) == discord.channel.TextChannel:
        logger.info(f'Channel created: {channel.id}: {channel.name}')
        query = "INSERT INTO text_channels (id, name, guild_id, category_id, position, last_message_id, slowmode_delay, nsfw, default_thread_slowmode_delay, type, created_at, permissions_synced) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        params = (channel.id, channel.name, channel.guild.id, channel.category_id, channel.position, channel.last_message_id, channel.slowmode_delay, str(channel.nsfw), channel.default_thread_slowmode_delay, str(channel.type), channel.created_at.timestamp(), channel.permissions_synced)
        write_success, result = await write_DB(query, params)
        if write_success:
            logger.info(result)
        else:
            logger.error(result)
    elif type(channel) != discord.channel.TextChannel:
        logger.info(f"Created channel ({channel.id} - {channel.name}) is a {channel.type}")


@client.event
async def on_guild_channel_delete(channel: discord.channel.TextChannel):
    print(type(channel))
    if type(channel) == discord.channel.TextChannel:
        logger.info(f'Channel deleted: {channel.id}: {channel.name}')
        query = "UPDATE text_channels SET deleted_at = ? WHERE id = ?"
        params = (datetime.now(UTC).timestamp(), channel.id)
        update_success, result = await write_DB(query, params)
        if update_success:
            logger.info(result)
        else:
            logger.error(result)
    elif type(channel) != discord.channel.TextChannel:
        logger.info(f"Deleted channel ({channel.id} - {channel.name}) is a {channel.type}")

# Bot commands
@client.command()
async def show_categories(ctx: commands.Context[commands.Bot]):
    success, result = await read_DB("SELECT * FROM ticket_categories")
    if success:
        logger.info("Returned ticket categories successfully")
        if len(result) == 0:
            _ = await ctx.send("No ticket categories. Add categories with !add_category [category ID].")
    else:
        logger.error(f"Failed to read ticket categories. {result}")
        _ = await ctx.send(str(result))

# Start up trigger
if __name__ == '__main__':
    print('Attempting to start bot services')
    if bot_key is not None:
        client.run(bot_key)
    else:
        logger.exception("Failed to start Discord bot")
        raise ValueError("Missing Discord bot token")
