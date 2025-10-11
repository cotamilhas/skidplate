import discord
from discord.ext import commands
from colorama import Fore, init
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

        if self.bot.guilds:
            print(f"\n{Fore.CYAN}Guilds connected to:")
            for guild in self.bot.guilds:
                print(f"{Fore.GREEN}{guild.name} {Fore.YELLOW}({guild.id})")
                print(f"Owner: {Fore.GREEN}{guild.owner} {Fore.YELLOW}({guild.owner.id})")
                print(f"Members: {Fore.GREEN}{guild.member_count}\n")
                
        else:
            print(f"{Fore.RED}[EVENTS] The bot is not connected to any servers.\n")


async def setup(bot):
    await bot.add_cog(Events(bot))
