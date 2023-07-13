import time
import feedparser
import requests
import os
import traceback
from telegram import Bot, InputFile
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
FEED_URL = os.getenv('FEED_URL')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH')
ERROR_REPORT_USER_ID = os.getenv('ERROR_REPORT_USER_ID')

# Initialize bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Create downloads folder if not exists
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Load processed IDs from file
processed_file_path = 'processed_ids.txt'
if os.path.exists(processed_file_path):
    with open(processed_file_path, 'r') as file:
        processed_ids = set(line.strip() for line in file)
else:
    processed_ids = set()

try:
    while True:
        # Parse the RSS feed
        feed = feedparser.parse(FEED_URL)

        # Loop over entries to catch all new posts
        for entry in feed.entries:
            # Parse ID from GUID URL
            id = urlparse(entry.guid).path.split('/')[-1]

            # If we haven't processed this entry yet
            if id not in processed_ids:
                # Form the magnet link
                magnet_link = f"magnet:?xt=urn:btih:{entry.nyaa_infohash}&dn={entry.title}&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
                view_link = f"[View]({entry.guid})"
                download_link = f"[Download]({entry.link})"
                # Form the message
                message = f"*{entry.title}* \n\nCategory: {entry.nyaa_category} \nSize: {entry.nyaa_size} \n\n{download_link} \n[Magnet]({magnet_link}) \n{view_link} \n\nInfoHash: {entry.nyaa_infohash} \nPublished Date: {entry.published} \nID: {id}"

                # Download the file
                response = requests.get(entry.link, stream=True)
                file_path = os.path.join(DOWNLOAD_PATH, f"{id}.torrent")
                with open(file_path, 'wb') as f:
                    f.write(response.content)

                # Send the message with the file
                with open(file_path, 'rb') as f:
                    bot.send_document(chat_id=TELEGRAM_CHANNEL_ID, document=InputFile(f), caption=message, parse_mode='Markdown')

                # Mark the entry as processed
                processed_ids.add(id)
                with open(processed_file_path, 'a') as file:
                    file.write(f"{id}\n")

        # Wait before checking again
        time.sleep(CHECK_INTERVAL)
except Exception as e:
    # Send the error message to the specified user
    error_message = str(e) + "\n\n" + traceback.format_exc()
    bot.send_message(chat_id=ERROR_REPORT_USER_ID, text=error_message)
