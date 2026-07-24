# Skidplate

A simple Discord bot for fetching player and creation data, viewing server statistics, and moderating a PLGarage instance (Soon™).

# Notice

Currently I'm focusing this project for ModNation Racers (PS3 only), feel free to contribute and add the support for LBP Karting and other platforms.

## Requirements

- Python 3.10+
- [PLGarage](https://github.com/jackcaver/PLGarage) instance

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root with:

```env
TOKEN=your_discord_bot_token_here
URL=http://example.com:10050
COMMAND_PREFIX=!
```

## Run

```bash
python main.py
```
