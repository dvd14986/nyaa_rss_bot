version="1.1"
released="09 nov 2023"

#changelog
# V1.0 - 13/07/2023
#   first release
#
# V1.0.1 - 14/07/2023
#   fixed bug on caption max length
#
# V1.0.2 - 19/07/2023
#   reviewed multiple send and add interval between sends to avoid flood error
#
# V1.0.3 - 08/08/2023
#   added external try-catch for unexpected errors
#
# v1..0.4 - 28/08/2023
#   added html tag char escape to avoid error on sending unexpected tags - https://core.telegram.org/bots/api#html-style
#
# V1.1 - 09/11/2023
#   added ids in the file name
#   added filename lenght limitation
#   check if file exist and rename it if true
#   torrent name is saved now in the processed_ids files too
#   spleep delay between message send set to 3 sec to avoid flood errors

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

# Load processed IDs from file. Cut on "|" and get only the number
processed_file_path = 'processed_ids.txt'
if os.path.exists(processed_file_path):
    with open(processed_file_path, 'r') as file:
        processed_ids = set(line.split("|")[0].strip() for line in file)
else:
    processed_ids = set()

# Load category-channel mappings from environment variable
category_channel_mappings_str = os.getenv('CATEGORY_CHANNEL_MAPPINGS')
category_channel_mappings = []
for mapping_str in category_channel_mappings_str.split(','):
    category, channel, enabled = mapping_str.split('|')
    category_channel_mappings.append(CategoryChannel(category, channel, enabled == '1'))


def generate_unique_filename(file_name, file_ext, id):
    global DOWNLOAD_PATH
    # Prepend the "id" variable to the filename
    full_filename = f"{id}-{file_name}{file_ext}"

    # Maximum allowed filename length taken from the OS
    try:
        max_filename_length = os.pathconf(DOWNLOAD_PATH, 'PC_NAME_MAX')
    except:
        max_filename_length = 255

    # Build the full file path
    file_path = os.path.join(DOWNLOAD_PATH, full_filename)

    counter = 1

    while os.path.exists(file_path):
        # Define a new filename with a counter
        new_file_name = f"{id}-{file_name}_{counter}{file_ext}"
        
        # Check if the total length is too long and shorten the file_name section
        if len(new_file_name) > max_filename_length:
            remaining_length = max_filename_length - len(file_ext) - len(id) - 3  # Account for "|", "_", and "."
            file_name = file_name[:remaining_length]
            new_file_name = f"{id}-{file_name}_{counter}{file_ext}"

        file_path = os.path.join(DOWNLOAD_PATH, new_file_name)

        counter += 1

    return file_path

errors = 0
while errors < RETRY_COUNT:
    try:
        try:
            while True:
                print("Parsing new feeds...")
                # Parse the RSS feed
                feed = feedparser.parse(FEED_URL)

                # Loop over entries in reverse order to catch all new posts in their historical order
                for entry in reversed(feed.entries):
                    # Parse ID from GUID URL
                    id = urlparse(entry.guid).path.split('/')[-1]
                    title = entry.title.replace("&", "&amp;").replace("<","&lt;").replace(">", "&gt;") #avoid unsupported start tag error when send message with <...> titles

                    # If we haven't processed this entry yet
                    if id not in processed_ids:
                        # Form the magnet link with URL encoding
                        magnet_link = f"magnet:?xt=urn:btih:{entry.nyaa_infohash}&dn={quote(title)}&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
                        view_link = f"<a href='{entry.guid}'>View</a>"
                        download_link = f"<a href='{entry.link}'>Download</a>"
                        published_datetime = entry.published.replace(" -0000", "")
                        
                        # Replace spaces and - in category with underscores and prepend with #
                        category = "#" + entry.nyaa_category.replace(" ", "_").replace("-", "_")

                        # Form the message in HTML
                        message = f"<b>{title}</b>\n<b>{entry.nyaa_size}</b> - {category}\n\n{download_link} - {view_link}\n\nID: {id}\nHash: <code>{entry.nyaa_infohash}</code>\n\n<code>{magnet_link}</code>\n\nPublished: {published_datetime}"
                        if len(message) >= 1024:
                            message_part1 = f"<b>{title}</b>\n<b>{entry.nyaa_size}</b> - {category}\n\n{download_link} - {view_link}\n\nID: {id}\nHash: <code>{entry.nyaa_infohash}</code>"
                            message_part2 = f"<code>{magnet_link}</code>\n\nPublished: {published_datetime}"

                        # Download the file
                        response = requests.get(entry.link, stream=True)
                        # Extract the filename from the Content-Disposition header and unquote
                        suggested_filename = unquote(response.headers['Content-Disposition'].split('filename*=UTF-8\'\'')[-1])
                        # Add [id] and [hash] in the filename before the .torrent extension
                        file_name, file_ext = os.path.splitext(suggested_filename)
                        #file_path = os.path.join(DOWNLOAD_PATH, f"{file_name}{file_ext}")#[{id}][{entry.nyaa_infohash}]{file_ext}")
                        file_path = generate_unique_filename(file_name, file_ext, id)

                        try:
                            with open(file_path, 'wb') as f:
                                f.write(response.content)
                                send_file = True
                        except Exception as e:
                            send_file = False  

                        send_to = [TELEGRAM_CHANNEL_ID]
                        
                        # Send the message with the file to each corresponding channel
                        for mapping in category_channel_mappings:
                            if mapping.category == entry.nyaa_categoryid and mapping.enabled:
                                send_to.append(mapping.channel)                  

                        if send_file:
                            # Send the message with the file to global channel
                            with open(file_path, 'rb') as f:
                                for destination in send_to:
                                    f.seek(0)  # Reset the file pointer to the beginning of the file
                                    if len(message) >= 1024:
                                        bot.send_document(chat_id=destination, document=InputFile(f), caption=message_part1, parse_mode='HTML')
                                        bot.send_message(chat_id=destination, text=message_part2, parse_mode='HTML')
                                    else:
                                        bot.send_document(chat_id=destination, document=InputFile(f), caption=message, parse_mode='HTML')
                                    time.sleep(3) #slow processing to avoid flood error
                        else:
                            for destination in send_to:
                                if len(message) >= 1024:
                                    bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message_part1, parse_mode='HTML')
                                    bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message_part2, parse_mode='HTML')
                                else:
                                    bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='HTML')
                                time.sleep(3) #slow processing to avoid flood error
        

                        # Mark the entry as processed - Attcach the torrent name to ids
                        processed_ids.add(id)
                        with open(processed_file_path, 'a') as file:
                            file.write(f"{id}|{file_name}{file_ext}\n")

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
    except Exception as e:
        # Unexpected error
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            print("Error: " + error_message)
        except Exception as ei:
            print("Unknown internal error.")
        time.sleep(120)

bot.send_message(chat_id=ERROR_REPORT_USER_ID, text="Max retry attempts reached.\n\nBye Bye!")
print("Max retry attempts reached.\n\nBye Bye!")