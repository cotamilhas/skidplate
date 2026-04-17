import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import asyncio
from datetime import datetime, timezone
from colorama import Fore, Style, init
from config import TOKEN, COMMAND_PREFIX, EMBED_COLOR, INTENTS, DEBUG_MODE
from utils import debug

init(autoreset=True)

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=INTENTS, help_command=None)

async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"This command is on cooldown. Try again in **{error.retry_after:.2f}** seconds.",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True
        )
    else:
        message = f"An unexpected error occurred: `{error}`"
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

bot.tree.on_error = on_tree_error

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename != '__init__.py':
            extension = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(extension)
                print(f"Loaded cog: {Fore.GREEN}{extension}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Failed to load {extension}: {e}{Style.RESET_ALL}")

# TODO: better help command, moderation cog has a lot of commands which breaks the embed field limit, maybe paginated help commands...
@bot.tree.command(name="help", description="Displays the help menu.")
@app_commands.describe(command="The command you want to get help with.")
async def help_command(interaction: discord.Interaction, command: str = None):
    def chunk_lines(lines: list[str], max_len: int = 1024) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for line in lines:
            if len(line) > max_len:
                line = line[: max_len - 3].rstrip() + "..."

            extra_len = len(line) + (1 if current else 0)
            if current and current_len + extra_len > max_len:
                chunks.append("\n".join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += extra_len

        if current:
            chunks.append("\n".join(current))

        return chunks

    embed = discord.Embed(
        title=f"Help for {bot.user.name}",
        color=EMBED_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    command_categories = {}

    for cog_name, cog in bot.cogs.items():
        commands_list = cog.get_app_commands()
        if commands_list:
            command_categories[cog_name] = commands_list

    if not command:
        max_category_fields = 24 
        used_fields = 0
        truncated_output = False

        for category, commands_list in command_categories.items():
            lines = [
                f"`/{cmd.name}` - {cmd.description or 'No description provided.'}"
                for cmd in commands_list
            ]
            category_chunks = chunk_lines(lines)

            for index, chunk in enumerate(category_chunks):
                if used_fields >= max_category_fields:
                    truncated_output = True
                    break

                field_name = category if index == 0 else f"{category} (cont.)"
                embed.add_field(name=field_name, value=chunk, inline=False)
                used_fields += 1

            if truncated_output:
                break

        details_text = "Use `/help <command>` to get detailed info about a specific command."
        if truncated_output:
            details_text = (
                "Use `/help <command>` to get detailed info about a specific command.\n"
                "Some categories were omitted because the embed reached Discord field limits."
            )

        embed.add_field(
            name="Command Details",
            value=details_text,
            inline=False
        )
    else:
        cmd = bot.tree.get_command(command)
        if cmd:
            params = []
            if hasattr(cmd, "parameters"):
                for param in cmd.parameters:
                    params.append(f"`{param.name}`: {param.description}")
            elif hasattr(cmd, "_params"):
                params = [f"`{param.name}`: {param.description}" for param in cmd._params.values()]

            usage = f"/{cmd.name}"
            if params:
                usage += " " + " ".join(
                    [f"<{param.name}>" for param in (cmd.parameters if hasattr(cmd, "parameters") else cmd._params.values())]
                )

            embed.add_field(
                name=f"Command: /{cmd.name}",
                value=f"**Description:** {cmd.description}\n**Usage:** `{usage}`",
                inline=False
            )
            if params:
                embed.add_field(
                    name="Parameters",
                    value="\n".join(params),
                    inline=False
                )
        else:
            embed.add_field(
                name="Command not found",
                value="No such command was found. Please check the name and try again.",
                inline=False
            )

    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
    embed.set_thumbnail(url=bot.user.avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not DEBUG_MODE:
        return

    BLACKLIST = {"mod_login", "mod_set_username", "mod_set_password"}
    
    if interaction.type == discord.InteractionType.application_command:
        if interaction.command.name in BLACKLIST:
            return

        params = ""
        if hasattr(interaction, "data") and "options" in interaction.data:
            options = interaction.data["options"]
            params = " | Params: " + ", ".join(
                f"{Fore.YELLOW}{opt['name']}{Style.RESET_ALL}="
                f"{Fore.MAGENTA}{opt.get('value', '')}{Style.RESET_ALL}"
                for opt in options
            )

        if interaction.guild:
            location = (
                f"Server: {Fore.CYAN}{interaction.guild.name}{Style.RESET_ALL} "
                f"(ID: {Fore.YELLOW}{interaction.guild.id}{Style.RESET_ALL})"
            )
        else:
            location = f"{Fore.MAGENTA}(DM){Style.RESET_ALL}"

        print(
            f"[COMMAND] {Fore.CYAN}/{interaction.command.name}{Style.RESET_ALL}{params} "
            f"| User: {Fore.GREEN}{interaction.user}{Style.RESET_ALL} "
            f"| {location}"
        )

async def get_instance_name(api_url: str) -> str | None:
    endpoint = f"{api_url}api/GetInstanceName"
    temp_session = None

    try:
        session = getattr(bot, "http_session", None)
        if session is None or session.closed:
            temp_session = aiohttp.ClientSession()
            session = temp_session

        timeout = aiohttp.ClientTimeout(total=5)
        async with session.get(endpoint, timeout=timeout) as response:
            if response.status != 200:
                return None

            instance_name = (await response.text()).strip()
            return instance_name or None
    except Exception:
        return None
    finally:
        if temp_session and not temp_session.closed:
            await temp_session.close()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    api_url = os.getenv("API_URL", "http://example.com:10050")
    instance_name = await get_instance_name(api_url)

    if instance_name:
        print(f"Connected to: {instance_name} ({api_url})")
    else:
        print("Could not retrieve instance name from API.")
        print("Shutting down bot...")
        await bot.close()

if __name__ == "__main__":
    async def main():
        bot.http_session = aiohttp.ClientSession()
        try:
            await load_cogs()
            await bot.start(TOKEN)
        except discord.LoginFailure:
            print("The provided token is invalid. Please verify your token and try again.")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if hasattr(bot, "http_session") and not bot.http_session.closed:
                await bot.http_session.close()

    asyncio.run(main())