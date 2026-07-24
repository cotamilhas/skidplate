import asyncio
import os
import discord
import requests
import logging
from discord.ext import commands

import config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("skidplate")

intents = discord.Intents.default()
intents.message_content = True

class Bot(commands.Bot):
    async def setup_hook(self) -> None:
        await load_extensions()

        synced = await self.tree.sync()
        logger.info("Synced %s application commands.", len(synced))

bot = Bot(
    command_prefix=config.COMMAND_PREFIX,
    intents=intents
)

@bot.event
async def on_ready():
    if bot.user is None:
        return
    
    from config import URL
    try:
        response = requests.get(f"{URL}/api/GetInstanceName", timeout=10)
    except requests.RequestException as exc:
        logger.error("Failed to retrieve instance name: %s", exc)
        await bot.close()
        return
    
    if response.status_code == 200:
        instance_name = response.text
        logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
        logger.info("Connected to: %s", instance_name)
    else:
        logger.error("Failed to retrieve instance name. Shutting down.")
        await bot.close()
    
async def load_extensions() -> None:
    cogs_dir = "cogs"

    if not os.path.isdir(cogs_dir):
        return

    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            extension = f"cogs.{filename[:-3]}"

            try:
                await bot.load_extension(extension)
                logger.info("Loaded extension: %s", extension)
            except Exception as e:
                logger.exception("Failed loading extension %s: %s", extension, e)

async def main() -> None:
    if not config.TOKEN:
        raise RuntimeError("Token not found. Set it in .env file.")

    async with bot:
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
