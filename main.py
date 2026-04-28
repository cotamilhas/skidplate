import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import asyncio
from datetime import datetime, timezone
from colorama import Fore, Style, init
from config import TOKEN, COMMAND_PREFIX, EMBED_COLOR, INTENTS, DEBUG_MODE
from ui.help_views import HelpPaginator
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

@bot.tree.command(name="help", description="Displays the help menu.")
@app_commands.describe(command="The command you want to get help with (e.g., 'players ban' for grouped commands).")
async def help_command(interaction: discord.Interaction, command: str = None):
    def chunk_lines(lines: list[str], max_len: int = 1024) -> list[str]:
        chunks, current, current_len = [], [], 0
        for line in lines:
            if len(line) > max_len:
                line = line[: max_len - 3].rstrip() + "..."
            extra_len = len(line) + (1 if current else 0)
            if current and current_len + extra_len > max_len:
                chunks.append("\n".join(current))
                current, current_len = [line], len(line)
            else:
                current.append(line)
                current_len += extra_len
        if current:
            chunks.append("\n".join(current))
        return chunks

    def count_leaf_commands(group: app_commands.Group) -> int:
        total = 0
        for sub in group.commands:
            if isinstance(sub, app_commands.Group):
                total += count_leaf_commands(sub)
            else:
                total += 1
        return total

    def get_compact_commands(commands_list):
        for cmd in commands_list:
            description = cmd.description or "No description."
            if isinstance(cmd, app_commands.Group):
                sub_count = count_leaf_commands(cmd)
                suffix = f" ({sub_count} subcommands)" if sub_count else ""
                yield f"`/{cmd.qualified_name}` - {description}{suffix}"
            else:
                yield f"`/{cmd.qualified_name}` - {description}"

    def find_command(cmd_name: str):
        parts = cmd_name.strip().lstrip("/").split()
        resolved = bot.tree.get_command(parts[0])
        for part in parts[1:]:
            if not isinstance(resolved, app_commands.Group):
                return None
            resolved = discord.utils.get(resolved.commands, name=part)
        return resolved

    if not command:
        pages = []
        for cog_name, cog in bot.cogs.items():
            cog_commands = cog.get_app_commands()
            if not cog_commands:
                continue
            lines = list(get_compact_commands(cog_commands))
            chunks = chunk_lines(lines)
            fields = [{"name": cog_name, "value": chunk} for chunk in chunks]
            pages.append({"category": cog_name, "fields": fields})

        if not pages:
            pages.append({"category": "Help", "fields": [{"name": "No Commands", "value": "No commands loaded."}]})

        paginator = HelpPaginator(
            interaction.user.id,
            pages=pages,
            bot_name=bot.user.name,
            requester_name=interaction.user.name,
            requester_avatar_url=interaction.user.display_avatar.url,
            bot_avatar_url=bot.user.display_avatar.url,
        )
        paginated_embed, error = await paginator.initialize()
        if error or not paginated_embed:
            await interaction.response.send_message(error or "Failed to build help.", ephemeral=True)
            return
        await interaction.response.send_message(embed=paginated_embed, view=paginator)
        paginator.message = await interaction.original_response()
    else:
        embed = discord.Embed(title=f"Help for {bot.user.name}", color=EMBED_COLOR)
        cmd = find_command(command)
        if cmd:
            command_params = []
            if hasattr(cmd, "parameters"):
                command_params = list(cmd.parameters)
            elif hasattr(cmd, "_params"):
                command_params = list(cmd._params.values())

            params = [f"`{p.name}`: {p.description}" for p in command_params]
            usage = f"/{cmd.qualified_name}" + (" " + " ".join(f"<{p.name}>" for p in command_params) if command_params else "")
            embed.add_field(name=f"Command: /{cmd.qualified_name}", value=f"**Description:** {cmd.description}\n**Usage:** `{usage}`", inline=False)

            if isinstance(cmd, app_commands.Group) and cmd.commands:
                subcommand_lines = [f"`/{sub.qualified_name}` - {sub.description or 'No description.'}" for sub in cmd.commands]
                for chunk in chunk_lines(subcommand_lines):
                    embed.add_field(name="Subcommands", value=chunk, inline=False)

            if params:
                embed.add_field(name="Parameters", value="\n".join(params), inline=False)
        else:
            embed.add_field(name="Command not found", value="No such command was found.", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not DEBUG_MODE:
        return

    BLACKLIST = {"moderators login", "moderators set-username", "moderators set-password"}
    
    if interaction.type == discord.InteractionType.application_command:
        cmd_name = interaction.command.qualified_name if hasattr(interaction.command, 'qualified_name') else interaction.command.name
        if cmd_name in BLACKLIST:
            return

        params = ""
        if hasattr(interaction, "data") and "options" in interaction.data:
            options = interaction.data["options"]

            def extract_param_options(raw_options):
                extracted = []
                for opt in raw_options:
                    nested = opt.get("options")
                    if isinstance(nested, list) and nested:
                        extracted.extend(extract_param_options(nested))
                        continue

                    if "value" in opt:
                        extracted.append(opt)
                return extracted

            param_options = extract_param_options(options)
            if param_options:
                params = " | Params: " + ", ".join(
                    f"{Fore.YELLOW}{opt['name']}{Style.RESET_ALL}="
                    f"{Fore.MAGENTA}{opt['value']}{Style.RESET_ALL}"
                    for opt in param_options
                )

        if interaction.guild:
            location = (
                f"Server: {Fore.CYAN}{interaction.guild.name}{Style.RESET_ALL} "
                f"(ID: {Fore.YELLOW}{interaction.guild.id}{Style.RESET_ALL})"
            )
        else:
            location = f"{Fore.MAGENTA}(DM){Style.RESET_ALL}"

        print(
            f"[COMMAND] {Fore.CYAN}/{cmd_name}{Style.RESET_ALL}{params} "
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
        print(f"Could not retrieve instance name from ({api_url})")
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