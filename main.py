import asyncio
import os
import discord
import requests
from discord.ext import commands

import config

intents = discord.Intents.default()
intents.message_content = True

class Bot(commands.Bot):
    async def setup_hook(self) -> None:
        await load_extensions()

        synced = await self.tree.sync()
        print(f"Synced {len(synced)} application commands.")

bot = Bot(
    command_prefix=config.COMMAND_PREFIX,
    intents=intents
)

@bot.event
async def on_ready():
    if bot.user is None:
        return
    
    from config import URL
    response = requests.get(f"{URL}/api/GetInstanceName")
    
    if response.status_code == 200:
        instance_name = response.text
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print(f"Connected to: {instance_name}")
    else:
        print("Failed to retrieve instance name. Shutting down.")
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
                print(f"Loaded {extension}")
            except Exception as e:
                print(f"Failed loading {extension}: {e}")

async def main() -> None:
    if not config.TOKEN:
        raise RuntimeError("Token not found. Set it in .env file.")

    async with bot:
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
