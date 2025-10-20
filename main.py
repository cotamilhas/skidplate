import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from datetime import datetime, timezone
from colorama import Fore, Style, init
from config import TOKEN, COMMAND_PREFIX, EMBED_COLOR, INTENTS, DEBUG_MODE

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
@app_commands.describe(command="The command you want to get help with.")
async def help_command(interaction: discord.Interaction, command: str = None):
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
        for category, commands_list in command_categories.items():
            embed.add_field(
                name=category,
                value="\n".join([f"`/{cmd.name}` - {cmd.description}" for cmd in commands_list]),
                inline=False
            )
        embed.add_field(
            name="Command Details",
            value="Use `/help <command>` to get detailed info about a specific command.",
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

    if interaction.type == discord.InteractionType.application_command:
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


if __name__ == "__main__":
    async def main():
        try:
            await load_cogs()
            await bot.start(TOKEN)
        except discord.LoginFailure:
            print("The provided token is invalid. Please verify your token and try again.")
        except Exception as e:
            print(f"An error occurred: {e}")

    asyncio.run(main())
