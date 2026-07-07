import datetime
import json
import os
import re

import googleapiclient.errors
from dateutil import parser
from dateutil.relativedelta import relativedelta
from googleapiclient.discovery import build


DEFAULT_REGION_CODES = ("RU", "UA", "BY", "KZ")
GAMBLING_KEYWORDS = ("казино", "ставки", "беттинг", "gambling", "casino", "betting")
YOUTUBE_MAX_BATCH_SIZE = 50


def load_api_keys(file_path):
    """Load YouTube API keys and cursor metadata from a JSON file."""
    with open(file_path, 'r') as file:
        return json.load(file)


def save_last_working_key_index(file_path, index):
    """Persist the last successful API-key index between runs."""
    with open(file_path, 'r+') as file:
        data = json.load(file)
        data['last_working_key_index'] = index
        file.seek(0)
        json.dump(data, file)
        file.truncate()


def initialize_youtube(api_keys, start_index=0):
    """Create a YouTube Data API client for the selected API key."""
    current_index = start_index
    youtube = build('youtube', 'v3', developerKey=api_keys[current_index])
    return youtube, current_index


def load_seen_channels(file_path):
    """Load channel IDs that were already analyzed in previous runs."""
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    try:
        with open(file_path, 'r') as file:
            seen_channels = set(json.load(file))
    except json.JSONDecodeError:
        seen_channels = set()
    return seen_channels


def save_seen_channels(file_path, seen_channels):
    """Save processed channel IDs so future runs can skip duplicates."""
    with open(file_path, 'w') as file:
        json.dump(list(seen_channels), file)


def handle_api_error(e, api_keys, current_index):
    """Rotate API keys when YouTube quota is exceeded."""
    if 'quotaExceeded' in str(e):
        print(f"API key {current_index + 1} reached its quota. Checking the next key.")
        current_index += 1
        if current_index >= len(api_keys):
            print("All API keys have reached their quota.")
            return None, current_index
        youtube = build('youtube', 'v3', developerKey=api_keys[current_index])
        return youtube, current_index
    else:
        print(f"An error occurred: {e}")
        return None, current_index


api_keys = []
current_api_key_index = 0
youtube = None


def initialize_from_config(file_path='api_keys.json'):
    global api_keys, current_api_key_index, youtube

    api_keys_data = load_api_keys(file_path)
    api_keys = api_keys_data['keys']
    last_working_key_index = api_keys_data.get('last_working_key_index', 0)
    youtube, current_api_key_index = initialize_youtube(api_keys, last_working_key_index)


def search_channels(query, region_codes=DEFAULT_REGION_CODES, seen_channels=None, max_channels=200):
    """Search YouTube channels by query across the configured regions."""
    global youtube, current_api_key_index

    if seen_channels is None:
        seen_channels = set()

    channels = []
    for region in region_codes:
        next_page_token = None
        while len(channels) < max_channels:
            try:
                response = youtube.search().list(
                    q=query,
                    type="channel",
                    part="snippet",
                    maxResults=min(YOUTUBE_MAX_BATCH_SIZE, max_channels - len(channels)),
                    regionCode=region,
                    pageToken=next_page_token
                ).execute()

                for item in response.get('items', []):
                    channel_id = item['id']['channelId']
                    if channel_id not in seen_channels:
                        channels.append({
                            "channel_id": channel_id,
                            "title": item['snippet']['title'],
                            "description": item['snippet']['description'],
                            "region": region,
                        })
                        seen_channels.add(channel_id)
                        if len(channels) >= max_channels:
                            break

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

            except googleapiclient.errors.HttpError as e:
                youtube, current_api_key_index = handle_api_error(e, api_keys, current_api_key_index)
                if youtube is None:
                    return channels

    return channels


def get_channel_details(channel_ids):
    """Fetch channel metadata in API-sized batches."""
    global youtube, current_api_key_index

    details_list = []
    for i in range(0, len(channel_ids), YOUTUBE_MAX_BATCH_SIZE):
        try:
            response = youtube.channels().list(
                id=','.join(channel_ids[i:i + YOUTUBE_MAX_BATCH_SIZE]),
                part="snippet,statistics,contentDetails"
            ).execute()
            details_list.extend(response.get('items', []))
        except googleapiclient.errors.HttpError as e:
            youtube, current_api_key_index = handle_api_error(e, api_keys, current_api_key_index)
            if youtube is None:
                break

    return details_list


def get_last_video_date(uploads_playlist_id):
    """Return the latest upload date and description for a channel uploads playlist."""
    global youtube, current_api_key_index

    try:
        response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="contentDetails,snippet",
            maxResults=1
        ).execute()

        if not response.get('items'):
            return None, None

        last_video = response.get('items')[0]
        last_video_date = last_video['contentDetails']['videoPublishedAt']
        last_video_description = last_video['snippet']['description']
        return parser.isoparse(last_video_date), last_video_description

    except googleapiclient.errors.HttpError as e:
        if 'playlistNotFound' in str(e):
            return None, None
        youtube, current_api_key_index = handle_api_error(e, api_keys, current_api_key_index)
        if youtube is None:
            return None, None

    return None, None


def get_time_difference(last_upload_date):
    """Format a relative age for the latest upload timestamp."""
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = relativedelta(now, last_upload_date)

    if diff.years > 0:
        unit = "year" if diff.years == 1 else "years"
        return f"{diff.years} {unit} ago"
    elif diff.months > 0:
        unit = "month" if diff.months == 1 else "months"
        return f"{diff.months} {unit} ago"
    elif diff.days > 0:
        unit = "day" if diff.days == 1 else "days"
        return f"{diff.days} {unit} ago"
    elif diff.hours > 0:
        unit = "hour" if diff.hours == 1 else "hours"
        return f"{diff.hours} {unit} ago"
    elif diff.minutes > 0:
        unit = "minute" if diff.minutes == 1 else "minutes"
        return f"{diff.minutes} {unit} ago"
    else:
        return "less than a minute ago"


def contains_telegram_link(description):
    """Return whether text contains a Telegram link and the first match."""
    telegram_pattern = re.compile(r't\.me/[a-zA-Z0-9_]+')
    match = telegram_pattern.search(description)
    if match:
        return True, match.group()
    return False, None


def contains_gambling_keywords(description):
    """Detect gambling-related terms in English and target regional languages."""
    return any(keyword in description.lower() for keyword in GAMBLING_KEYWORDS)


def find_inactive_channels(
    query,
    min_subs=2000,
    max_subs=1000000,
    inactive_months=6,
    region_codes=DEFAULT_REGION_CODES,
    seen_channels=None,
    max_channels=200,
):
    """Find inactive channels matching subscriber, region, and content filters."""
    if seen_channels is None:
        seen_channels = set()

    print("Channel search started...")
    total_channels_analyzed = 0
    inactive_channels = []
    threshold_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=inactive_months * 30)

    while total_channels_analyzed < max_channels:
        channels = search_channels(
            query,
            region_codes=region_codes,
            seen_channels=seen_channels,
            max_channels=max_channels - total_channels_analyzed,
        )
        if not channels:
            break

        channel_ids = [ch['channel_id'] for ch in channels]
        details_list = get_channel_details(channel_ids)
        if not details_list:
            break

        for details in details_list:
            total_channels_analyzed += 1

            stats = details['statistics']
            snippet = details['snippet']
            content_details = details['contentDetails']
            channel_info = {
                "title": snippet['title'],
                "channel_id": details['id'],
                "subscriber_count": int(stats.get('subscriberCount', 0)),
                "video_count": int(stats.get('videoCount', 0)),
                "last_upload_date": None,
                "region": snippet.get('country', 'Not specified'),
                "description": snippet['description'],
            }

            uploads_playlist_id = content_details['relatedPlaylists'].get('uploads')
            if uploads_playlist_id:
                last_upload_date, last_video_description = get_last_video_date(uploads_playlist_id)
                channel_info['last_upload_date'] = last_upload_date
                channel_info['last_video_description'] = last_video_description

            if min_subs <= channel_info['subscriber_count'] <= max_subs and channel_info['video_count'] >= 10:
                last_upload_date = channel_info['last_upload_date']
                last_video_description = channel_info.get('last_video_description', '')
                if last_upload_date and last_upload_date < threshold_date:
                    telegram_in_description, telegram_link = contains_telegram_link(channel_info['description'])
                    telegram_in_video, telegram_video_link = contains_telegram_link(last_video_description)
                    if not contains_gambling_keywords(channel_info['description']) and not contains_gambling_keywords(last_video_description):
                        if channel_info['region'] in region_codes:
                            inactive_channels.append(channel_info)
                            time_since_last_video = get_time_difference(channel_info['last_upload_date'])
                            print(
                                f"{len(inactive_channels)}. Title: {channel_info['title']}, Subscribers: {channel_info['subscriber_count']}, "
                                f"Last video: {time_since_last_video}, Region: {channel_info['region']}"
                            )

        if len(channels) < max_channels - total_channels_analyzed:
            break

    if not inactive_channels:
        print("No channels found for this query.")

    return inactive_channels, seen_channels, total_channels_analyzed

def extract_email(description):
    """Return the first email address found in a description."""
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    match = email_pattern.search(description)
    if match:
        return match.group()
    return None


def ask_continue():
    while True:
        response = input("Continue? (Y/N): ").strip().lower()
        if response in ['y', 'yes', '']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Invalid input. Please enter Y or N.")


if __name__ == "__main__":
    try:
        initialize_from_config()

        while True:
            query = input("Enter a channel search query: ")
            max_channels = int(input("Enter the maximum number of channels to analyze: "))

            min_subs = 2000
            max_subs = 1000000
            region_codes = DEFAULT_REGION_CODES
            seen_channels_file = 'seen_channels.json'

            seen_channels = load_seen_channels(seen_channels_file)

            inactive_channels, seen_channels, total_channels_analyzed = find_inactive_channels(
                query,
                min_subs=min_subs,
                max_subs=max_subs,
                region_codes=region_codes,
                seen_channels=seen_channels,
                max_channels=max_channels,
            )

            save_seen_channels(seen_channels_file, seen_channels)

            if inactive_channels:
                print("\nTelegram links for matching channels:")
                for idx, channel in enumerate(inactive_channels, start=1):
                    telegram_in_description, telegram_link = contains_telegram_link(channel['description'])
                    if telegram_link:
                        print(f"{idx}. Title: {channel['title']}, {telegram_link}")
            else:
                print("No inactive channels matched the configured criteria.")

            print(f"\nAnalyzed {total_channels_analyzed} channels.")

            save_last_working_key_index('api_keys.json', current_api_key_index)

            if not ask_continue():
                break

    except FileNotFoundError:
        print("Missing api_keys.json. Copy api_keys.example.json to api_keys.json and add your YouTube API keys.")
    except KeyboardInterrupt:
        print("\nSearch interrupted by the user.")
    except googleapiclient.errors.HttpError as e:
        if 'quotaExceeded' in str(e):
            print("API quota exceeded. Search stopped.")
        else:
            print(f"An error occurred: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
