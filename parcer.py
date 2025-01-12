import json
import datetime
from dateutil import parser
from googleapiclient.discovery import build
import googleapiclient.errors

# API ключ для доступа к YouTube Data API
API_KEY = "AIzaSyBL4qjEPKvNoChLoTVRLjToR_nLf3d09qE"
youtube = build('youtube', 'v3', developerKey=API_KEY)

# Имя файла для хранения данных
JSON_FILE = "channels.json"

# Загрузка данных из файла
def load_data():
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"channels": []}

# Сохранение данных в файл
def save_data(data):
    with open(JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# Проверка, обработан ли канал
def is_processed(channel_id, data):
    return any(channel["channel_id"] == channel_id for channel in data["channels"])

# Поиск каналов через YouTube API
def search_channels(query, region_codes, max_results=50):
    channels = []
    for region in region_codes:
        try:
            response = youtube.search().list(
                q=query,
                type="channel",
                part="snippet",
                maxResults=max_results,
                regionCode=region
            ).execute()

            for item in response.get('items', []):
                channels.append({
                    "channel_id": item['id']['channelId'],
                    "title": item['snippet']['title'],
                    "description": item['snippet']['description'],
                    "region": region
                })
        except googleapiclient.errors.HttpError as e:
            if 'quotaExceeded' in str(e):
                print("Превышена квота API. Попробуйте позже.")
                break
            else:
                print(f"Ошибка API: {e}")
    return channels

# Получение информации о канале
def get_channel_details(channel_id):
    try:
        response = youtube.channels().list(
            id=channel_id,
            part="snippet,statistics,contentDetails"
        ).execute()

        if not response.get('items'):
            return None

        channel = response['items'][0]
        stats = channel['statistics']
        details = {
            "channel_id": channel['id'],
            "title": channel['snippet']['title'],
            "description": channel['snippet']['description'],
            "subscriber_count": int(stats.get('subscriberCount', 0)),
            "video_count": int(stats.get('videoCount', 0)),
            "last_upload_date": None,
            "region": channel['snippet'].get('country', 'Не указано'),
        }

        uploads_playlist_id = channel['contentDetails']['relatedPlaylists'].get('uploads')
        if uploads_playlist_id:
            last_upload_date = get_last_video_date(uploads_playlist_id)
            details['last_upload_date'] = last_upload_date
        return details
    except googleapiclient.errors.HttpError as e:
        print(f"Ошибка при получении данных канала {channel_id}: {e}")
        return None

# Получение даты последнего видео
def get_last_video_date(uploads_playlist_id):
    try:
        response = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="contentDetails",
            maxResults=1
        ).execute()

        if not response.get('items'):
            return None

        last_video_date = response['items'][0]['contentDetails']['videoPublishedAt']
        return parser.isoparse(last_video_date).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception as e:
        print(f"Ошибка при получении даты последнего видео: {e}")
        return None

# Основная функция
def main():
    data = load_data()
    query = input("Введите запрос для поиска каналов: ")
    region_codes = ["RU", "UA", "BY", "KZ"]
    max_results = 50

    # Поиск новых каналов
    print("Поиск новых каналов...")
    new_channels = search_channels(query, region_codes, max_results)
    print(f"Найдено {len(new_channels)} новых каналов.")

    for channel in new_channels:
        if not is_processed(channel['channel_id'], data):
            details = get_channel_details(channel['channel_id'])
            if details:
                data["channels"].append(details)

    save_data(data)
    print("Обработка завершена. Все данные сохранены в файл.")

if __name__ == "__main__":
    main()
