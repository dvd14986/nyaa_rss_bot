Collecting workspace information# Nyaa RSS Bot

A Python bot that monitors [Nyaa.si](https://nyaa.si) RSS feeds, automatically downloads new torrents, and forwards them to Telegram channels.

## Features

- Monitors Nyaa.si RSS feeds at configurable intervals
- Downloads torrent files and sends them to Telegram channels
- Supports mapping different Nyaa categories to different Telegram channels
- Organizes downloaded torrents in folders (1000 files per subfolder)
- Handles rate limiting to avoid Telegram API flood errors
- Provides error reporting and monitoring alerts
- Sanitizes filenames for compatibility across operating systems
- Manages message splitting for long torrent descriptions

## Requirements

- Python 3.6+
- Telegram bot token (get from [@BotFather](https://t.me/BotFather))
- A Telegram channel or group where the bot is an administrator

## Installation

Clone the repository or download the source code:

```bash
git clone https://github.com/yourusername/nyaa_rss_bot.git
cd nyaa_rss_bot
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Create a .env file from the example:

```bash
cp .env.example .env
```

Edit the .env file with your configuration (see Configuration section).


### Using Virtual Environment (recommended)
It's recommended to use a virtual environment to avoid dependency conflicts:

Creating a virtual environment
```bash
# Create a virtual environment in the project directory
python -m venv venv
```

Activating the virtual environment
On Windows:
```bash
venv\Scripts\activate
```

On macOS and Linux:
```bash
venv\Scripts\activate
```

Installing dependencies in the virtual environment
```bash
pip install -r requirements.txt
```

Deactivating when done
```bash
deactivate
```

Note: Always make sure your virtual environment is activated when running the bot.

## Configuration

Edit the .env file with your settings:

```
FEED_URL=https://nyaa.si/?page=rss
CHECK_INTERVAL=30
RETRY_COUNT=10
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=your_channel_id_here
DOWNLOAD_PATH=downloads/
ERROR_REPORT_USER_ID=your_telegram_id_here
CATEGORY_CHANNEL_MAPPINGS=1_1|channel_id1|1,1_2|channel_id2|1,1_3|channel_id3|1,1_4|channel_id4|1
FEED_REQUEST_TIMEOUT=30
TORRENT_FILE_REQUEST_TIMEOUT=30
DELAY_BETWEEN_SENDS=3
```

Configuration explanation:

- `FEED_URL`: The Nyaa.si RSS feed URL to monitor
- `CHECK_INTERVAL`: How often to check the feed (in seconds)
- `RETRY_COUNT`: Number of retry attempts for failed operations
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `TELEGRAM_CHANNEL_ID`: The ID of the main Telegram channel to send torrents to
- `DOWNLOAD_PATH`: Directory to save downloaded torrent files
- `ERROR_REPORT_USER_ID`: Telegram user ID to receive error reports
- `CATEGORY_CHANNEL_MAPPINGS`: Maps Nyaa categories to specific channels
  - Format: `category_id|channel_id|enabled(0/1)`, separated by commas
  - Example: `1_1|xxx|1` = Send category 1_1 to channel ID xxx, enabled
- `FEED_REQUEST_TIMEOUT`: Timeout for RSS feed requests (in seconds)
- `TORRENT_FILE_REQUEST_TIMEOUT`: Timeout for torrent file downloads (in seconds)
- `DELAY_BETWEEN_SENDS`: Delay between Telegram message sends (in seconds)

## Usage

Run the bot:

```bash
python nyaa_rss_bot.py
```

For production use, you may want to use a process manager like `systemd`, `supervisor`, or a simple script that restarts the bot if it crashes.

Example of a simple startup script:

```bash
#!/bin/bash
while true; do
  python nyaa_rss_bot.py
  sleep 10
done
```

## File Organization

The bot creates the following structure:

```
/downloads
  /1773xxx/
    1773001-torrent1.torrent
    1773002-torrent2.torrent
  /1774xxx/
    1774001-torrent1.torrent
    ...
processed_ids.txt  # Keeps track of processed torrents
```

## Changelog

See the changelog in the comments at the beginning of nyaa_rss_bot.py for version history and updates.