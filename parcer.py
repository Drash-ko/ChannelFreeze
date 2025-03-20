import os
import json
from googleapiclient.discovery import build
import datetime
import googleapiclient.errors
from dateutil import parser
from dateutil.relativedelta import relativedelta
import re

# Функция для загрузки API ключей из файла
def load_api_keys(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Функция для сохранения последнего рабочего API ключа
def save_last_working_key_index(file_path, index):
    with open(file_path, 'r+') as file:
        data = json.load(file)
        data['last_working_key_index'] = index
        file.seek(0)
        json.dump(data, file)
        file.truncate()

# Функция для инициализации клиента YouTube API
def initialize_youtube(api_keys, start_index=0):
    current_index = start_index
    youtube = build('youtube', 'v3', developerKey=api_keys[current_index])
    return youtube, current_index

# Функция для загрузки уже обработанных каналов из файла
def load_seen_channels(file_path):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    try:
        with open(file_path, 'r') as file:
            seen_channels = set(json.load(file))
    except json.JSONDecodeError:
        seen_channels = set()
    return seen_channels

# Функция для сохранения обработанных каналов в файл
def save_seen_channels(file_path, seen_channels):
    with open(file_path, 'w') as file:
        json.dump(list(seen_channels), file)

# Функция для обработки ошибок и переключения между API ключами
def handle_api_error(e, api_keys, current_index):
    if 'quotaExceeded' in str(e):
        print(f"API {current_index + 1} не работает, проверяю следующий.")
        current_index += 1
        if current_index >= len(api_keys):
            print("Все API ключи перегружены.")
            return None, current_index
        youtube = build('youtube', 'v3', developerKey=api_keys[current_index])
        return youtube, current_index
    else:
        print(f"Произошла ошибка: {e}")
        return None, current_index

# Загрузка API ключей и инициализация клиента YouTube API
api_keys_data = load_api_keys('api_keys.json')
api_keys = api_keys_data['keys']
last_working_key_index = api_keys_data.get('last_working_key_index', 0)
youtube, current_api_key_index = initialize_youtube(api_keys, last_working_key_index)

# Функция для поиска каналов по запросу
def search_channels(query, region_codes=["RU", "UA", "BY", "KZ"], seen_channels=None, max_channels=200):
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
                    maxResults=min(50, max_channels - len(channels)),  # Ограничение на 50 результатов за запрос
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

# Функция для получения деталей канала
def get_channel_details(channel_ids):
    global youtube, current_api_key_index

    details_list = []
    # Разбиваем запросы на части по 50 каналов
    for i in range(0, len(channel_ids), 50):
        try:
            response = youtube.channels().list(
                id=','.join(channel_ids[i:i+50]),
                part="snippet,statistics,contentDetails"
            ).execute()
            details_list.extend(response.get('items', []))
        except googleapiclient.errors.HttpError as e:
            youtube, current_api_key_index = handle_api_error(e, api_keys, current_api_key_index)
            if youtube is None:
                break

    return details_list

# Функция для получения даты последнего видео в плейлисте
def get_last_video_date(uploads_playlist_id):
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

# Функция для вычисления разницы во времени
def get_time_difference(last_upload_date):
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = relativedelta(now, last_upload_date)

    if diff.years > 0:
        if diff.years == 1:
            return f"{diff.years} год назад"
        elif 2 <= diff.years <= 4:
            return f"{diff.years} года назад"
        else:
            return f"{diff.years} лет назад"
    elif diff.months > 0:
        if diff.months == 1:
            return f"{diff.months} месяц назад"
        elif 2 <= diff.months <= 4:
            return f"{diff.months} месяца назад"
        else:
            return f"{diff.months} месяцев назад"
    elif diff.days > 0:
        if diff.days == 1:
            return f"{diff.days} день назад"
        elif 2 <= diff.days <= 4:
            return f"{diff.days} дня назад"
        else:
            return f"{diff.days} дней назад"
    elif diff.hours > 0:
        if diff.hours == 1:
            return f"{diff.hours} час назад"
        elif 2 <= diff.hours <= 4:
            return f"{diff.hours} часа назад"
        else:
            return f"{diff.hours} часов назад"
    elif diff.minutes > 0:
        if diff.minutes == 1:
            return f"{diff.minutes} минута назад"
        elif 2 <= diff.minutes <= 4:
            return f"{diff.minutes} минуты назад"
        else:
            return f"{diff.minutes} минут назад"
    else:
        return "меньше минуты назад"

# Функция для проверки наличия ссылки на Telegram в описании
def contains_telegram_link(description):
    telegram_pattern = re.compile(r't\.me/[a-zA-Z0-9_]+')
    match = telegram_pattern.search(description)
    if match:
        return True, match.group()
    return False, None

# Функция для проверки наличия ключевых слов, связанных с азартными играми, в описании
def contains_gambling_keywords(description):
    gambling_keywords = ["казино", "ставки", "беттинг", "gambling", "casino", "betting"]
    return any(keyword in description.lower() for keyword in gambling_keywords)

# Функция для поиска неактивных каналов
def find_inactive_channels(query, min_subs=2000, max_subs=1000000, inactive_months=6, region_codes=["RU", "UA", "BY", "KZ"], seen_channels=None, max_channels=200):
    if seen_channels is None:
        seen_channels = set()

    print("Поиск каналов начался...")
    total_channels_analyzed = 0
    inactive_channels = []
    threshold_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=inactive_months * 30)

    while total_channels_analyzed < max_channels:
        channels = search_channels(query, region_codes=region_codes, seen_channels=seen_channels, max_channels=max_channels - total_channels_analyzed)
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
                "region": snippet.get('country', 'Не указано'),
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
                                f"{len(inactive_channels)}. Название: {channel_info['title']}, Подписчики: {channel_info['subscriber_count']}, "
                                f"Последнее видео: {time_since_last_video}, Регион: {channel_info['region']}"
                            )

        if len(channels) < max_channels - total_channels_analyzed:
            break

    if not inactive_channels:
        print("По запросу каналов не найдено.")

    return inactive_channels, seen_channels, total_channels_analyzed

def extract_email(description):
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

# Основной блок
if __name__ == "__main__":
    try:
        while True:
            query = input("Введите запрос для поиска каналов: ")
            max_channels = int(input("Введите максимальное количество каналов для анализа: "))

            # Параметры фильтрации
            min_subs = 2000
            max_subs = 1000000
            region_codes = ["RU", "UA", "BY", "KZ"]
            seen_channels_file = 'seen_channels.json'

            seen_channels = load_seen_channels(seen_channels_file)

            inactive_channels, seen_channels, total_channels_analyzed = find_inactive_channels(
                query, min_subs=min_subs, max_subs=max_subs, region_codes=region_codes, seen_channels=seen_channels, max_channels=max_channels
            )

            save_seen_channels(seen_channels_file, seen_channels)

            if inactive_channels:
                print(f"\nСсылки на Telegram для найденных каналов:")
                for idx, channel in enumerate(inactive_channels, start=1):
                    telegram_in_description, telegram_link = contains_telegram_link(channel['description'])
                    if telegram_link:
                        print(f"{idx}. Название: {channel['title']}, {telegram_link}")
            else:
                print("Неактивных каналов по заданным критериям не найдено.")

            print(f"\nОбработано {total_channels_analyzed} каналов.")

            # Сохранение последнего рабочего API ключа
            save_last_working_key_index('api_keys.json', current_api_key_index)

            if not ask_continue():
                break

    except KeyboardInterrupt:
        print("\nПоиск прерван пользователем.")
    except googleapiclient.errors.HttpError as e:
        if 'quotaExceeded' in str(e):
            print("Превышена квота API. Поиск остановлен.")
        else:
            print(f"Произошла ошибка: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")
