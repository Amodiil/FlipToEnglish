# Architecture

## System Overview

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   collector.py   │     │  translator.py   │     │     bot.py       │
│                  │     │                  │     │                  │
│  Telethon client │     │  Claude AI API   │     │  Telegram Bot    │
│  monitors 9 UA   │────▶│  translates to   │────▶│  delivers news   │
│  news channels   │     │  3 English lvls  │     │  to users        │
│                  │     │                  │     │                  │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │         ┌──────────────┴──────────┐             │
         └────────▶│   fliptoenglish.db      │◀────────────┘
                   │   (SQLite database)     │
                   └─────────────────────────┘
```

All three components share a single SQLite database (`fliptoenglish.db`). They can run independently and communicate only through the database.

## Pipeline Flow

```
1. COLLECT        2. TRANSLATE         3. DELIVER
   │                  │                    │
   │  New post        │  Untranslated      │  Translated
   │  appears in      │  news found        │  news ready
   │  UA channel      │  in DB             │  for user
   │       │          │       │            │       │
   │       ▼          │       ▼            │       ▼
   │  Download text   │  Send to Claude    │  Match user's
   │  + media         │  AI for            │  channels &
   │       │          │  translation       │  level
   │       ▼          │       │            │       │
   │  Check for       │       ▼            │       ▼
   │  duplicates      │  Get 3 levels:     │  Format with
   │       │          │  - beginner        │  underlined
   │       ▼          │  - intermediate    │  words
   │  Save to DB      │  - advanced        │       │
   │  (news table)    │       │            │       ▼
   │                  │       ▼            │  Send via
   │                  │  Extract word      │  Telegram
   │                  │  lists per level   │  with media
   │                  │       │            │
   │                  │       ▼            │
   │                  │  Save to DB        │
   │                  │                    │
```

## Database Schema

### `news` table

Stores all collected news posts and their translations.

| Column                      | Type    | Description                                      |
|-----------------------------|---------|--------------------------------------------------|
| `id`                        | INTEGER | Primary key, auto-increment                      |
| `channel`                   | TEXT    | Source channel (e.g. `@uniannet`)                |
| `message_id`                | INTEGER | Original Telegram message ID                     |
| `original_text`             | TEXT    | Original Ukrainian text                          |
| `media_type`                | TEXT    | `photo`, `video`, `document`, or NULL            |
| `media_file_id`             | TEXT    | Local path to primary media file                 |
| `media_files`               | TEXT    | JSON array of `{type, path}` for albums          |
| `created_at`                | TEXT    | ISO 8601 timestamp when post was published       |
| `collected_at`              | TEXT    | ISO 8601 timestamp when post was collected       |
| `is_duplicate`              | INTEGER | `1` if detected as duplicate, `0` otherwise      |
| `translation_beginner`      | TEXT    | English translation — beginner level             |
| `translation_intermediate`  | TEXT    | English translation — intermediate level         |
| `translation_advanced`      | TEXT    | English translation — advanced level             |
| `is_translated`             | INTEGER | `1` once translated (or failed), `0` if pending  |
| `word_list_beginner`        | TEXT    | JSON dict: English word → Ukrainian translation  |
| `word_list_intermediate`    | TEXT    | JSON dict: English word → Ukrainian translation  |
| `word_list_advanced`        | TEXT    | JSON dict: English word → Ukrainian translation  |

### `users` table

Stores per-user preferences and setup state.

| Column           | Type    | Description                                       |
|------------------|---------|---------------------------------------------------|
| `user_id`        | INTEGER | Primary key — Telegram user ID                    |
| `channels`       | TEXT    | Comma-separated list of selected channels         |
| `english_level`  | TEXT    | `beginner`, `intermediate`, or `advanced`         |
| `news_per_day`   | INTEGER | Max news per day (default: 5)                     |
| `setup_complete` | INTEGER | `1` if both channels and level are configured     |
| `welcomed`       | INTEGER | `1` if the welcome message has been shown         |

### `user_news_log` table

Tracks which news items have been sent to which user (prevents re-sending).

| Column    | Type    | Description                      |
|-----------|---------|----------------------------------|
| `user_id` | INTEGER | Telegram user ID                 |
| `news_id` | INTEGER | Reference to `news.id`           |

Primary key: `(user_id, news_id)`

## Component Details

### collector.py

- Uses **Telethon** (user-client API) to monitor channels in real-time
- On startup, backfills the last 1 post per channel to catch up
- Handles **media groups (albums)** — buffers grouped messages for 2 seconds before saving as a single entry
- Downloads photos, videos, and documents up to 20 MB
- Performs **duplicate detection** using `SequenceMatcher` (threshold: 0.72) against the last 200 posts

### translator.py

- Polls the database every 10 seconds for untranslated news
- Calls **Claude AI** (`claude-haiku-4-5-20251001`) with a structured prompt
- Produces 3 translation levels with difficulty-appropriate vocabulary highlighting (`_word_` markers)
- Generates word lists mapping highlighted English words to Ukrainian translations
- Validates translation quality (checks for formatting artifacts, excessive Cyrillic, orphaned markers)
- Retries failed translations once before marking as failed
- Post-translation duplicate detection (threshold: 0.60) catches semantically similar news from different channels

### bot.py

- Uses **python-telegram-bot** library
- Full setup flow: channel selection → level selection → start reading
- Supports custom channel requests
- **Auto-delivery loop** — every 30 seconds, pushes new translated news to all configured users
- Inline buttons: "Show original" (Ukrainian text), "Words" (vocabulary list), "Next" (fetch next news)

## How to Add New Channels

1. Open `collector.py` and add the channel to the `CHANNELS` list:
   ```python
   CHANNELS = [
       "@truexanewsua",
       # ... existing channels ...
       "@your_new_channel",  # <-- add here
   ]
   ```

2. Add the same channel to the `CHANNELS` list in `bot.py` so users can select it:
   ```python
   CHANNELS = [
       "@truexanewsua",
       # ... existing channels ...
       "@your_new_channel",  # <-- add here
   ]
   ```

3. Restart `collector.py` — it will begin monitoring the new channel immediately.

> **Tip:** The channel must be a public Telegram channel (starting with `@`). The Telethon client must be able to access it.
