"""
collector.py — monitors public Telegram channels via Telethon and saves new
posts to the local SQLite database for the FlipToEnglish bot to deliver.

Run once interactively to authenticate (enter phone + code).
After that the session file (collector.session) keeps you logged in.

Usage:
    python collector.py
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

load_dotenv()

API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DB_PATH  = "fliptoenglish.db"
MEDIA_DIR = "media"

# Max file size to download (bytes). Videos above this are skipped to save disk.
MAX_MEDIA_BYTES = 20 * 1024 * 1024  # 20 MB

# On every startup fetch only the last 1 post per channel to catch up quickly.
BACKFILL_LIMIT = 1

# Seconds to wait before flushing a media group (album) buffer.
GROUP_FLUSH_DELAY = 2.0

CHANNELS = [
    "@truexanewsua",
    "@vanek_nikolaev",
    "@u_now",
    "@insiderUKR",
    "@Tsaplienko",
    "@Ukraine_365News",
    "@uniannet",
    "@TCH_channel",
    "@suspilnenews",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Buffers for media-group (album) accumulation during live monitoring
_group_buffer: dict[int, list] = {}   # grouped_id -> [(msg, channel_tag), ...]
_group_tasks: dict[int, asyncio.Task] = {}


# ── Database ──────────────────────────────────────────────────────────────────

def init_news_table():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                channel       TEXT    NOT NULL,
                message_id    INTEGER,
                original_text TEXT    NOT NULL DEFAULT '',
                media_type    TEXT,
                media_file_id TEXT,
                media_files   TEXT,
                created_at    TEXT    NOT NULL,
                collected_at  TEXT    NOT NULL,
                is_duplicate  INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Migrate existing tables that may be missing new columns
        cols = [r[1] for r in con.execute("PRAGMA table_info(news)").fetchall()]
        for col_name, col_def in [
            ("message_id",   "INTEGER"),
            ("collected_at", "TEXT"),
            ("media_files",  "TEXT"),
        ]:
            if col_name not in cols:
                con.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_def}")
        # Backfill collected_at from created_at for existing rows
        con.execute(
            "UPDATE news SET collected_at = created_at WHERE collected_at IS NULL"
        )
        con.commit()


def already_saved(channel: str, message_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT id FROM news WHERE channel = ? AND message_id = ?",
            (channel, message_id),
        ).fetchone()
    return row is not None


def check_duplicate(text: str, threshold: float = 0.72) -> bool:
    if not text or len(text) < 30:
        return False
    compare = text[:400]
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT original_text FROM news WHERE is_duplicate = 0 ORDER BY id DESC LIMIT 200"
        ).fetchall()
    for (existing,) in rows:
        if not existing:
            continue
        if SequenceMatcher(None, compare, existing[:400]).ratio() >= threshold:
            return True
    return False


def save_news(
    channel: str,
    message_id: int,
    text: str,
    media_type: str | None,
    media_path: str | None,
    media_files: list | None,
    is_duplicate: bool,
) -> int:
    """Insert a news row and return its new id."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    media_files_json = json.dumps(media_files, ensure_ascii=False) if media_files else None
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """INSERT INTO news
                   (channel, message_id, original_text, media_type, media_file_id,
                    media_files, created_at, collected_at, is_duplicate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                channel, message_id, text, media_type, media_path,
                media_files_json, now, now, int(is_duplicate),
            ),
        )
        con.commit()
        return cur.lastrowid


# ── Media helpers ─────────────────────────────────────────────────────────────

def _media_size(message) -> int:
    try:
        if isinstance(message.media, MessageMediaDocument):
            return message.media.document.size
        if isinstance(message.media, MessageMediaPhoto):
            sizes = message.media.photo.sizes
            last = sizes[-1]
            return getattr(last, "size", 0)
    except Exception:
        pass
    return 0


async def _download_media(message, channel_tag: str) -> tuple:
    """Download media to MEDIA_DIR. Returns (media_type, local_path) or (None, None)."""
    if not message.media:
        return None, None

    size = _media_size(message)
    if size and size > MAX_MEDIA_BYTES:
        log.info("Skipping large media (%d MB) from %s", size // 1_048_576, channel_tag)
        return None, None

    tag = channel_tag.lstrip("@")
    msg_id = message.id

    if isinstance(message.media, MessageMediaPhoto):
        path = os.path.join(MEDIA_DIR, f"{tag}_{msg_id}.jpg")
        await message.download_media(file=path)
        return "photo", path

    if isinstance(message.media, MessageMediaDocument):
        mime = (message.media.document.mime_type or "").lower()
        if mime.startswith("video"):
            path = os.path.join(MEDIA_DIR, f"{tag}_{msg_id}.mp4")
            await message.download_media(file=path)
            return "video", path
        if mime.startswith("image") or "gif" in mime:
            ext = ".gif" if "gif" in mime else ".jpg"
            path = os.path.join(MEDIA_DIR, f"{tag}_{msg_id}{ext}")
            await message.download_media(file=path)
            return "photo", path
        # Other documents (PDFs, etc.) — download as-is
        if mime:
            path = os.path.join(MEDIA_DIR, f"{tag}_{msg_id}")
            await message.download_media(file=path)
            return "document", path
        return None, None

    return None, None


# ── Single-message processing ────────────────────────────────────────────────

async def _process_message(client, msg, channel_tag: str) -> None:
    """Process a single (non-grouped) message."""
    if already_saved(channel_tag, msg.id):
        log.debug("[%s] message #%d already in db — skipping", channel_tag, msg.id)
        return

    text = (msg.text or getattr(msg, "caption", None) or "").strip()

    media_type, media_path = None, None
    try:
        media_type, media_path = await _download_media(msg, channel_tag)
    except Exception as exc:
        log.warning("Media download failed for %s #%d: %s", channel_tag, msg.id, exc)

    if not text and not media_type:
        return

    # Build media_files list for single-media items too (consistency)
    media_files = None
    if media_type and media_path:
        media_files = [{"type": media_type, "path": media_path}]

    duplicate = check_duplicate(text) if text else False
    news_id = save_news(channel_tag, msg.id, text, media_type, media_path, media_files, duplicate)

    log.info(
        "[%s] %s id=%d | %.80s",
        channel_tag,
        "DUP " if duplicate else "NEW ",
        news_id,
        text or f"[{media_type}]",
    )


# ── Media-group (album) processing ──────────────────────────────────────────

async def _process_message_group(msgs: list, channel_tag: str) -> None:
    """Process a list of messages that belong to the same media group (album)."""
    if not msgs:
        return

    # Pick the message with text/caption as the primary record
    primary = next(
        (m for m in msgs if (m.text or getattr(m, "caption", None) or "").strip()),
        msgs[0],
    )

    if already_saved(channel_tag, primary.id):
        log.debug("[%s] group message #%d already in db — skipping", channel_tag, primary.id)
        return

    text = (primary.text or getattr(primary, "caption", None) or "").strip()

    # Download all media in the group
    media_files = []
    first_type, first_path = None, None

    for m in msgs:
        try:
            mtype, mpath = await _download_media(m, channel_tag)
            if mtype and mpath:
                media_files.append({"type": mtype, "path": mpath})
                if first_type is None:
                    first_type, first_path = mtype, mpath
        except Exception as exc:
            log.warning("Media download failed in group %s #%d: %s", channel_tag, m.id, exc)

    if not text and not media_files:
        return

    duplicate = check_duplicate(text) if text else False
    news_id = save_news(
        channel_tag, primary.id, text,
        first_type, first_path,
        media_files if media_files else None,
        duplicate,
    )

    log.info(
        "[%s] %s id=%d | %.80s [%d media]",
        channel_tag,
        "DUP " if duplicate else "NEW ",
        news_id,
        text or f"[{first_type}]",
        len(media_files),
    )


# ── Backfill ──────────────────────────────────────────────────────────────────

async def backfill_channels(client: TelegramClient) -> None:
    """Fetch the last BACKFILL_LIMIT posts from each channel, skip already-saved ones."""
    log.info("Backfilling last %d post(s) from each channel…", BACKFILL_LIMIT)
    for channel_tag in CHANNELS:
        try:
            messages = await client.get_messages(channel_tag, limit=BACKFILL_LIMIT)
            # Separate grouped (album) messages from singles
            groups: dict[int, list] = {}
            singles = []
            for msg in reversed(messages):
                gid = getattr(msg, "grouped_id", None)
                if gid:
                    groups.setdefault(gid, []).append(msg)
                else:
                    singles.append(msg)

            for msg in singles:
                await _process_message(client, msg, channel_tag)

            for group_msgs in groups.values():
                await _process_message_group(group_msgs, channel_tag)

        except Exception as exc:
            log.warning("Could not backfill %s: %s", channel_tag, exc)
    log.info("Backfill complete.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not API_ID or not API_HASH:
        raise SystemExit(
            "API_ID and API_HASH are required in .env\n"
            "Get them at https://my.telegram.org/apps"
        )

    init_news_table()

    client = TelegramClient("collector", API_ID, API_HASH)

    try:
        await client.start()
        log.info("Collector connected. Monitoring %d channels.", len(CHANNELS))

        await backfill_channels(client)

        @client.on(events.NewMessage(chats=CHANNELS))
        async def on_new_message(event):
            msg = event.message

            try:
                username = (await event.get_chat()).username or ""
                channel = f"@{username}" if username else str(event.chat_id)
            except Exception:
                channel = str(event.chat_id)

            grouped_id = getattr(msg, "grouped_id", None)

            if grouped_id:
                # Buffer this message for group processing
                if grouped_id not in _group_buffer:
                    _group_buffer[grouped_id] = []
                _group_buffer[grouped_id].append((msg, channel))

                # Cancel any existing flush task and reschedule
                old_task = _group_tasks.pop(grouped_id, None)
                if old_task and not old_task.done():
                    old_task.cancel()

                gid = grouped_id  # capture for closure

                async def flush_group(gid=gid):
                    await asyncio.sleep(GROUP_FLUSH_DELAY)
                    items = _group_buffer.pop(gid, [])
                    _group_tasks.pop(gid, None)
                    if items:
                        ch = items[0][1]
                        await _process_message_group([m for m, _ in items], ch)

                _group_tasks[grouped_id] = asyncio.create_task(flush_group())
            else:
                await _process_message(client, msg, channel)

        log.info("Listening for new posts (no per-channel limit)…")
        await client.run_until_disconnected()

    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down.")
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            loop.close()
