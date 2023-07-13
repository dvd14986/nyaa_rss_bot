version="1.0"
released="13 jul 2023"

#changelog
# V1.0 - 13/07/2023
#   first release
#

import time
import feedparser
import requests
import os
import traceback
from telegram import Bot, InputFile
from urllib.parse import urlparse, quote, unquote
from dotenv import load_dotenv

class CategoryChannel:
    def __init__(self, category, channel, enabled):
        self.category = category
        self.channel = channel
        self.enabled = enabled

# Load environment variables
load_dotenv()
FEED_URL = os.getenv('FEED_URL')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL'))
RETRY_COUNT = int(os.getenv('RETRY_COUNT'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH')
ERROR_REPORT_USER_ID = os.getenv('ERROR_REPORT_USER_ID')

# Initialize bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

start_message = "Nyaa RSS bot " + version + " released on " + released + " started."
print(start_message)
bot.send_message(chat_id=ERROR_REPORT_USER_ID, text=start_message)

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

# Load category-channel mappings from environment variable
category_channel_mappings_str = os.getenv('CATEGORY_CHANNEL_MAPPINGS')
category_channel_mappings = []
for mapping_str in category_channel_mappings_str.split(','):
    category, channel, enabled = mapping_str.split('|')
    category_channel_mappings.append(CategoryChannel(category, channel, enabled == '1'))

errors = 0
while errors < RETRY_COUNT:
    try:
        while True:
            print("Parsing new feeds...")
            # Parse the RSS feed
            feed = feedparser.parse(FEED_URL)

            # Loop over entries in reverse order to catch all new posts in their historical order
            for entry in reversed(feed.entries):
                # Parse ID from GUID URL
                id = urlparse(entry.guid).path.split('/')[-1]

                # If we haven't processed this entry yet
                if id not in processed_ids:
                    # Form the magnet link with URL encoding
                    magnet_link = f"magnet:?xt=urn:btih:{entry.nyaa_infohash}&dn={quote(entry.title)}&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
                    view_link = f"<a href='{entry.guid}'>View</a>"
                    download_link = f"<a href='{entry.link}'>Download</a>"
                    published_datetime = entry.published.replace(" -0000", "")
                    
                    # Replace spaces and - in category with underscores and prepend with #
                    category = "#" + entry.nyaa_category.replace(" ", "_").replace("-", "_")

                    # Form the message in HTML
                    message = f"<b>{entry.title}</b>\n<b>{entry.nyaa_size}</b> - {category}\n\n{download_link} - {view_link}\n\nID: {id}\nHash: <code>{entry.nyaa_infohash}</code>\n\n<code>{magnet_link}</code>\n\nPublished: {published_datetime}"

                    # Download the file
                    response = requests.get(entry.link, stream=True)
                    # Extract the filename from the Content-Disposition header and unquote
                    suggested_filename = unquote(response.headers['Content-Disposition'].split('filename*=UTF-8\'\'')[-1])
                    # Add [id] and [hash] in the filename before the .torrent extension
                    file_name, file_ext = os.path.splitext(suggested_filename)
                    file_path = os.path.join(DOWNLOAD_PATH, f"{file_name}[{id}][{entry.nyaa_infohash}]{file_ext}")

                    with open(file_path, 'wb') as f:
                        f.write(response.content)

                    # Send the message with the file to global channel
                    with open(file_path, 'rb') as f:
                        bot.send_document(chat_id=TELEGRAM_CHANNEL_ID, document=InputFile(f), caption=message, parse_mode='HTML')

                    # Send the message with the file to each corresponding channel
                    for mapping in category_channel_mappings:
                        if mapping.category == entry.nyaa_categoryid and mapping.enabled:
                            with open(file_path, 'rb') as f:
                                bot.send_document(chat_id=mapping.channel, document=InputFile(f), caption=message, parse_mode='HTML')

                    # Mark the entry as processed
                    processed_ids.add(id)
                    with open(processed_file_path, 'a') as file:
                        file.write(f"{id}\n")

            # Wait before checking again
            print("Feed parsed. Waiting " + str(CHECK_INTERVAL) + " seconds for next parsing.")
            time.sleep(CHECK_INTERVAL)
            errors = 0
    except Exception as e:
        # Send the error message to the specified user
        error_message = str(e) + "\n\n" + traceback.format_exc()
        print("Error: " + error_message)
        bot.send_message(chat_id=ERROR_REPORT_USER_ID, text=error_message)
        print("Waiting 60 seconds to retry. Attempt: " + str(errors))
        errors += 1
        time.sleep(60)
