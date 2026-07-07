# ChannelFreeze

Find inactive YouTube channels based on search queries and custom filtering criteria.

ChannelFreeze helps discover abandoned or inactive YouTube channels by analyzing subscriber count, upload activity and channel metadata.

---

## Features

- 🔍 Search YouTube channels by keyword
- 📅 Detect inactive channels based on the last uploaded video
- 👥 Filter by subscriber count
- 🌍 Search across multiple regions
- 📢 Detect Telegram links
- 🚫 Ignore gambling-related channels
- 🔄 Automatically rotate YouTube API keys when quota is exceeded
- 💾 Store previously analyzed channels to avoid duplicates

---

## Technologies

- Python
- YouTube Data API v3

---

## Setup

1. Clone the repository.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a private API key config:

   ```bash
   cp api_keys.example.json api_keys.json
   ```

4. Add one or more YouTube Data API v3 keys to `api_keys.json`.

---

## Usage

Run the parser:

```bash
python parser.py
```

The script stores processed channel IDs in `seen_channels.json` to avoid duplicate analysis between runs.

---

## Private files

The following local files are intentionally ignored by Git:

- `api_keys.json`
- `seen_channels.json`
- `.DS_Store`
- virtual environments and IDE settings

---

## Purpose

This project was built to automate the discovery of inactive YouTube channels for outreach and research purposes.

---

## Future improvements

- Export results to CSV
- GUI interface
- More advanced filtering
- Better reporting
