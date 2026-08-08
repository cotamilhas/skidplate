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

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
    original = getattr(error, "original", error)

    if isinstance(original, discord.NotFound) and getattr(original, "code", None) == 10062:
        command_name = interaction.command.qualified_name if interaction.command else "unknown"
        logger.warning("Expired interaction for command '%s'.", command_name)
        return

    command_name = interaction.command.qualified_name if interaction.command else "unknown"
    logger.exception("Unhandled app command error in '%s': %s", command_name, original)

    error_message = "Error: Command failed. Please try again."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)
    except discord.HTTPException:
        pass

@bot.event
async def on_ready():
    if bot.user is None:
        return
    
    from config import URL
    try:
        response = await asyncio.to_thread(requests.get, f"{URL}/api/GetInstanceName", timeout=10)
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
