version="1.4"
released="2024 may 11"

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
#
# V1.2 - 27/11/2023
#   added filename sanitization
#
# V1.3 - 01/02/2024
#   added subfolder for saved torrent in the 1773xxx format. 1000 files per subfolder
#
# V1.4 - 2024/05/11 (switch to new date format)
#   refactored the feed parsing to use requests and ElementTree instead of feedparser
#   refactored the structure of the script to use threading and scheduling
#   added a global list to store RSS entries
#   added a function to process entries from the list in a separate thread to avoid blocking the feed parsing
#   added function to safe send messages and documents to handle rate limits and retries
#   RETRY_COUNT now applies to sending messages and documents
#   added FEED_REQUEST_TIMEOUT environment variable to manage the timeout for fetching the feed
#   added encoding="utf-8" to open and write the processed_ids file to avoid UnicodeEncodeError
#   add function to log messages with timestamps (no file logging yet)
#   add a lot of log messages to track the script execution
#   add DELAY_BETWEEN_SENDS environment variable to set the delay between sending messages
#   disabled log of processed entries to avoid flooding the log
#   added a log to notify that no more entries are available to process
#   added a function to send an alert if no new items are processed for a certain amount of time
#   added a function to reacquire the feed on alert to verify if new items are being added and not noticed by the script
#   send alert if no new items are processed for a certain amount of time and new items are detected in the feed


import time
import requests
import os
import traceback
from telegram import Bot, InputFile
from telegram.error import RetryAfter
from urllib.parse import urlparse, quote, unquote
from dotenv import load_dotenv
import re
import threading
import xml.etree.ElementTree as ET
import schedule

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
FEED_REQUEST_TIMEOUT = int(os.getenv('FEED_REQUEST_TIMEOUT') or 30)
TORRENT_FILE_REQUEST_TIMEOUT = int(os.getenv('TORRENT_FILE_REQUEST_TIMEOUT') or 30)
DELAY_BETWEEN_SENDS = int(os.getenv('DELAY_BETWEEN_SENDS') or 3)

# Initialize bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)


def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}")

# Function to safely send a message to a chat
def safe_send_message(chat_id, text, parse_mode=None):
    global bot
    max_retries = RETRY_COUNT  # Maximum number of retries to send a message
    delay = DELAY_BETWEEN_SENDS  # Initial delay between retries
    for attempt in range(max_retries):
        log(f"Attempt {attempt + 1} of {max_retries} to send message...")
        try:
            bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            log(f"Sent. Waiting {DELAY_BETWEEN_SENDS} seconds...")
            time.sleep(delay)  # Delay between messages to prevent rate limit errors
            break
        except RetryAfter as e:
            sleep_time = max(delay, e.retry_after)  # Wait for the maximum of the initial delay or the required retry time
            log(f"Rate limit hit, retrying in {sleep_time} seconds")
            time.sleep(sleep_time)
        except Exception as e:
            log(f"Failed to send message on attempt {attempt + 1} due to: {e}")
            if attempt == max_retries - 1:
                raise

# Function to safely send a document to a chat
def safe_send_document(chat_id, document, caption=None, parse_mode=None):
    global bot, DELAY_BETWEEN_SENDS
    max_retries = RETRY_COUNT  # Maximum number of retries to send a message
    delay = DELAY_BETWEEN_SENDS  # Initial delay between retries
    for attempt in range(max_retries):
        log(f"Attempt {attempt + 1} of {max_retries} to send document...")
        try:
            bot.send_document(chat_id=chat_id, document=document, caption=caption, parse_mode=parse_mode)
            log(f"Sent. Waiting {DELAY_BETWEEN_SENDS} seconds...")
            time.sleep(delay)
            break
        except RetryAfter as e:
            sleep_time = max(delay, e.retry_after)
            log(f"Rate limit hit, retrying in {sleep_time} seconds")
            time.sleep(sleep_time)
        except Exception as e:
            log(f"Failed to send document on attempt {attempt + 1} due to: {e}")
            if attempt == max_retries - 1:
                raise

start_message = "Nyaa RSS bot " + version + " released on " + released + " started."
log(start_message)
safe_send_message(chat_id=ERROR_REPORT_USER_ID, text=start_message)

# Create downloads folder if not exists
log("Creating downloads folder if not exists...")
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)
log("Done.")

# Load processed IDs from file. Cut on "|" and get only the number
log("Loading processed_ids file...")
processed_file_path = 'processed_ids.txt'
if os.path.exists(processed_file_path):
    with open(processed_file_path, 'r', encoding="utf-8") as file:
        processed_ids = set(line.split("|")[0].strip() for line in file)
    log("Loaded.")
else:
    log("File not found. Creating empty set.")
    processed_ids = set()

# Load category-channel mappings from environment variable
log("Loading category-channel mappings...")
category_channel_mappings_str = os.getenv('CATEGORY_CHANNEL_MAPPINGS')
category_channel_mappings = []
for mapping_str in category_channel_mappings_str.split(','):
    category, channel, enabled = mapping_str.split('|')
    category_channel_mappings.append(CategoryChannel(category, channel, enabled == '1'))
    log(f"Loaded: {category} -> {channel} ({'Enabled' if enabled == '1' else 'Disabled'})")
log("Loaded.")


def sanitize_filename(filename):
    """
    Sanitize a filename to be compatible with both Linux and Windows.
    Removes characters that are not allowed in Windows filenames,
    while preserving spaces and supporting international characters.
    """

    # Windows filename restrictions (characters not allowed: \/:*?"<>|)
    # Using Unicode character properties to support international characters
    sanitized = re.sub(r'[\\/:*?"<>|\r\n]+', '', filename, flags=re.UNICODE)

    # Remove leading and trailing periods, which can cause issues in Windows
    sanitized = sanitized.strip(".")

    return sanitized


def generate_unique_filename(file_name, file_ext, id):
    global DOWNLOAD_PATH
    # Calculate the folder name based on the id
    folder_name = f"{int(id) // 1000}xxx"  # Integer division to get the base and append 'xxx'
    folder_path = os.path.join(DOWNLOAD_PATH, folder_name)

    # Ensure the folder exists
    os.makedirs(folder_path, exist_ok=True)

    # Prepend the "id" variable to the filename
    full_filename = f"{id}-{file_name}{file_ext}"

    # Maximum allowed filename length taken from the OS
    try:
        max_filename_length = os.pathconf(folder_path, 'PC_NAME_MAX')
    except:
        max_filename_length = 255

    # Build the full file path
    file_path = os.path.join(folder_path, full_filename)

    counter = 1

    while os.path.exists(file_path):
        # Define a new filename with a counter
        new_file_name = f"{id}-{file_name}_{counter}{file_ext}"
        
        # Check if the total length is too long and shorten the file_name section
        if len(new_file_name) > max_filename_length:
            remaining_length = max_filename_length - len(file_ext) - len(str(id)) - 3  # Account for "|", "_", and "."
            file_name = file_name[:remaining_length]
            new_file_name = f"{id}-{file_name}_{counter}{file_ext}"

        file_path = os.path.join(folder_path, new_file_name)

        counter += 1

    return file_path


# Global list to store RSS entries
rss_entries = []

def fetch_latest_rss_entry():
    last_id = 0
    try:
        try:
            log("Fetching latest feed item...")
            response = requests.get(FEED_URL, timeout=FEED_REQUEST_TIMEOUT)
            log("Feed fetched.")
            try:
                log("Validating XML...")
                root = ET.fromstring(response.content)
                log("Validated.")
                log("Parsing items...")
                item = root.find('.//item')
                entry = {
                    'title': item.find('title').text,
                    'link': item.find('link').text,
                    'guid': item.find('guid').text,
                    'published': item.find('pubDate').text,
                    'nyaa_infohash': item.find('{https://nyaa.si/xmlns/nyaa}infoHash').text,
                    'nyaa_categoryid': item.find('{https://nyaa.si/xmlns/nyaa}categoryId').text,
                    'nyaa_category': item.find('{https://nyaa.si/xmlns/nyaa}category').text,
                    'nyaa_size': item.find('{https://nyaa.si/xmlns/nyaa}size').text
                }
                log("Parsed.")
                last_id = urlparse(entry['guid']).path.split('/')[-1]
            except ET.ParseError as pe:
                error_message = "XML Parse Error for latest entry: Incomplete or malformed XML."
                log(error_message)
                safe_send_message(chat_id=ERROR_REPORT_USER_ID, text=error_message)
        except requests.RequestException as re:
            error_message = str(re) + "\n\n" + traceback.format_exc()
            log("Error fetching RSS: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error fetching RSS for latest entry: " + error_message)
        except Exception as e:
            # Unknown error
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Unknown Error fetching RSS for latest entry: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error fetching RSS for latest entry: " + error_message)
    except Exception as e:
        # Unexpected error
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Error: " + error_message)
        except Exception as ei:
            log("Unknown internal error while fetching RSS.")
    return last_id

def fetch_rss_feed():
    global rss_entries
    local_entries = []
    try:
        try:
            log("Fetching feed...")
            response = requests.get(FEED_URL, timeout=FEED_REQUEST_TIMEOUT)
            log("Feed fetched.")
            try:
                log("Validating XML...")
                root = ET.fromstring(response.content)
                log("Validated.")
                log("Parsing items...")
                for item in root.findall('.//item'):
                    local_entries.append({
                        'title': item.find('title').text,
                        'link': item.find('link').text,
                        'guid': item.find('guid').text,
                        'published': item.find('pubDate').text,
                        'nyaa_infohash': item.find('{https://nyaa.si/xmlns/nyaa}infoHash').text,
                        'nyaa_categoryid': item.find('{https://nyaa.si/xmlns/nyaa}categoryId').text,
                        'nyaa_category': item.find('{https://nyaa.si/xmlns/nyaa}category').text,
                        'nyaa_size': item.find('{https://nyaa.si/xmlns/nyaa}size').text
                    })
                log("Parsed. Found " + str(len(local_entries)) + " items.")

                rss_entries.extend(reversed(local_entries))

                log("Feed parsed. Waiting " + str(CHECK_INTERVAL) + " seconds for next parsing.")

            except ET.ParseError as pe:
                error_message = "XML Parse Error: Incomplete or malformed XML."
                log(error_message)
                safe_send_message(chat_id=ERROR_REPORT_USER_ID, text=error_message)
        except requests.RequestException as re:
            error_message = str(re) + "\n\n" + traceback.format_exc()
            log("Error fetching RSS: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error fetching RSS: " + error_message)
        except Exception as e:
            # Unknown error
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Unknown Error fetching RSS: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error fetching RSS: " + error_message)
    except Exception as e:
        # Unexpected error
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Error: " + error_message)
        except Exception as ei:
            log("Unknown internal error while fetching RSS.")

def safe_fetch_rss_feed():
    try:
        fetch_rss_feed()
    except Exception as e:
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Error on handling scheduled job: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error on handling scheduled job: " + error_message)
        except Exception as e:
            # Unexpected error
            try:
                error_message = str(e) + "\n\n" + traceback.format_exc()
                log("Error: " + error_message)
            except Exception as ei:
                log("Unknown error while running scheduled job.")

last_new_item_timestamp = time.time()
last_alert_sent = 0
last_processed_id = 0

def reset_alerts():
    global last_new_item_timestamp, last_alert_sent
    last_new_item_timestamp = time.time()
    last_alert_sent = 0

def send_alert_if_needed():
    global last_new_item_timestamp, last_alert_sent, processed_ids
    time_thresholds = [
        # (20, "20 seconds"),
        # (40, "40 seconds"),
        # (60, "1 minute"),
        (600, "10 minutes"),
        (1200, "20 minutes"),
        (1800, "30 minutes"),
        (3600, "1 hour"),
        (7200, "2 hours"),
        (14400, "4 hours"),
        (21600, "6 hours")
    ]
    current_time = time.time()
    message_sent = False

    for threshold, message in time_thresholds:
        if current_time - last_new_item_timestamp > threshold and last_alert_sent < threshold:
            # verify if new items are being added to the xml
            last_xml_id =  fetch_latest_rss_entry()
            if last_xml_id not in processed_ids:
                # something is wrong
                last_alert_sent = threshold
                message_text = f"Something wrong.\nNo new items in the last {message}. But the XML feed has new items.\nLast items in the processed_ids: {last_processed_id}\nLast item in the XML: {last_xml_id}"
                safe_send_message(chat_id=ERROR_REPORT_USER_ID, text=message_text)
                log(message_text)
                message_sent = True
                break  # Only send one message per check
            else:
                # normal behavior
                last_alert_sent = threshold
                log("No new items in the last " + message + " but no new items detected from the XML feed when checking.")
                message_sent = False
                break

    return message_sent

def process_entries():
    global rss_entries
    to_process = False
    while True:
        if rss_entries:
            to_process = True
            entry = rss_entries.pop(0)
            process_entry(entry)  # Assuming this function is defined elsewhere
        else:
            if to_process:
                log("No more entries to process. Waiting for new entries...")
                to_process = False
            send_alert_if_needed()
            time.sleep(1)  # Sleep for a short time if there are no entries to process

def process_entry(entry):
    global last_processed_id, processed_ids
    try:
        try:
            # Parse ID from GUID URL
            id = urlparse(entry['guid']).path.split('/')[-1]
            title = entry['title'].replace("&", "&amp;").replace("<","&lt;").replace(">", "&gt;") #avoid unsupported start tag error when send message with <...> titles

            # If we haven't processed this entry yet
            if id not in processed_ids:
                log(f"Processing entry: {id} | {title}")
                # Form the magnet link with URL encoding
                magnet_link = f"magnet:?xt=urn:btih:{entry['nyaa_infohash']}&dn={quote(title)}&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
                view_link = f"<a href='{entry['guid']}'>View</a>"
                download_link = f"<a href='{entry['link']}'>Download</a>"
                published_datetime = entry['published'].replace(" -0000", "")
                
                # Replace spaces and - in category with underscores and prepend with #
                category = "#" + entry['nyaa_category'].replace(" ", "_").replace("-", "_")

                # Form the message in HTML
                message = f"<b>{title}</b>\n<b>{entry['nyaa_size']}</b> - {category}\n\n{download_link} - {view_link}\n\nID: {id}\nHash: <code>{entry['nyaa_infohash']}</code>\n\n<code>{magnet_link}</code>\n\nPublished: {published_datetime}"
                if len(message) >= 1024:
                    message_part1 = f"<b>{title}</b>\n<b>{entry['nyaa_size']}</b> - {category}\n\n{download_link} - {view_link}\n\nID: {id}\nHash: <code>{entry['nyaa_infohash']}</code>"
                    message_part2 = f"<code>{magnet_link}</code>\n\nPublished: {published_datetime}"
                
                log("Downloading torrent file...")
                # Download the file
                response = requests.get(entry['link'], stream=True, timeout=TORRENT_FILE_REQUEST_TIMEOUT)
                log("Downloaded. Saving...")
                # Extract the filename from the Content-Disposition header and unquote
                suggested_filename = unquote(response.headers['Content-Disposition'].split('filename*=UTF-8\'\'')[-1])
                # Add [id] and [hash] in the filename before the .torrent extension
                file_name, file_ext = os.path.splitext(suggested_filename)
                sanitized_file_name = sanitize_filename(file_name)
                #file_path = os.path.join(DOWNLOAD_PATH, f"{file_name}{file_ext}")#[{id}][{entry['nyaa_infohash']}]{file_ext}")
                file_path = generate_unique_filename(sanitized_file_name, file_ext, id)

                try:
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                        send_file = True
                        log("Saved.")
                except Exception as e:
                    send_file = False  
                    log("Error saving file: " + str(e))

                send_to = [TELEGRAM_CHANNEL_ID]
                
                # Send the message with the file to each corresponding channel
                for mapping in category_channel_mappings:
                    if mapping.category == entry['nyaa_categoryid'] and mapping.enabled:
                        send_to.append(mapping.channel)                  

                log("Sending message...")
                if send_file:
                    # Send the message with the file to global channel
                    log(f"Sending file {file_path} ...")
                    with open(file_path, 'rb') as f:
                        for destination in send_to:
                            log(f"Sending to {destination}...")
                            f.seek(0)  # Reset the file pointer to the beginning of the file
                            if len(message) >= 1024:
                                safe_send_document(chat_id=destination, document=InputFile(f), caption=message_part1, parse_mode='HTML')
                                log("Sent first part. Sending second part...")
                                safe_send_message(chat_id=destination, text=message_part2, parse_mode='HTML')
                                log("Sent second part.")
                            else:
                                safe_send_document(chat_id=destination, document=InputFile(f), caption=message, parse_mode='HTML')
                                log("Done.")
                            #time.sleep(3) #slow processing to avoid flood error # disabled -> already added delay in safe_send_* functions
                else:
                    log("Sending message only...")
                    for destination in send_to:
                        log(f"Sending to {destination}...")
                        if len(message) >= 1024:
                            safe_send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message_part1, parse_mode='HTML')
                            log("Sent first part. Sending second part...")
                            safe_send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message_part2, parse_mode='HTML')
                            log("Sent second part.")
                        else:
                            safe_send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='HTML')
                            log("Done.")
                        #time.sleep(3) #slow processing to avoid flood error # disabled -> already added delay in safe_send_* functions
                    


                # Mark the entry as processed - Attach the torrent name to ids
                processed_ids.add(id)
                last_processed_id = id
                log("Saving entry to processed_ids file.")
                with open(processed_file_path, 'a', encoding="utf-8") as file:
                    file.write(f"{id}|{file_name}{file_ext}\n")
                log("Saved.")

                reset_alerts()
                log(f"Processed.")
            # else:
            #     log(f"Entry already processed: {id} | {title}")
        except Exception as e:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log(f"Error processing entry: {id} | {title} \nError:" + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Error processing entry: " + error_message)
            log("Waiting 60 seconds to retry.")
            time.sleep(60)
    except Exception as e:
        # Unexpected error
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Error: " + error_message)
        except Exception as ei:
            log("Unknown internal error.")
        time.sleep(120)

    

# safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Max retry attempts reached.\n\nBye Bye!")
# log("Max retry attempts reached.\n\nBye Bye!")

# Start processing thread
log("Starting processing thread...")
thread = threading.Thread(target=process_entries)
thread.daemon = True
thread.start()
log("Started.")

# First Run and then Schedule the fetching task
log("First run of fetch_rss_feed...")
safe_fetch_rss_feed()
log("First run done. Scheduling task.")
schedule.every(CHECK_INTERVAL).seconds.do(safe_fetch_rss_feed)
log("Scheduled.")

# Start scheduled tasks
while True:
    try:
        schedule.run_pending()
    except Exception as e:
        try:
            error_message = str(e) + "\n\n" + traceback.format_exc()
            log("Very unexpected error on handling scheduled job: " + error_message)
            safe_send_message(chat_id=ERROR_REPORT_USER_ID, text="Very unexpected error on handling scheduled job: " + error_message)
        except Exception as e:
            # Unexpected error
            try:
                error_message = str(e) + "\n\n" + traceback.format_exc()
                log("Error: " + error_message)
            except Exception as ei:
                log("Very unexpected error while running scheduled job.")
    time.sleep(1)

