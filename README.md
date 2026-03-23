# Skidplate

A Discord Bot written in Python that retrieves player and creation information from a PLGarage instance.

## About

Skidplate is a Discord bot designed to integrate with PLGarage APIs, providing easy access to player statistics and creation data from supported gaming platforms. Currently focused on ModNation Racers for PS3, with plans to support other platforms and LittleBigPlanet Karting.

This project is built on discord.py and uses Docker for containerized deployment.

## Features

- Retrieve player information from PLGarage instances
- Access creation metadata and statistics
- Configurable command prefix and responses
- Extensible cog-based command system
- Debug mode for development
- Docker and Docker Compose support for easy deployment
- Asynchronous command handling with error management

## Requirements

- Python 3.13+
- Docker and Docker Compose (for containerized deployment)
- A Discord Bot token from Discord Developer Portal
- A PLGarage instance URL

## Quick Start with Docker

The fastest way to get started is using Docker Compose.

### Prerequisites

1. Clone the repository
2. Create a `.env` file in the project root with your configuration
3. Ensure Docker and Docker Compose are installed

### Environment Configuration

Create a `.env` file in the root directory with the following variables:

```bash
DISCORD_TOKEN=your_discord_bot_token_here
COMMAND_PREFIX=!
API_URL=http://your-plgarage-instance:10050/
DEBUG_MODE=false
MODERATOR_ROLE_ID=1234567890123456789
SHOW_WIN_RATE=false
USE_EMOJIS=false
FULL_EMOJI=<:full:1234567891234567890>
HALF_EMOJI=<:half:1234567891234567890>
EMPTY_EMOJI=<:empty:1234567891234567890>
```

Replace the placeholder values with your actual configuration:
- `DISCORD_TOKEN`: Your Discord bot token from the Developer Portal
- `COMMAND_PREFIX`: The prefix for text commands (default: !)
- `API_URL`: The URL to your PLGarage instance API
- `DEBUG_MODE`: Set to true to enable detailed logging (default: false)
- `MODERATOR_ROLE_ID`: Discord role ID for users with moderator permissions
- `SHOW_WIN_RATE`: Set to true to display win rate statistics (default: false)
- `USE_EMOJIS`: Set to true to enable emoji-based visuals in bot responses (ratings, stats, and embeds). Requires custom emojis to be configured below. (default: false)
- `FULL_EMOJI`, `HALF_EMOJI`, `EMPTY_EMOJI`: Custom emoji IDs for ratings (optional)

### Running with Docker Compose

The easiest deployment method:

```bash
docker-compose up -d
```

This command will:
1. Build the Docker image from the Dockerfile
2. Start the bot container
3. Mount local volumes for hot-reloading cogs and config changes
4. Automatically restart on failure

To view logs:

```bash
docker-compose logs -f skidplate
```

To stop the bot:

```bash
docker-compose down
```

### Running with Docker (Manual Build)

If you prefer to build and run manually:

Build the image:

```bash
docker build -t skidplate:latest .
```

Run the container:

```bash
docker run -d --name skidplate-bot \
  --env-file .env \
  -v $(pwd)/cogs:/app/cogs \
  -v $(pwd)/config.py:/app/config.py \
  --restart unless-stopped \
  skidplate:latest
```

View logs:

```bash
docker logs -f skidplate-bot
```

Stop the container:

```bash
docker stop skidplate-bot
docker rm skidplate-bot
```

## Local Development

For local development without Docker:

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Setup Environment

Create a `.env` file (same as Docker setup) in the project root directory.

### Run the Bot

```bash
python main.py
```

The bot will log its activities to the console. If DEBUG_MODE is enabled in .env, you will see detailed command execution information.

## Project Structure

```
skidplate/
├── main.py              Main bot entry point
├── config.py            Configuration management
├── utils.py             Utility functions
├── requirements.txt     Python dependencies
├── Dockerfile           Container configuration
├── docker-compose.yml   Compose configuration
├── .env                 Environment variables (create this)
└── cogs/                Discord command modules
```

## Dependencies

- `discord.py>=2.4.0` - Discord API wrapper
- `colorama==0.4.6` - Colored terminal output
- `aiohttp>=3.7.4` - Asynchronous HTTP client
- `python-dotenv>=1.2.1` - Environment variable management

## Creating Custom Commands

Commands are organized as cogs in the `cogs/` directory. Each cog is a Python module that extends the bot's functionality.

When using Docker Compose, the cogs directory is mounted as a volume, allowing you to add or modify cogs without restarting the container (though you may need to reload them via Discord commands).

## Troubleshooting

### Bot doesn't start
- Verify your `DISCORD_TOKEN` is valid
- Check that the `API_URL` is accessible
- Review logs: `docker-compose logs skidplate`

### Commands not responding
- Ensure `DEBUG_MODE=true` in .env to see detailed logs
- Verify the bot has permission to send messages in the Discord channel
- Check that cogs are loading: look for "Loaded cog:" messages in logs

### API connection issues
- Verify the `API_URL` is correct and reachable from the container
- For Docker, use the full network address (not localhost)
- Check firewall settings allowing container access

## Related Projects

- [PLGarage](https://github.com/jackcaver/PLGarage)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.