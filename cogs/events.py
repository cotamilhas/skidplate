import discord
from discord.ext import commands
from colorama import Style, Fore, init
import sys
init(autoreset=True)

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not hasattr(self.bot, 'appinfo'):
            self.bot.appinfo = await self.bot.application_info()
            self.bot.owner_id = self.bot.appinfo.owner.id
        
        print(f"\n{Fore.GREEN}Bot is Online!")
        print(f"Logged in as {Fore.GREEN}{self.bot.user.name} {Fore.YELLOW}({self.bot.user.id})\n")
        print(f"{Fore.CYAN}Owner: {Fore.GREEN}{self.bot.appinfo.owner} {Fore.YELLOW}({self.bot.appinfo.owner.id})")
        print(f"{Fore.CYAN}Python Version: {Fore.GREEN}{sys.version}")
        print(f"{Fore.CYAN}Command Prefix: {Fore.GREEN}{self.bot.command_prefix}")

        try:
            synced = await self.bot.tree.sync()
            print(f"{Fore.GREEN}Synced {len(synced)} application command(s).{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Failed to sync commands: {e}{Style.RESET_ALL}")

        print(f"{Fore.CYAN}Bot is online as {self.bot.user}{Style.RESET_ALL}")


async def setup(bot):
    await bot.add_cog(Events(bot))
